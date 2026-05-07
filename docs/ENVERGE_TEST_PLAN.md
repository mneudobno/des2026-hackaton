# Enverge DGX Spark dry-run — test plan

**Purpose:** validate `scripts/bootstrap_zgx.sh`, NIM/Ollama model pulls,
and end-to-end latency on **actual GB10 hardware** before the judged run.
Enverge ([spark.enverge.ai](https://spark.enverge.ai/)) rents real DGX Spark
boxes at ~$0.48/hr, so a 2-hour session runs ~$1.

Target budget: **2 hours wall-clock**, ~$1 spend. If something blocks for
more than 20 min, skip it and log the gap in `REHEARSALS.md`.

## Prerequisites

- [ ] Enverge account access granted + SSH key added
- [ ] Local repo on latest `main`, `git status` clean
- [ ] `uv run pytest -q` passes locally (baseline)
- [ ] A laptop SSH key already loaded (`ssh-add -l` lists it)
- [ ] This file + `docs/zgx_notes.md` open in split pane for reference

## Step 1 — Spin up instance

1. Log in to Enverge. Note: we want a **DGX Spark (GB10)** box, not a
   Hopper/Blackwell data-center SKU.
2. Launch the instance with the default DGX OS image.
3. Once running, record the public IP here: `ENVERGE_IP=___`
4. `ssh user@$ENVERGE_IP` — confirm login works.
5. On the instance: `nvidia-smi` — confirm GB10 visible, memory free.

**Pass:** `nvidia-smi` shows one GB10 device with ~128 GB unified memory.
**Fail cases:** if the instance shows H100/H200/GB200 instead, that's not
DGX Spark — tear it down and re-launch with the correct SKU.

## Step 2 — Baseline recon

From the laptop:
```bash
uv run hack recon user@$ENVERGE_IP
cat runs/recon-latest.json
```

Write the preinstalled NIM container names from `recon-latest.json` into
`PREP_TODO.md §Open questions` — this answers "which exact NIM containers
ship on DGX OS by default?"

**Pass:** `runs/recon-latest.json` written; `nvidia-smi`, `docker ps`,
`ollama list`, disk-free all populated.

## Step 3 — Ship the repo

```bash
rsync -av --exclude .venv --exclude runs --exclude __pycache__ ./ user@$ENVERGE_IP:~/hackaton/
```

Alternative: clone from GitHub if the instance has internet and your
commits are pushed. `rsync` is faster and doesn't require pushing WIP.

## Step 4 — Bootstrap the ZGX (this is the point)

On the instance:
```bash
cd ~/hackaton
bash scripts/bootstrap_zgx.sh --role primary
```

**Watch for:**
- Does NIM pull Nemotron cleanly, or does it wedge? (Expected: NVIDIA's
  default containers load; if not, note the error text.)
- Does Ollama fallback engage when NIM fails?
- Any prompts for credentials / EULA acceptance? (If so, document — we
  can't hit those day-of under time pressure.)
- Disk usage after pulls — flag in `zgx_notes.md` if >200 GB.

**Pass:** `bootstrap_zgx.sh` exits 0; `docker ps` shows the NIM container
(or `ollama list` shows `qwen2.5:14b-instruct`); no manual prompts left.

## Step 5 — Verify serving endpoint

From the laptop:
```bash
uv run hack serve status --host $ENVERGE_IP
```

**Pass:** all rows green. If red, diagnose on the instance with
`docker logs <container>` or `journalctl -u ollama`.

## Step 6 — Warmup + measure first-token latency

```bash
uv run hack serve warmup --host $ENVERGE_IP
```

Record the first-token time here: `WARMUP_MS=___`. Target: **<2 000 ms**
for NIM; <3 000 ms for Ollama qwen2.5:14b.

## Step 7 — Full end-to-end agent loop

Edit a copy of `configs/agent.yaml` on the instance to point at the local
serving endpoints (`localhost:8000` or `localhost:11434`). Then:

```bash
uv run hack agent run --robot mock --config configs/agent.yaml
# Ctrl-C after ~30 seconds
```

Or if a mic is attached (it won't be, on a cloud box), use `hack rehearse`
with the `live` scenario and a scripted cue.

**Pass:** `runs/rehearsal-live-*.jsonl` contains `observation`, `plan`,
`action` events; no parse failures; tick latency recorded.

## Step 8 — Record numbers

Append one row to `docs/REHEARSALS.md`:

```
| <date> | enverge-gb10 | live / mock-robot | <llm-model> / <vlm-model> | PASS/FAIL | <tick_ms> ms | insight | action |
```

And update `docs/zgx_notes.md` with any surprise — unexpected container
names, hidden EULA gates, disk pressure, latency offsets vs Mac baseline.

## Step 9 — Tear down

**Don't forget this step** — billing continues while the instance runs.

1. Terminate the Enverge instance from their console.
2. Confirm it shows "terminated" in your dashboard.
3. Record total cost here: `COST_USD=___`.

## After the dry-run

- Check `PREP_TODO.md` §6 (DGX-class rehearsal) → tick everything that
  passed; leave blockers as open with a note.
- If bootstrap failed on a specific step, file it as a top-priority item
  for the week — this is the only chance to fix it before the event.
- If latency was much worse than Mac baseline (unlikely — GB10 should be
  faster), investigate before writing off the Enverge-specific config.

## Stretch (only if everything above passed with time to spare)

- Clone `NVIDIA/dgx-spark-playbooks` and run the
  [`spark-reachy-photo-booth`](https://github.com/NVIDIA/dgx-spark-playbooks/tree/main/nvidia/spark-reachy-photo-booth)
  docker-compose once. This is the reference stack NVIDIA ships for the
  exact hardware pair — if it runs here, it will run at the event.
- Test `configs/agent.yaml` `base_urls` failover by stopping the NIM
  container mid-run and verifying the adapter rotates to Ollama (if both
  are serving). Validates the `_HostPool._request` retry logic on real
  network conditions.

## Rollback / cut-list

If Enverge access doesn't work or GB10 instances aren't available:
- **Substitute:** rent a Lambda GH200 (~$3.19/hr, ARM64 Grace+Hopper) — not
  exactly GB10 but same ISA and CUDA/NIM ARM image path. ~$6.40 for 2 hrs.
  [lambda.ai/nvidia-gh200](https://lambda.ai/nvidia-gh200)
- **Do NOT** fall back to x86 H100/H200 — NIM ships ARM-specific containers
  and you'd exercise the wrong image set.
