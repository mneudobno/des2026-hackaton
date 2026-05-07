#!/usr/bin/env bash
# bootstrap_zgx.sh — bring up local model serving on an HP ZGX Nano (DGX OS).
#
# Day-of (per organizer email 2026-05-05): vLLM + llama.cpp + Nemotron + OpenCode
# are pre-installed on the ZGX Nano boxes. We probe the vLLM endpoint first and
# only fall back to Ollama if it is absent. Ollama remains the canonical Mac
# dev path.
#
# Usage:
#   bash scripts/bootstrap_zgx.sh [--role primary|secondary] [--models llm,vlm,stt,tts]
#
# Env overrides:
#   VLLM_PORT          (default: 8000)        vLLM serving port
#   OLLAMA_PORT        (default: 11434)       Ollama serving port
#   VLLM_MODEL         (default: auto-detect first model from /v1/models)
#   LLM_MODEL          (default: qwen2.5:14b-instruct) Ollama fallback LLM tag
#   VLM_MODEL          (default: qwen2.5vl:7b)         Ollama fallback VLM tag
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

VLLM_PORT="${VLLM_PORT:-8000}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
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

# ---- vLLM probe (day-of primary) ---------------------------------------------
VLLM_OK=0
VLLM_MODELS_JSON="$(curl -fsS --max-time 2 "http://127.0.0.1:${VLLM_PORT}/v1/models" 2>/dev/null || true)"
if [[ -n "$VLLM_MODELS_JSON" ]]; then
  # Pick the first id from the response if VLLM_MODEL wasn't supplied.
  if [[ -z "${VLLM_MODEL:-}" ]]; then
    VLLM_MODEL="$(printf '%s' "$VLLM_MODELS_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("data") or [{}])[0].get("id",""))' 2>/dev/null || true)"
  fi
  # Only declare vLLM ready if /v1/models returned a usable model id.
  # Endpoint up but unloaded (empty data array) or malformed JSON → fall
  # through to Ollama rather than misreport "vLLM detected".
  if [[ -n "${VLLM_MODEL:-}" ]]; then
    VLLM_OK=1
    log "vLLM detected on :${VLLM_PORT} — primary model: ${VLLM_MODEL}. Skipping Ollama install."
  else
    log "vLLM responded on :${VLLM_PORT} but no usable model id (empty data?). Falling through to Ollama."
  fi
fi

if [[ "$VLLM_OK" -eq 1 ]]; then
  if [[ "$ROLE" == "primary" && -n "${VLLM_MODEL:-}" ]]; then
    log "warming vLLM (4-token request to ${VLLM_MODEL})..."
    curl -s -X POST "http://127.0.0.1:${VLLM_PORT}/v1/chat/completions" \
      -H "content-type: application/json" \
      -d "{\"model\":\"${VLLM_MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"ok\"}],\"max_tokens\":4}" \
      >/dev/null && log "vLLM warm: ok" || log "vLLM warm: FAIL (model name? auth?)"
  fi
  log "done (vLLM path)."
  exit 0
fi

# ---- Ollama fallback (Mac dev / ZGX without vLLM) ----------------------------
log "vLLM not detected on :${VLLM_PORT} — falling back to Ollama path."

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
  curl -s "http://127.0.0.1:${OLLAMA_PORT}/api/generate" \
    -d "{\"model\":\"$LLM_MODEL\",\"prompt\":\"ok\",\"stream\":false,\"options\":{\"num_predict\":4}}" \
    >/dev/null && log "LLM warm: ok" || log "LLM warm: FAIL"
fi

log "done (Ollama path)."
