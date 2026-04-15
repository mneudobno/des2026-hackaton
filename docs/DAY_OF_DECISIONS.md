# Day-of decisions matrix

After `docs/DAY_OF_INTAKE.md` is filled, walk this top to bottom. Each section: intake answer → what we change in the repo. **No "it depends" entries** — if an answer doesn't match a row, use the default and note it in the intake's "Open questions".

The rule: each row is one commit. Intake facts go in the commit message. Debate kept under 5 minutes total.

## 1. Robot adapter

| Intake §3 "Transport" | Action | File to edit |
|---|---|---|
| ROS2 topics | Use `ROS2Robot`. Import `rclpy`, spin executor in a thread. Map `/cmd_vel`, `/gripper`, joint services. | `src/hack/robot/ros2.py` |
| HTTP / REST | Use `HTTPRobot`. Adjust `_post` route/body shape to match SDK. Add auth header if needed. | `src/hack/robot/http.py` |
| LeRobot driver available | Use `LeRobotAdapter`. Pass `robot_class="lerobot.robots.<driver>.<Class>"` plus config dict. | `src/hack/robot/lerobot_adapter.py` |
| Python package (non-LeRobot) | Subclass `RobotAdapter` directly in `src/hack/robot/<name>.py`. Register in `ADAPTERS`. Budget: 30 min. | new file |
| Serial / USB raw | Wrap the serial commands in an async adapter. Budget: 45 min; consider dropping in favour of MockRobot + scripted demo. | new file |

Then: `configs/agent.yaml` → `robot.adapter:` set to the chosen name. Run `uv run hack robot probe --adapter <name>` → must be green before next decision.

> All "Intake §6" references below read from `runs/recon-latest.json` (machine-authoritative) if present, falling back to what was hand-typed. `hack intake` prints the effective values on top.

## 2. LLM (planner)

| Intake §6 "Software preinstalled" | Action | File to edit |
|---|---|---|
| NIM containers include Nemotron | `llm.provider: openai-compat`, `model: nvidia/Nemotron-3-Nano-30B-A3B`, `base_url: http://<zgx-a>:8000/v1` | `configs/agent.yaml` |
| NIM containers include generic OpenAI-compat | Same as above, substitute model + port from `docker ps` | `configs/agent.yaml` |
| No NIM, Ollama only | `llm.provider: ollama`, `model: qwen2.5:14b-instruct`, `base_url: http://<zgx-a>:11434`. Pull happens in `bootstrap_zgx.sh`. | `configs/agent.yaml` |
| Nothing installed (worst case) | Ollama fallback as above — our bootstrap pulls it | — |

## 3. VLM

| Intake §3 morphology + §4 cameras | Action | File to edit |
|---|---|---|
| Robot has usable camera AND NIM present | `vlm.model: nvidia/Nemotron-Nano-12B-v2-VL`, point at NIM endpoint. Camera source = robot feed (see §5 below). | `configs/agent.yaml` |
| Robot has camera, no NIM | `vlm.model: qwen2.5vl:7b`, Ollama. | `configs/agent.yaml` |
| Robot has no camera — host webcam watches the scene | Same as above; `sensors/camera.py` stays on device 0. | `configs/agent.yaml` |
| Vision is irrelevant to the task | Set `vlm.frame_fps: 0` to disable. Saves ~30% of runtime. | `configs/agent.yaml` |

## 4. Router (intent triage)

| Intake §1 goal includes… | Action |
|---|---|
| …conversation / dialogue | `router.enabled: true`, `shortcut_routes: [chit_chat]`. Saves planner calls on greetings. Requires `phi3:mini` pulled. |
| …pure action / no user voice | `router.enabled: false`. Every frame goes straight to the planner. |

## 5. Audio

| Intake §4 + scoring axis | STT | TTS |
|---|---|---|
| Audio-in is judged, NIM present | `nvidia/riva-parakeet-ctc-1.1B` via gRPC | `hexgrad/Kokoro-82M` |
| Audio-in is judged, no NIM | `faster-whisper large-v3-turbo` | `piper en_US-amy-medium` |
| Audio isn't judged | Disable both pipelines entirely — set `stt.provider: none`, `tts.provider: none`. Saves ~20% of planner round-trip and eliminates a failure mode. | |

## 6. Camera source

| Intake §4 "Who owns the camera stream" | Action |
|---|---|
| Robot SDK exposes camera | Add a method to the robot adapter that yields frames; swap `sensors/camera.py` import with a thin adapter that reads from the robot. Mark the camera device config `-1` ("robot-provided"). |
| Host captures via USB | Leave `sensors/camera.py` alone; set `device:` to whatever index works. |
| Both | Prefer robot-mounted for task relevance; keep host as a backup feed fed to the dashboard. |

## 7. Latency target

| Observed first-pass end-to-end latency (see §T+0:45 in `DAY_OF_TASKS.md`) | Action |
|---|---|
| ≤ 1.0 s | Do nothing. Ship. |
| 1.0–2.0 s | Drop VLM FPS from 2 → 1; enable tracker between VLM calls (`robot.tracker.enabled: true`). |
| 2.0–3.5 s | Also cap LLM `max_tokens` to 256; trim system prompt by 30%. |
| > 3.5 s | Swap planner model to a smaller variant (Qwen 7B → Qwen 3B, or Nemotron → Phi). Last resort: disable VLM entirely and rely on structured robot state only. |

## 8. Task-specific prompt profile

| Intake §8 primary behaviour | Starting prompts |
|---|---|
| Pick-and-place / manipulate objects | System prompt emphasises: identify target, approach, grasp, transport, release, verify. Observation prompt lists objects with spatial positions (left/right/near/far). |
| Follow / track a person | Emphasise: continuous motion, barge-in tolerance, don't lose the target. Use tracker module heavily. Route audio through the planner. |
| Conversational / assistant-like | Emphasise `speak` tool. Router on. Short observation prompt — we only need scene awareness occasionally. |
| Exploration / mapping | Emphasise `remember` tool; log observations to memory for later retrieval. Keep a growing scene summary. |

## 9. Dashboard / demo strategy

| Intake §7 "Judges present during demo" | Action |
|---|---|
| Yes, live | `hack ui` on a big screen. Rehearse the 60-second narration (`.claude/skills/demo-polish/SKILL.md`). Record in parallel as backup. |
| No — judges watch the recording | Focus on the recorded take. Still run `hack ui`, but for our own debugging, not the judges. |

## 10. Defaults when unsure

If the intake leaves any row blank, default to:

- MockRobot if the real robot isn't probing green by T+0:40.
- Qwen on Ollama if the NIM stack isn't responding by T+0:30.
- Router off (simpler).
- Audio pipelines off (fewer failure modes).
- VLM at 1 FPS, LLM max_tokens 256.

These defaults will not win anything, but they guarantee a working demo.

---

After this walkthrough: commit the edited `configs/agent.yaml` and any adapter stub. Open `docs/DAY_OF_TASKS.md` and start ticking.
