---
name: recon-summary
description: Run hack recon against both ZGX boxes (or read the existing runs/recon-latest.json), then produce a five-line authoritative summary plus the next config edit. Trigger on "recon", "what's on the ZGX", "summarise the box", "did vLLM start", "what models are loaded", or whenever IPs land and the team needs to translate raw recon output into a decision. Replaces the manual reading of recon-latest.json that nobody actually does at T+0:05.
---

# recon-summary — turn recon JSON into a config decision

`hack recon user@<host>` SSHs into a ZGX box, runs `scripts/zgx_recon.sh`,
and writes `runs/recon-<host>-<ts>.json` (plus a symlink
`runs/recon-latest.json`). The output is verbose. Your job is to compress
it into something the team can act on in 60 seconds.

## Procedure

1. **Get the IPs.** Try in order:
   a. **`docs/DAY_OF_BRIEF.md` — Hardware + network checklist.** The team
      types ZGX-A / ZGX-B IPs there as they hear them at 10:30. Look for
      lines `- [ ] ZGX-A IP:` and `- [ ] ZGX-B IP:`. If both are filled in
      (not still `___.___.___.___`), use those — they're the canonical
      source.
   b. **The user's chat message.** If the brief slots are empty but the
      user pasted IPs in chat, use those.
   c. **Ask the user.** Last resort.
   Also read the SSH user from the brief (`SSH user: ___`); default to
   `user` if blank.

2. **Run recon for each box** (skip if `runs/recon-latest.json` was written
   in this session and the IPs match):
   ```
   uv run hack recon <ssh-user>@<zgx-a-ip>
   uv run hack recon <ssh-user>@<zgx-b-ip>
   ```
   If multiple hosts have been reconned, list both summaries side-by-side.

3. **Extract these fields** (in this order; missing field = mark `?`):
   - GPU model + memory (e.g. "GB10 128 GB unified")
   - vLLM status: is `:8000/v1/models` responding? If yes, list the served
     model `id`s.
   - Ollama status: is `:11434/api/tags` responding? If yes, list tag names.
   - NIM containers: any `nvcr.io/nim` rows in `docker ps` output?
   - Disk free on `/` (warn if <20 GB).
   - Hostname / IP echo so the team knows which is which.

4. **Decide what to swap in `configs/agent.yaml`.** Use the
   `swap-llm` skill's profile table:
   - vLLM up + Omni served → profile A (multimodal, single endpoint).
   - vLLM up + only Qwen served → profile C (LLM via vLLM, VLM on laptop).
   - vLLM down + Ollama up + qwen2.5:14b-instruct present → profile D-ish
     but pointed at the ZGX Ollama.
   - Both down → escalate; this is bad. Tell the user.

## Output template

Print exactly this shape so the team can read it across the room:

```
RECON · zgx-a (10.0.0.X)            zgx-b (10.0.0.Y)
─────────────────────────────────────────────────────
GPU         GB10 128 GB             GB10 128 GB
vLLM :8000  ✅ Nemotron-3-Nano-Omni ✅ same
            Qwen3-A3B
Ollama      ❌ not running          ❌ not running
NIM         (none)                  (none)
Disk /      214 GB free             198 GB free
─────────────────────────────────────────────────────
DECISION  →  configs/agent.yaml: profile A (Nemotron Omni multimodal)
            llm.base_url:  http://10.0.0.X:8000/v1
            llm.base_urls: [http://10.0.0.Y:8000/v1]
            vlm.* same as llm (Omni is multimodal)
NEXT      →  invoke /swap-llm with the model id, then `hack doctor`.
```

If the recon JSON is missing or stale, say "no recon-latest.json — run
`hack recon user@<zgx-a>` first" and stop. Do not guess.

## Don't

- Don't paste the raw recon JSON. The team has already seen it.
- Don't recommend an action you can't justify from the recon output (e.g.
  "use NIM" when no NIM containers were found).
- Don't retry recon yourself if SSH fails — that's a network problem,
  surface it to the user.
