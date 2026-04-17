---
name: watch-rehearsal
description: Automatically monitor rehearsal logs when the user is testing with the TUI or running any rehearsal. Triggers on "run rehearsal", "test it", "try it", "started tui", "testing", or any variant. Also triggers when the user mentions they are using hack tui in another terminal/pane.
---

# Watch rehearsal logs

When a rehearsal is running — whether started by Claude, by the user via `hack tui` (Ctrl+R), or by `hack rehearse` in another pane — always arm a log watcher immediately without being asked.

## When to trigger

- User says "run rehearsal", "test it", "try it", "started tui", "I'm testing"
- User mentions they have `hack tui` open in another Kitty pane/window
- User presses Ctrl+R in the TUI (you won't see it directly, but the trace file will appear)
- Any new `runs/rehearsal-*.jsonl` file appears
- After any code/config change that might affect rehearsal behaviour

## Steps

1. **Ensure watch script exists:**
   ```bash
   test -f /tmp/hack_watch.py || cat > /tmp/hack_watch.py << 'PY'
   import json, sys
   for line in sys.stdin:
       try: e = json.loads(line)
       except: continue
       k = e.get("kind"); t = e.get("tick",""); tag = f"t{t:>2}" if t!="" else "   "
       if k == "live_cue":
           print(f"{tag} MIC  {e['text']!r}", flush=True)
       elif k == "scripted_cue":
           print(f"{tag} CUE  {e['text']!r}", flush=True)
       elif k == "plan_installed":
           print(f"{tag} INSTALL {len(e.get('steps',[]))} steps", flush=True)
       elif k == "plan_progress":
           print(f"{tag} PROG {e['step_index']}/{e['total']}", flush=True)
       elif k == "plan_complete":
           print(f"{tag} COMPLETE", flush=True)
       elif k == "action":
           c = e.get("call",{}); src = e.get("source","llm")
           ok = "OK" if e.get("result",{}).get("ok") else "ERR"
           print(f"{tag} ACT  [{src}] {ok} {c.get('name')} {c.get('args')}", flush=True)
       elif k == "alert":
           print(f"{tag} ALERT [{e.get('code')}] {e.get('message','')[:80]}", flush=True)
       elif k == "status" and e.get("state") in ("vlm_done","planner_done"):
           print(f"{tag} {e['state']} {e.get('ms')}ms", flush=True)
       elif k == "stop":
           print(f"     STOP success={e.get('success')} reason={e.get('reason')}", flush=True)
   PY
   ```

2. **Arm a Monitor** tailing the latest trace:
   ```bash
   sleep 2 && F=$(ls -t runs/rehearsal-*.jsonl | head -1) && tail -n 0 -F "$F" | python3 -u /tmp/hack_watch.py
   ```
   Use `timeout_ms=900000` (15 min) and `persistent=false`.

3. **Report events inline** as they arrive — especially:
   - MIC cues (what the user typed in TUI)
   - Plan installations (how many steps, deterministic vs LLM)
   - Actions (pre-baked vs LLM, success/error)
   - Alerts (obstacle-detected, safety-clamp, cue-decompose-failed)
   - STOP result (pass/fail + reason)

4. **After STOP or timeout**, check:
   - `tail -5 /tmp/rehearsal_stderr.log` for errors
   - `cat runs/issues.ndjson | tail -5` for correctness monitor findings
   - Latest `runs/rehearsal-*.json` summary for metrics

5. **Proactive analysis:** When you see issues in the logs:
   - Sign flips → suggest decomposer prompt fix
   - Collisions → suggest obstacle layout or dodge geometry change
   - cue-decompose-failed → check if the cue should be a new deterministic case
   - Plan rejected → check validator prompt or step coverage rules
   Don't wait to be asked — flag issues as they happen.

## When NOT to use

- When the user explicitly says "don't watch logs" or "I'll handle it"
- When replaying an old trace with `hack tui --no-follow` (read-only, no live action)

## Multiple TUI sessions

The user may restart the TUI or press Ctrl+R multiple times. Each restart creates a new trace file. If your monitor stops receiving events but the user is still testing, re-arm with the newest trace:
```bash
F=$(ls -t runs/rehearsal-*.jsonl | head -1) && tail -n 0 -F "$F" | python3 -u /tmp/hack_watch.py
```
