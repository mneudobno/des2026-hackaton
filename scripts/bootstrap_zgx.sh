#!/usr/bin/env bash
# bootstrap_zgx.sh — bring up local model serving on an HP ZGX Nano (DGX OS).
#
# Usage:
#   bash scripts/bootstrap_zgx.sh [--role primary|secondary] [--models llm,vlm,stt,tts]
#
# Idempotent: re-running is safe; it skips already-pulled models / running services.

set -euo pipefail

ROLE="primary"
MODELS="llm,vlm,stt,tts"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) ROLE="$2"; shift 2 ;;
    --models) MODELS="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

LLM_MODEL="${LLM_MODEL:-qwen2.5:14b-instruct}"
# Ollama tag is `qwen2.5vl:7b` (no dash); NIM containers may use `qwen2.5-vl:7b`.
VLM_MODEL="${VLM_MODEL:-qwen2.5vl:7b}"
STT_MODEL="${STT_MODEL:-large-v3-turbo}"

log() { printf "[bootstrap %s] %s\n" "$ROLE" "$*" >&2; }

log "checking GPU..."
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || true
else
  log "WARN: nvidia-smi not found (ok on Mac dev, fail on ZGX)"
fi

log "ensuring ollama is installed..."
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

log "starting ollama daemon..."
if ! pgrep -x ollama >/dev/null; then
  nohup ollama serve >/tmp/ollama.log 2>&1 &
  sleep 2
fi

pull_if_missing() {
  local m="$1"
  if ! ollama list | awk '{print $1}' | grep -qx "$m"; then
    log "pulling $m..."
    ollama pull "$m"
  else
    log "$m already present"
  fi
}

if [[ ",$MODELS," == *",llm,"* && "$ROLE" == "primary" ]]; then
  pull_if_missing "$LLM_MODEL"
fi
if [[ ",$MODELS," == *",vlm,"* && "$ROLE" == "primary" ]]; then
  pull_if_missing "$VLM_MODEL"
fi

if [[ ",$MODELS," == *",stt,"* && "$ROLE" == "secondary" ]]; then
  log "STT (faster-whisper) will lazy-load on first call: $STT_MODEL"
fi
if [[ ",$MODELS," == *",tts,"* && "$ROLE" == "secondary" ]]; then
  if ! command -v piper >/dev/null; then
    log "piper not found — install with: pip install piper-tts && download a voice (.onnx + .json)"
  fi
fi

log "warming caches..."
if [[ "$ROLE" == "primary" ]]; then
  curl -s http://127.0.0.1:11434/api/generate \
    -d "{\"model\":\"$LLM_MODEL\",\"prompt\":\"ok\",\"stream\":false,\"options\":{\"num_predict\":4}}" \
    >/dev/null && log "LLM warm: ok" || log "LLM warm: FAIL"
fi

log "done."
