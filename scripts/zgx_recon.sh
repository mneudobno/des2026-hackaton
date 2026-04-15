#!/usr/bin/env bash
# zgx_recon.sh — collect an objective snapshot of a machine's relevant state
# for the hackathon. Pure bash, no Python, no extra packages — works on DGX OS
# out of the box.
#
# Output:
#   - Full human-readable text on stdout
#   - Structured JSON on fd 3 if called with `--json /path/to/out.json`,
#     else appended as a `=== JSON ===` block at the end of stdout.
#
# Usage:
#   bash zgx_recon.sh                      # text to stdout
#   bash zgx_recon.sh --json recon.json    # text to stdout + json to file

set -u
JSON_OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON_OUT="$2"; shift 2 ;;
    -h|--help) sed -n '1,20p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ---------- helpers ----------
say() { printf "\n=== %s ===\n" "$*"; }
try() { "$@" 2>&1 || true; }
have() { command -v "$1" >/dev/null 2>&1; }

json_escape() {
  # portable JSON string escape — joins multi-line input with literal "\n",
  # no trailing newline artifact for single-line values.
  tr -d '\r' | awk '{
    gsub(/\\/, "\\\\");
    gsub(/"/, "\\\"");
    gsub(/\t/, "\\t");
    printf "%s", (NR==1 ? "" : "\\n") $0
  }'
}

# ---------- collect ----------
HOSTNAME_="$(hostname 2>/dev/null || echo unknown)"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

say "identity"
echo "hostname: $HOSTNAME_"
echo "timestamp: $TS"
echo "uname: $(uname -a)"
if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  echo "os: ${PRETTY_NAME:-unknown}"
  OS_PRETTY="${PRETTY_NAME:-unknown}"
else
  OS_PRETTY="unknown"
fi
ARCH="$(uname -m 2>/dev/null || echo unknown)"
echo "arch: $ARCH"

say "GPU / nvidia"
GPU_NAME=""
GPU_MEM=""
GPU_DRIVER=""
if have nvidia-smi; then
  GPU_LINE="$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null | head -n1)"
  echo "$GPU_LINE"
  GPU_NAME="$(echo "$GPU_LINE" | awk -F',' '{print $1}' | sed 's/^ *//;s/ *$//')"
  GPU_MEM="$(echo "$GPU_LINE" | awk -F',' '{print $2}' | sed 's/^ *//;s/ *$//')"
  GPU_DRIVER="$(echo "$GPU_LINE" | awk -F',' '{print $3}' | sed 's/^ *//;s/ *$//')"
  echo "--- full ---"
  try nvidia-smi
else
  echo "nvidia-smi NOT FOUND"
fi

say "CPU / memory"
CPU_CORES="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 0)"
echo "cores: $CPU_CORES"
if have free; then
  MEM_TOTAL="$(free -h 2>/dev/null | awk '/^Mem:/{print $2}')"
  MEM_FREE="$(free -h 2>/dev/null | awk '/^Mem:/{print $7}')"
  free -h 2>/dev/null
else
  # macOS fallback
  if have vm_stat; then
    MEM_TOTAL="$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.1fG", $1/1024/1024/1024}')"
    MEM_FREE="(see vm_stat)"
    try vm_stat
  fi
fi

say "disk"
DISK_FREE=""
try df -h / /home /data /var /tmp 2>/dev/null
DISK_FREE="$(df -h / 2>/dev/null | awk 'NR==2{print $4}')"

say "docker"
DOCKER_RUNNING="false"
DOCKER_PS=""
if have docker; then
  if docker info >/dev/null 2>&1; then
    DOCKER_RUNNING="true"
    DOCKER_PS="$(docker ps --format '{{.Names}}|{{.Ports}}|{{.Image}}' 2>/dev/null)"
    docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Image}}'
    echo "--- images (head 20) ---"
    try docker images --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}' | head -20
  else
    echo "docker installed but daemon not reachable"
  fi
else
  echo "docker NOT installed"
fi

# Heuristic: NIM containers usually have 'nim' or a nvidia/nemotron/riva image name
NIM_CONTAINERS=""
if [[ -n "$DOCKER_PS" ]]; then
  NIM_CONTAINERS="$(echo "$DOCKER_PS" | grep -iE 'nim|nemotron|riva|nvcr\.io|nvidia/' || true)"
fi

say "NVIDIA NeMo Agent Toolkit"
NAT_PRESENT="false"
if have nat; then
  NAT_PRESENT="true"
  echo "nat found: $(command -v nat)"
  try nat --help | head -5
elif [[ -d /opt/nvidia/nemo-agent-toolkit ]]; then
  NAT_PRESENT="true"
  echo "toolkit directory present: /opt/nvidia/nemo-agent-toolkit"
else
  echo "NAT not found (ok, our runtime doesn't require it)"
fi

say "Ollama"
OLLAMA_RUNNING="false"
OLLAMA_MODELS=""
if have ollama; then
  echo "ollama at: $(command -v ollama)"
  if curl -sf --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    OLLAMA_RUNNING="true"
    echo "--- models ---"
    OLLAMA_MODELS="$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ',' | sed 's/,$//')"
    try ollama list
  else
    echo "ollama installed but daemon not reachable on :11434"
  fi
else
  echo "ollama NOT installed"
fi

say "listening ports"
PORTS_OF_INTEREST="11434 8000 8001 8080 50051 9000 5000 7860"
PORTS_IN_USE=""
for p in $PORTS_OF_INTEREST; do
  if have lsof; then
    USER_OF="$(lsof -iTCP:"$p" -sTCP:LISTEN -P -n 2>/dev/null | awk 'NR==2{print $1}')"
  elif have ss; then
    USER_OF="$(ss -ltn 2>/dev/null | awk -v p=":$p" '$4 ~ p {print "listening"; exit}')"
  else
    USER_OF=""
  fi
  if [[ -n "$USER_OF" ]]; then
    echo "  :$p -> $USER_OF"
    PORTS_IN_USE="$PORTS_IN_USE $p"
  else
    echo "  :$p -> free"
  fi
done
PORTS_IN_USE="$(echo "$PORTS_IN_USE" | sed 's/^ *//')"

say "network interfaces"
if have ip; then
  try ip -4 -o addr show | awk '{print $2, $4}'
elif have ifconfig; then
  try ifconfig | awk '/inet /{print $2}'
fi

say "USB devices (look for robot)"
if have lsusb; then
  try lsusb
else
  echo "lsusb not available"
fi

say "python / uv"
PY_VERSION=""
if have python3; then
  PY_VERSION="$(python3 --version 2>&1)"
  echo "$PY_VERSION"
fi
UV_PRESENT="false"
if have uv; then
  UV_PRESENT="true"
  echo "uv: $(uv --version 2>/dev/null)"
fi

# ---------- JSON summary ----------
emit_json() {
  local escaped_os escaped_gpu_name escaped_ollama escaped_nim escaped_docker_ps
  escaped_os="$(printf "%s" "$OS_PRETTY" | json_escape)"
  escaped_gpu_name="$(printf "%s" "$GPU_NAME" | json_escape)"
  escaped_ollama="$(printf "%s" "$OLLAMA_MODELS" | json_escape)"
  escaped_nim="$(printf "%s" "$NIM_CONTAINERS" | json_escape)"
  escaped_docker_ps="$(printf "%s" "$DOCKER_PS" | json_escape)"

  cat <<EOF
{
  "hostname": "$(printf "%s" "$HOSTNAME_" | json_escape)",
  "timestamp": "$TS",
  "os": "$escaped_os",
  "arch": "$ARCH",
  "gpu": {
    "name": "$escaped_gpu_name",
    "memory_total": "$(printf "%s" "$GPU_MEM" | json_escape)",
    "driver": "$(printf "%s" "$GPU_DRIVER" | json_escape)",
    "present": $([ -n "$GPU_NAME" ] && echo true || echo false)
  },
  "cpu_cores": ${CPU_CORES:-0},
  "memory": {
    "total": "$(printf "%s" "${MEM_TOTAL:-}" | json_escape)",
    "free": "$(printf "%s" "${MEM_FREE:-}" | json_escape)"
  },
  "disk_free_root": "$(printf "%s" "${DISK_FREE:-}" | json_escape)",
  "docker": {
    "running": $DOCKER_RUNNING,
    "ps": "$escaped_docker_ps",
    "nim_containers": "$escaped_nim"
  },
  "nat_present": $NAT_PRESENT,
  "ollama": {
    "running": $OLLAMA_RUNNING,
    "models": "$escaped_ollama"
  },
  "ports_in_use": "$(printf "%s" "$PORTS_IN_USE" | json_escape)",
  "python_version": "$(printf "%s" "$PY_VERSION" | json_escape)",
  "uv_present": $UV_PRESENT
}
EOF
}

if [[ -n "$JSON_OUT" ]]; then
  emit_json > "$JSON_OUT"
  echo
  echo "=== JSON written to $JSON_OUT ==="
else
  say "JSON"
  emit_json
fi
