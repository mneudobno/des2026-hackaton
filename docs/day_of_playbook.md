# Day-of playbook — team "Just Build" @ DIS2026X1, 2026-05-08

> **This file is strategy** (roles, timing, cut-list). The **tactical** day-of files are:
> - [`DAY_OF_INTAKE.md`](./DAY_OF_INTAKE.md) — blank form filled during intro
> - [`DAY_OF_DECISIONS.md`](./DAY_OF_DECISIONS.md) — intake → repo choice matrix
> - [`DAY_OF_TASKS.md`](./DAY_OF_TASKS.md) — live task board (tick as you go)
>
> Run `uv run hack intake` after the challenge intro for a single-screen punch-list.

## Schedule (event-given)

| Time | Block |
|------|-------|
| 10:30–11:00 | Intro + challenge reveal |
| 11:00–13:00 | **2-hour build window** |
| 13:00–13:30 | Break / evaluation |
| 13:30–14:30 | Awards |

## Roles (team of 3)

Role assignments are TBD — decide during the first sync and fill in below:

- **Robot lead (R)** — _______ — implements the `RobotAdapter`. First task: read SDK sample, get `hack robot probe` green.
- **Brain lead (B)** — _______ — tunes prompts in `configs/agent.yaml`, runs `hack agent replay` loops.
- **Demo lead (D)** — _______ — runs the dashboard, captures clean takes, builds the 60-second narration. Also: utility/ops (kill flaky processes, restart serving, watch latency).

Candidates: **Timur**, **Kamila**, **Simon**. Roles are sticky once set — do not swap mid-build.

## Minute-by-minute

| T+ | All / R / B / D |
|----|-----------------|
| 0:00 | All: `hack doctor` on laptop and both ZGX boxes. Fix red rows. |
| 0:05 | All: read challenge brief together. 5-min silent read, 5-min discuss. Pick *one* primary behavior to nail. |
| 0:15 | R: `bash scripts/bootstrap_zgx.sh --role primary` on box A, `--role secondary` on B. Then read robot SDK sample. B: open `configs/agent.yaml`, sketch system prompt for the chosen behavior. D: open dashboard, set up screen recording. |
| 0:30 | R: first cut of `src/hack/robot/<name>.py`. Run `hack robot probe --adapter <name>`. |
| 0:45 | R: probe green; commit. B: `hack agent run --robot mock` end-to-end on laptop. |
| 1:00 | All: integrate — `hack agent run --robot <real>`. Watch dashboard. **Latency check.** |
| 1:15 | B: prompt iteration via `hack agent replay`. R: handle adapter edge cases (units, blocking calls). D: start capturing demo takes. |
| 1:30 | All: behavior must work end-to-end *now*. If not, invoke cut-list. |
| 1:45 | D: record 2–3 clean takes. B: lock prompts. R: do not change adapter. |
| 1:55 | All: freeze. `git tag submit`. Final demo capture. Print judge handoff sheet. |
| 2:00 | Submit. |

## Cut-list (apply ruthlessly)

| At | Cut |
|----|-----|
| 1:00 if behind | Drop audio input. Use dashboard text input. |
| 1:15 if behind | Drop TTS. Show transcript instead. |
| 1:30 if behind | Drop the second ZGX. Run everything on box A. |
| 1:45 if behind | Drop live robot. Demo MockRobot + recorded video of an earlier real run. |

## What never gets cut

- The dashboard. Judges see intelligence through it.
- JSONL logging. Demo replay depends on it.
- The single `RobotAdapter`. No parallel adapters mid-build.

## Pre-event checklist (1 week before)

- [ ] Rent a DGX Spark / A100 and run `bootstrap_zgx.sh` end-to-end. Note actual model pull times.
- [ ] Run `hack agent run --robot mock` on laptop with mic + webcam. Confirm <2s latency.
- [ ] Confirm `hack ui` works in Chrome/Firefox.
- [ ] Verify `hack demo play` works **with network unplugged**.
- [ ] Email organizers: can we bring USB drives with pre-pulled models? Pre-built Docker images?
- [ ] Pack: laptop + charger, Ethernet adapter, 2× USB-C cables, USB drive with models, printed `day_of_playbook.md` + `zgx_notes.md`.
- [ ] Sleep.

## Pre-event checklist (morning of)

- [ ] Pull latest from `main`. Run `hack doctor` locally — green.
- [ ] `git status` clean.
- [ ] Phone batteries full (for video backup).
- [ ] Coffee.
