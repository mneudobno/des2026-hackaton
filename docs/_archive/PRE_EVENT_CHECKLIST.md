# Pre-event checklist — DIS2026X1, 2026-05-08

Consolidated action list with explicit completion signals. Event is **2026-05-08**.
Today's date at the time this file was written: **2026-04-18** — **20 days out**.

Related files: [`PREP_TODO.md`](./PREP_TODO.md) (comprehensive tracker),
[`day_of_playbook.md`](./day_of_playbook.md) (strategy),
[`DEMO_SCRIPT.md`](./DEMO_SCRIPT.md) (60-sec narration),
[`DAY_OF_INTAKE.md`](./DAY_OF_INTAKE.md) / [`DAY_OF_DECISIONS.md`](./DAY_OF_DECISIONS.md) / [`DAY_OF_TASKS.md`](./DAY_OF_TASKS.md) (tactical).

Legend: ✅ done · 🟡 in-flight · ⬜ todo · ⏳ blocked

---

## T–20 → T–14 days (this week)

| Status | Action | Command / file | Completion signal |
|---|---|---|---|
| 🟡 | Pull qwen2.5 models on all three laptops | `ollama pull qwen2.5:7b && ollama pull qwen2.5vl:7b` | `ollama list` shows both |
| ⬜ | Pull phi3:mini (intent router) | `ollama pull phi3:mini` | `ollama list` includes `phi3:mini` |
| ⬜ | Teammate onboarding (Kamila + Simon) | `docs/ONBOARDING.md` | All three run `uv run hack doctor` green |
| ⬜ | Email organizers: USB / Docker / pre-pulled models policy | mail | Written reply pasted into `PREP_TODO.md` §Open questions |
| ⬜ | Email organizers: robot type + network setup at each team station | mail | Written reply pasted into `PREP_TODO.md` |
| ⬜ | Confirm event seat + travel for all three | — | "CONFIRMED" in team channel |

## T–13 → T–7 days

| Status | Action | Command / file | Completion signal |
|---|---|---|---|
| ⬜ | DGX-class rehearsal on rented GPU (Lambda / RunPod, ~1 hr) | `scripts/bootstrap_zgx.sh --role primary` on rented host; `uv run hack serve status --host <ip>`; one full agent run | Latency measurement logged in `docs/REHEARSALS.md` |
| ⬜ | Rehearse with real mic + webcam end-to-end | `uv run hack rehearse --scenario obstacle-corridor --display` × 3 | `runs/rehearsal-*.json` success=True on all three |
| ⬜ | Verify Chrome browser MCP loads `http://localhost:<port>` for TUI side-views | `uv run hack ui` | Dashboard visible + SSE streaming |
| ⬜ | Verify demo replay works offline (Ethernet unplugged) | `uv run hack agent replay runs/<any-rehearsal>.jsonl` | Replay produces `plan` + `action` events identical to source |
| ⬜ | Record a clean 60-sec demo take on laptop | QuickTime / OBS + narrate `DEMO_SCRIPT.md` | Clip saved under `docs/takes/` |

## T–6 → T–2 days (final week)

| Status | Action | Command / file | Completion signal |
|---|---|---|---|
| ⬜ | All three on same commit | `git pull && uv sync && uv run hack doctor` | Green on all three |
| ⬜ | Print day-of materials (2 copies each) | `day_of_playbook.md`, `DAY_OF_TASKS.md`, `zgx_notes.md`, `DEMO_SCRIPT.md` | Printed pages in go-bag |
| ⬜ | Pack go-bag | See §Pack list below | All items crossed off |
| ⬜ | Run the regression suite | `uv run hack regression` | PASS |
| ⬜ | Run the 30-scenario pytest | `uv run pytest tests/test_all_scenarios.py -q` | 30 passed |
| ⬜ | Run the full pytest | `uv run pytest -q` | 107 passed (or whatever the latest count is after this week's additions) |
| ⬜ | Read the top-3 robot adapter files one more time | `src/hack/robot/reachy_mini.py`, `unitree_go2.py`, `http.py` | Each teammate can point to the 6 methods in each |

## T–1 day (2026-05-07, evening in Stockholm)

| Status | Action | Command / file | Completion signal |
|---|---|---|---|
| ⬜ | Walk to the venue (Kistamässan) — scout parking/entry | — | Known path |
| ⬜ | Hotel wifi test: pull a small model on laptop from Ollama | `ollama pull phi3:mini` | Completes under 5 min |
| ⬜ | Latest `git pull` + `uv sync` + `hack doctor` | — | Green on all three |
| ⬜ | Charge all batteries (laptop, phone, backup) | — | 100% |
| ⬜ | Sleep | — | >= 7 hours |

## Day-of (2026-05-08) — event-time checklist

**Until 10:20** (before main-stage assembly):

| Status | Action | Command / file | Completion signal |
|---|---|---|---|
| ⬜ | All three at venue with go-bag | — | Inside Kistamässan |
| ⬜ | Approach main stage **P1** for seat assignment (organizer email: 10 min before 10:30) | — | Seated by 10:30 |
| ⬜ | `hack doctor` on all three laptops | `uv run hack doctor` | Green |
| ⬜ | Recon both ZGX boxes once IPs are handed out | `uv run hack recon user@<zgx-a>`, `uv run hack recon user@<zgx-b>` | `runs/recon-latest.json` written |
| ⬜ | Confirm network reach from laptop (vLLM endpoint, default :8000) | `curl http://<zgx-a>:8000/v1/models`, `curl http://<zgx-b>:8000/v1/models` | 200 OK with Nemotron / Qwen listed |
| ⬜ | Warm up models on both ZGX boxes | `uv run hack serve warmup` on each | First token < 2 s |
| ⬜ | Dashboard + TUI boot green | `uv run hack ui`, `uv run hack tui` | Both render |

**10:30–10:50** (kickoff + challenge briefing & technical setup — all three listen, typist fills `DAY_OF_BRIEF.md`):

| Status | Action | Command / file | Completion signal |
|---|---|---|---|
| ⬜ | Type free-form intro notes into `DAY_OF_BRIEF.md` | — | Notes captured by 10:45 |
| ⬜ | Say *"process the brief"* → Claude runs `day-of-brief` skill | — | Missing-facts list + config edits + first three tasks per role produced |
| ⬜ | Run `uv run hack intake` (cross-check vs recon) | — | Prints recon summary + DAYOF punch-list |

**10:50–13:00** (~2h10min build). Follow `DAY_OF_TASKS.md` minute-by-minute.
Critical beats:

| T+ | Status | Deliverable |
|---|---|---|
| 0:15 | ⬜ | Robot SDK chosen; config updated; adapter class chosen (reachy_mini / unitree_go2 / http / new) |
| 0:30 | ⬜ | `hack robot probe --adapter <name>` green |
| 0:45 | ⬜ | First end-to-end run: mic → VLM → planner → action. Latency measured. |
| 1:00 | ⬜ | Real robot performing the challenge behaviour. Latency < 2s per tick. |
| 1:15 | ⬜ | Prompt locked; adapter stable. Demo lead starts capturing takes. |
| 1:30 | ⬜ | **Cut-list decision point** — drop audio / TTS / second ZGX / live robot (in that order) if behind. |
| 1:45 | ⬜ | Final clean demo take recorded. |
| 1:55 | ⬜ | `git tag submit`; final trace saved to `runs/submit.jsonl`. |
| 2:00 | ⬜ | Submit. |

**13:00 — submission deadline** · **14:00 — jury deliberation & stage assembly** · **14:10 — winner announcement & showcase**

| Status | Action | Command / file | Completion signal |
|---|---|---|---|
| ⬜ | Hand-off sheet at station | `DEMO_SCRIPT.md` §Hand-off sheet | Printed + at station |
| ⬜ | Live narration per `DEMO_SCRIPT.md` | — | 60-sec run delivered |

---

## Pack list (in go-bag)

**Hardware:**
- Laptop + charger (USB-C 100 W minimum)
- Ethernet adapter (USB-C → RJ45)
- 2 × USB-C cables, 1 × USB-A
- USB-C hub (at least one HDMI + Ethernet)
- USB drive, 64 GB+, with: latest repo snapshot, pre-pulled model blobs (if organizers allow), printed copies of the key docs
- Phones, all three, fully charged (video backup)
- Earbuds (mic test in loud venue)
- Optional: portable Ethernet switch (5-port) — cheaper than a failed DHCP

**Printed:**
- `docs/day_of_playbook.md`
- `docs/DAY_OF_TASKS.md`
- `docs/zgx_notes.md`
- `docs/DEMO_SCRIPT.md`
- This file

**Soft:**
- One clean rehearsal JSONL on the USB drive (fallback demo if live run fails)
- A 60-sec recorded demo take (video) as absolute last-resort fallback

---

## Gap analysis — what is NOT ready yet (as of 2026-04-18)

Ordered by day-of risk:

| Risk | Gap | Plan |
|---|---|---|
| High | DGX-class rehearsal not done — we've never hit a real GB10 | Rent Lambda/RunPod this weekend; 1 hr burn |
| High | Teammate onboarding incomplete (Kamila + Simon) | 30-min screen share this week; each runs `hack doctor` on their own machine |
| Medium | Live-voice rehearsal with real mic + Whisper in loud room | Run `hack rehearse` with earbuds + fan noise at least 3× before leaving |
| Medium | Physical robot has never been tested — all rehearsals are `virtual` adapter | Not fixable until the event (SDK unknown). Mitigation: `reachy_mini` + `unitree_go2` adapter stubs are shape-correct; adapter swap should be < 30 min if hardware matches our top-2 predictions |
| Low | `phi3:mini` intent router not wired into runtime | Day-of decision: enable via config only if judge-facing challenge is conversational. Current code path works either way |
| Low | Unit tests for `PlanMemory` not added | Write this week — low risk since we have 30 scenario tests exercising it |
| Low | `docs/REHEARSALS.md` hasn't been updated recently | Append after each rehearsal this week |

---

## Contact tree (if something goes wrong pre-event)

- **Organizer** — [CONTACT: fill from confirmation email]
- **Hyperight support** — [CONTACT: fill from event page]
- **Pollen Robotics (if Reachy Mini)** — GitHub issues on reachy_mini repo
- **NVIDIA** — NGC support, DGX OS forum
- **Team channel** — [Slack/Signal/etc link]
