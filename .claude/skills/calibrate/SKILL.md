---
name: calibrate
description: Conversationally calibrate the robot's physical and safety parameters from real measurements. Walks the user through every knob in `robot.calibration` + `robot.safety`, computes scale factors from observed motions, captures footprint/clearance from a tape measure, derives planner geometry, and writes results to `configs/agent.local.yaml`. Trigger on "calibrate the robot", "calibration", "tune the robot", "/calibrate", "robot drifts", "robot under/overshoots", "set up calibration", "the robot doesn't move 1m when I say 1m", or any time the user is configuring a freshly-revealed physical robot (day-of, after `hack recon` and after `robot-adapter` has been wired). Two surfaces already exist — `hack calibrate` (CLI, motion scale only) and TUI Ctrl+L (live nudge); this skill is the conversational orchestrator that uses both and covers everything else.
---

# /calibrate — guided robot calibration

The runtime never reads physical robot constants directly. Every value lives in
`configs/agent.yaml` under `robot.safety` and `robot.calibration`. Your job is
to populate those values from actual measurements (motion experiments + tape
measure + datasheet) and write the result to `configs/agent.local.yaml`
(gitignored override; same path the TUI uses).

## Preconditions

Before starting, verify in this order. Stop and ask the user if any are missing:

1. **A robot adapter is in use.** Read `configs/agent.yaml` `robot.adapter`. If
   it's still `mock` and the user is calibrating for a *real* robot, ask them
   to invoke the `robot-adapter` skill first — calibration without the real
   adapter only tunes the simulator.
2. **The robot is powered, connected, and homed.** Run
   `uv run hack robot probe --adapter <name>` (read its output) — if any
   command fails the robot isn't ready and calibration will produce garbage.
3. **A measured workspace.** Tape on the floor (or a known-distance reference)
   for linear scale. Compass / phone protractor for angular scale. Tape measure
   for body footprint.
4. **Datasheet** if available — saves measurement work for `max_linear_speed`,
   `max_angular_speed`, joint limits.

## What to calibrate (the canonical 10 knobs)

Two blocks in the YAML, ten values total. Pull current values by reading
`configs/agent.yaml` (and `configs/agent.local.yaml` if it exists — the local
file overrides):

```yaml
robot:
  safety:
    max_linear_speed:    # m/s, per-tick cap
    max_angular_speed:   # rad/s, per-tick cap
  calibration:
    linear_scale:        # 1.0 = perfect; 1.18 = robot undershoots by ~15%
    angular_scale:       # same
    prefer_forward_walk: # bool — true for legged robots that can't strafe
    robot_radius:        # m, widest body half-width including gripper
    extra_clearance:     # m, safety margin added by A* around obstacles
    planner_cell_size:   # m, A* grid resolution; should be <= robot_radius
    reactive_dodge_m:    # m, sidestep size when obstacle appears ahead
    reactive_advance_m:  # m, forward recovery after dodging
```

`DEFAULT_SAFETY` in `src/hack/agent/plan_memory.py` mirrors the safety block;
it is the *only* fallback site. The TUI's `CalibrationScreen.PARAMS`
(`src/hack/ui/tui_app.py`) and `hack calibrate` (`src/hack/cli.py`) cover
subsets of these — this skill is the union.

## Procedure

Walk the user through these in order. **Ask before each motion test** — the
robot may need clearing of the area first. After each measurement, compute
the value and show it; do not write to disk yet.

### 1. Detect adapter, load current values

```bash
# Read both files; local overrides base.
cat configs/agent.yaml | yq '.robot'
test -f configs/agent.local.yaml && cat configs/agent.local.yaml | yq '.robot' || echo "(no local override yet)"
```

Tell the user the current adapter and which knobs already have non-default
values. Skip knobs they're happy with.

### 2. `linear_scale` — motion test

Reuse `hack calibrate` interactively *if* the user wants to type into the
terminal directly. Otherwise script it:

> "Place the robot at a known start line. I'll tell you what to send; you tell
> me how far it actually went."

1. Suggest: `n=3` steps of `dx=0.2 m` → expected total **0.6 m forward**.
2. Either:
   - User runs `uv run hack calibrate --adapter <name> --steps 3` and pastes the result, OR
   - User sends the motions themselves (TUI test buttons / direct adapter call) and reports the measured distance.
3. Compute `linear_scale = expected_distance / measured_distance`.
4. Sanity check: if `linear_scale` is outside `[0.5, 2.0]`, something else is
   wrong (units? reference frame?) — investigate before continuing.

### 3. `angular_scale` — rotation test

Same pattern, rotational:

1. Suggest: `n=3` steps of `dtheta=0.6 rad` → expected **≈103°** counter-clockwise.
2. User reports measured rotation in degrees (use phone compass or two reference marks).
3. Compute `angular_scale = expected_deg / measured_deg`.
4. Sanity check: same `[0.5, 2.0]` bound. If the robot turns the *opposite*
   direction, it's a sign convention issue, not a scale — note it for the
   adapter, do not paper over with a negative scale.

### 4. `prefer_forward_walk` — kinematic capability

Boolean, no measurement. Ask the user:

> "Can the robot strafe sideways (move along body-frame Y without turning)?"

- Most legged robots: **no** → `prefer_forward_walk: true` (return-to-origin
  emits turn → walk → turn).
- Wheeled / omnidirectional / mock: **yes** → `prefer_forward_walk: false`.

### 5. `max_linear_speed` and `max_angular_speed` — per-tick safety caps

Two ways:

- **From datasheet:** Robot's max forward speed in m/s and max yaw rate in rad/s.
  Multiply by `1 / agent.tick_hz` (default 5) to get the per-tick cap.
  E.g. 4.5 m/s × (1/5) = 0.9 m/tick. Use these as the YAML values.
- **By observation:** Send progressively larger `move(dx=...)` until motion
  becomes unsafe / juddery / the robot complains. Use 80% of that as the cap.

If the user has no datasheet and isn't comfortable observing under load, leave
the current `0.9` / `1.8` (snappy rehearsal defaults) and document the gap.

### 6. `robot_radius` — physical footprint

Pure tape-measure. Ask:

> "Measure from the centre of the robot's body to the widest external point
> (gripper extended if it can stick out during motion). In metres."

Common values: small wheeled (0.05–0.10 m), Reachy / small humanoid (0.10–0.20 m),
adult-sized humanoid (0.30–0.40 m).

### 7. `extra_clearance` — safety margin

Ask: "How much padding should A* add around obstacles, beyond the robot
radius?" Pragmatic default `0.03 m` for small robots, `0.10 m` for fast or
imprecise ones. Higher = safer but more "no path found" cases.

### 8. `planner_cell_size` — A* grid resolution

**Derived:** `≤ robot_radius`. Smaller = more accurate path but slower
search. Recommendation: `min(robot_radius, 0.05)`. Don't go below `0.02 m` —
the grid blows up.

### 9. `reactive_dodge_m` and `reactive_advance_m` — reactive avoidance

**Derived:** these scale with footprint.

- `reactive_dodge_m ≈ 2 × robot_radius` (sidestep is at least one body width)
- `reactive_advance_m ≈ 3 × robot_radius` (recovery distance forward)

Override only if the venue is very tight (smaller) or very open (larger).

### 10. Adapter-specific knobs (optional, only if relevant)

If `robot.adapter` is `reachy_mini` or `lerobot`, ask whether the team wants
to expose these (they're hardcoded in the adapter today):

- **Reachy Mini:** `gaze_scale` (head tilt per body-frame metre, default 0.4),
  antenna pose for the grasp emote (currently `±30°` literal).
- **LeRobot:** gripper open/close command values (currently `1.0`/`0.0` —
  may be wrong if the robot uses a different scale).

If the team wants these parametrized, propose a YAML key like
`robot.calibration.reachy.gaze_scale` and tell the user — don't make the
adapter edit silently. Out of scope for the standard skill flow.

## Writing the result

Confirm the proposed values with the user (show a diff vs current), then
write to `configs/agent.local.yaml` (NOT the base config — the local file is
gitignored and exactly mirrors the TUI's save target). Use the existing TUI
save pattern as the reference: `src/hack/ui/tui_app.py` `action_save`.

```python
# Pseudocode for the write — use yaml.safe_load + safe_dump.
import yaml
local_path = Path("configs/agent.local.yaml")
existing = yaml.safe_load(local_path.read_text()) if local_path.exists() else {}
robot = existing.setdefault("robot", {})
robot.setdefault("calibration", {}).update(new_calibration_values)
robot.setdefault("safety", {}).update(new_safety_values)
local_path.write_text(yaml.safe_dump(existing, sort_keys=False))
```

Keep `sort_keys=False` so the order matches the TUI's writes (cleaner diffs).

**Never write to `configs/agent.yaml` directly.** The base config is the
checked-in reference; the local file is per-machine.

## Verification

In order:

1. **Static:** print the merged effective config (`base + local`) so the user
   confirms what runtime will actually see.
2. **Regression gate:** `uv run hack regression`. Must remain 2/2. The
   `spin_360` checker is safety-aware (`expected_min = ceil(2π / max_angular_speed)`),
   so changing the angular cap automatically updates the floor.
3. **Smoke rehearsal:** `uv run hack rehearse --scenario obstacle-corridor` —
   exercises path planner, safety clamp, and reactive dodge in one shot.
   Expect `success: ✅` and zero collisions; if either fails, the geometry
   knobs are wrong.
4. **Append a row to `docs/REHEARSALS.md`** with insight ("calibration: N knobs
   tuned from measurements") and action ("written to `agent.local.yaml`").

## Common pitfalls

| Symptom | Likely cause | Fix |
|---|---|---|
| `linear_scale` > 2 or < 0.5 | Units mismatch (cm vs m, ft vs m) | Re-check the SDK's distance unit; the adapter should normalize to metres |
| Robot turns *opposite* direction | Sign convention in adapter, not scale | Fix in `src/hack/robot/<name>.py`'s `move()`; do NOT use a negative `angular_scale` |
| Robot oscillates around obstacles | `extra_clearance` too tight or `reactive_dodge_m` too small | Bump `extra_clearance` first by `0.02`; only increase `reactive_dodge_m` if A* still finds paths but reactive recovery overshoots |
| "no path found" everywhere | `extra_clearance + robot_radius` exceeds half the workspace | Reduce `extra_clearance`; check obstacles aren't placed inside walls |
| Regression `spin_360` fails after change | Stale: `_check_spin_360` reads `max_angular_speed` from the safety dict — if you wrote calibration but not safety, the old cap is still in effect | Make sure `max_angular_speed` was updated alongside `angular_scale` |
| Rehearsal collisions spike after change | `robot_radius` smaller than reality | Re-measure with a tape; physical robots rarely shrink |

## What to tell the user when done

Five lines:

1. Which knobs changed (key + old → new).
2. Where it landed (`configs/agent.local.yaml`).
3. Regression result (X/Y passed).
4. Smoke rehearsal result + collision count.
5. Next action (`Ctrl+R` in TUI to reload, or `uv run hack rehearse <scenario>`
   for a deeper test, or "ready for the judged run").

Never silently apply a calibration change if the regression or smoke rehearsal
fails. Roll back the local file (or revert to the previous values you read at
step 1) and report what went wrong.
