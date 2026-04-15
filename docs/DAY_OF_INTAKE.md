# Day-of intake — fill during the 30-min intro

One person types here live while all three listen. Replace every `...` with a fact (or `N/A`). Aim to finish by T+0:25. Don't worry about formatting — just type.

---

## 1. Challenge summary

One-sentence goal: ...

What wins the scoring (in your own words): ...

Stretch bonus if any: ...

---

## 2. Scoring specifics

Performance (hardware utilization) — what it means for this challenge, any gotchas:
...

Sensor / input integration — what it means for this challenge, any gotchas:
...

Agent quality (responsiveness, coherence) — what it means for this challenge, any gotchas:
...

Time-weighted component? ... (yes/no)

Submission format: ...

---

## 3. Robot

Model / name: ...

Morphology (mobile base / arm / quadruped / humanoid / other): ...

Degrees of freedom or joints (names if known): ...

SDK language: ... (Python / C++ / other)

Transport: ... (ROS2 / HTTP / Python package / serial / LeRobot driver `<name>` / other)

Docs link or on-device README path: ...

Coordinate frame and units: ... (e.g. body-frame XY in metres, yaw in radians)

Homing required before motion? ... (no, or: "yes, call `X`")

Kill-switch procedure: ...

Known safety limits (max speed, torque, workspace): ...

---

## 4. Robot sensors

List every sensor the robot exposes and who owns the stream. One line each.

- RGB camera(s): ... (count, FOV, resolution, fps — or `none`)
- Depth / stereo: ...
- Microphone: ...
- Force / torque: ...
- IMU: ...
- Tactile: ...
- Joint encoders: ...

Camera stream owner: ... (robot SDK / host USB / both)

---

## 5. Network topology

- ZGX A IP: ...
- ZGX B IP: ...
- Robot IP + ports: ...
- Laptops on same VLAN as ZGX/robot? ...
- Internet access during build? ... (yes / no / partial — describe)
- Preinstalled mDNS / hostnames we can use: ...

---

## 6. Software preinstalled on ZGX

> **Auto-filled by `uv run hack recon user@<zgx-ip>` — machine recon wins over anything hand-written here.** Only fill manually if `hack recon` can't reach the machine. Run recon against both ZGXs; the latest result is the authority.

- `nvidia-smi` output (first line): ...
- `docker ps` running containers (names + ports): ...
- NIM containers present: ...
- LeRobot driver for our robot? ... (yes = class path / no)  ← this one stays human (recon can't tell)
- `nat` (NeMo Agent Toolkit) on PATH? ...
- Ollama already running? ...
- Disk free on `/`: ...

---

## 7. Constraints

- Build window clock times (start / end): ... / ...
- Checkpoints judges will do mid-build: ...
- Mandatory submission format (PR, zip, URL): ...
- Judges present during demo? ...
- Can we speak to judges during demo? ...
- Any forbidden techniques, models, or cloud use: ...

---

## 8. One committed primary behaviour

Write a single sentence describing the minimum demo we will ship. Nothing else is guaranteed.

> Primary behaviour: ...

Delete these examples after you write yours:
- "Pick up a red block on voice command and drop it in the bin."
- "Follow a person around the room and describe what they do."
- "Respond to three voice commands with coherent arm gestures."

---

## 9. Stretch behaviours (priority order)

1. ...
2. ...
3. ...

---

## 10. Cut-list order

Rank features from first-to-drop to never-drop.

1. ... (drop first)
2. ...
3. ...
4. ... (never cut)

---

## 11. Role assignment (final, sticky)

- Robot lead (R): ...
- Brain lead (B): ...
- Demo lead (D): ...

Candidates: Timur, Kamila, Simon.

---

## 12. Open questions for organisers

- ...
- ...

---

Once filled, run `uv run hack intake` and then walk `docs/DAY_OF_DECISIONS.md` top to bottom with all three teammates.
