---
name: robot-adapter
description: Implement a new RobotAdapter from a given SDK. Use when wiring up a real robot, adding a new adapter (e.g., "add adapter for X"), or mapping an unknown robot API onto the hack runtime.
---

# Implementing a new RobotAdapter

The runtime only calls six methods — map the robot's SDK onto those and stop.

**Before writing code:** check `docs/DAY_OF_DECISIONS.md` §1 — it already maps the intake's "transport" answer to a specific adapter (ROS2 / HTTP / LeRobot / custom). Don't re-derive the choice. Every `# DAYOF: R` marker in the chosen file is a spot you're expected to edit.

## Steps

1. **Read the SDK's hello-world sample first.** Note: connection handshake, teardown, coordinate frames, units (m vs cm, rad vs deg), and blocking vs async.
2. **Create** `src/hack/robot/<name>.py` subclassing `RobotAdapter` from `src/hack/robot/base.py`.
3. **Map the six methods.** If the SDK has no analogue for one, raise `NotImplementedError` with a clear message — the planner will route around it.
   - `move(dx, dy, dtheta)` — body-frame translation + yaw.
   - `grasp()` / `release()` — gripper; no-op if no gripper.
   - `set_joint(name, value)` — named joint target.
   - `get_state()` — return `RobotState` pydantic model.
   - `emote(label)` — LEDs/sounds/poses; no-op is fine.
4. **Register** in `src/hack/robot/__init__.py` adapter factory (`ADAPTERS["<name>"] = <Class>`).
5. **Add teardown** in `__aexit__` — the runtime relies on clean shutdown.
6. **Smoke test:** `hack robot probe --adapter <name>` cycles every method with safe small values. Commit only after it passes.
7. **If the SDK blocks:** wrap calls in `asyncio.to_thread`. Never block the event loop.

## Common pitfalls

- Units silently differ (mm vs m). Log the first command's pre/post state.
- Some robots reject commands until homed/calibrated — expose `home()` as an extra method and call it in `__aenter__`.
- ROS2 adapters: launch the rclpy executor in a thread; the runtime is asyncio.
