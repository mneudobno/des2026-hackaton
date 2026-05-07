# Day-of brief — raw notes from the challenge intro

**Purpose:** one person types into this file during the 30-minute challenge
intro while the other two listen. Write free-form, out of order, whatever
you hear. No structure required. Claude Code turns this into concrete repo
edits when you're done — trigger with: *"process the brief"*.

**Target: finish typing by T+0:25.** Then say *"process the brief"* and walk
away while Claude produces the missing-facts list + proposed config edits.

---

<!--
Hints for the typist (delete or ignore while writing — Claude reads around them):
- The challenge goal, in whatever words the presenter uses
- What scoring rewards: hardware utilization, sensor integration, agent quality
- Robot name, size, joints, what it can do, what it cannot, any safety limits
- Sensors on the robot: cameras (count, resolution), mics, force/IMU
- Network: how the robot connects, what IP / hostname, same VLAN as ZGX?
- Anything about the ZGX boxes: pre-installed containers, models, disk free
- Submission format, time limits, judge checkpoints, allowed/forbidden techniques
- Anything that made the presenter emphasise it with voice — copy that
-->

## Challenge

<!-- what are we building? why does it win? -->


## Robot

<!-- name, morphology, SDK, units, kill-switch, safety limits -->


## Sensors

<!-- cameras, mics, IMU, who owns each stream -->


## Network

<!-- ZGX A/B IPs, robot IP, internet access during build -->


## ZGX state

<!-- output of hack recon goes in runs/recon-latest.json — don't retype; just note surprises -->

**Pre-installed (organizer email 2026-05-05):** HP ZGX Toolkit, NVIDIA AI Enterprise stack, Nemotron, vLLM, llama.cpp, OpenCode.
**Models on-box:** NVIDIA Nemotron 3 Nano Omni (multimodal), Qwen 3.6 35B A3B (LLM).
**Open questions to verify at event:** exact HF/vLLM tag for each model, port (likely 8000), whether Omni's vision endpoint is on the same `/v1/chat/completions` route or a separate one.


## Scoring / submission

<!-- time-weighted? live demo? submission format? checkpoints? -->


## Constraints

<!-- forbidden techniques, forbidden models, forbidden cloud, time cuts -->


## Quotes and emphasis

<!-- anything the presenter said twice or in a louder voice -->


## Free notes / questions

<!-- anything that doesn't fit above, or you'll want to ask the organizer -->


---

When typing stops, say: **"process the brief"** — Claude Code will invoke
the `day-of-brief` skill, which cross-references this file with
`DAY_OF_INTAKE.md`, `DAY_OF_DECISIONS.md`, `runs/recon-latest.json`, and
`configs/agent.yaml`, then outputs:

1. Missing facts (go ask the organizer, now)
2. Filled intake summary
3. Proposed repo edits (ready to commit)
4. First three tasks to start (per role)
5. Open questions for the organizer
