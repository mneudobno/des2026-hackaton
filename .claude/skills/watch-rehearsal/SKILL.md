---
name: watch-rehearsal
description: Automatically monitor rehearsal logs when a rehearsal is running or about to start. Use when the user starts a rehearsal, says "run rehearsal", "test it", "try it", or any variant of launching a hack rehearse / hack tui session.
---

# Watch rehearsal logs

When a rehearsal is running (or being started), always arm a log watcher immediately without being asked.

## Steps

1. **Find the latest trace:** `ls -t runs/rehearsal-*.jsonl | head -1`
2. **Arm a Monitor** tailing that file with the watch script:
   ```
   tail -n 0 -F "$F" | python3 -u /tmp/hack_watch.py
   ```
   If `/tmp/hack_watch.py` doesn't exist, write it first (see below).
3. **Report events inline** as they arrive: MIC cues, plan installs, actions, alerts, STOP results.
4. **Check stderr** after the rehearsal completes: `tail -5 /tmp/rehearsal_stderr.log`
5. **Check issues:** `cat runs/issues.ndjson | tail -5` for correctness monitor findings.

## Watch script (`/tmp/hack_watch.py`)

If the file doesn't exist, create it:

```python
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
```

## When NOT to use

- When the user explicitly says "don't watch logs" or "I'll handle it".
- When replaying an old trace (not a live rehearsal).
