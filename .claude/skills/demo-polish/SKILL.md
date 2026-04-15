---
name: demo-polish
description: Prepare the final judged submission — clean run capture, dashboard screenshots, 60-second narration. Use in the last 20 minutes of the hackathon.
---

# Final demo prep

Judges see: one live run + one backup recording + a 60-second narrated summary. Assume the live run might fail.

## Steps

1. **Freeze code.** Create `submit` branch. No more changes except `configs/agent.yaml` and `docs/`.
2. **Record a clean run:** `hack demo record --out runs/submit.jsonl --video runs/submit.mp4`. Do this 2–3 times; keep the best.
3. **Screenshots:** open `hack ui`, screenshot (a) dashboard mid-run, (b) robot executing, (c) transcript panel. Save to `docs/submit/`.
4. **60-second narration** in `docs/submit/narration.md`:
   - 10s: what the agent does (one sentence)
   - 20s: how it uses vision + audio
   - 20s: one surprising behavior you're proud of
   - 10s: what it runs on (ZGX Nano, local, models listed)
5. **Backup:** `hack demo play runs/submit.jsonl` must work offline. Test it with the network cable unplugged.
6. **Judge handoff:** print a one-page sheet with: team name, what to watch for, how to trigger behaviors, fallback command.

## Cut-list (apply ruthlessly if time < 20 min)

- Drop TTS if it stutters — transcript on screen reads fine.
- Drop audio input if STT is flaky — text input via dashboard works.
- Drop the live run; show the recorded one and the replay.
- Never drop the dashboard — it is how judges see the system's intelligence.
