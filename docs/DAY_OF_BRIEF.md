---
---

# Day-of brief

> **Type/paste freely below.** No structure. Whatever organizers say or send.
> Pre-event email, the verbal intro at 10:30 — all goes here, in any order.
> When you're done, say to Claude: **"process the brief"**.

---



## Critical confirmations — tick as you hear them

> Listen for each. If a box is still empty when the briefing ends, that's
> a question for the organizer **before** we start coding.

**Robot**
- [ ] Robot model + SDK name (Reachy Mini? Unitree Go2? something else?)
- [ ] Kill switch — physical button, software, or both
- [ ] Safety limits — max linear speed, max angular speed, fragile parts
- [ ] Robot's network address (or "USB", or "we hand you a token")

**Hardware + network**
- [ ] ZGX-A and ZGX-B IPs (or printed somewhere)
- [ ] vLLM endpoint port (default `:8000`; confirm if different)
- [ ] Internet access during the **build** — yes / no
- [ ] Internet access during the **judged run** — yes / no

**Sensors**
- [ ] Camera source — robot-mounted, laptop webcam, or provided device
- [ ] Microphone source — laptop, robot, or table mic
- [ ] Audio judged? (i.e., does the demo need to be voice-driven)

**Submission + demo**
- [ ] Submission format — file, video, live demo, scored harness, all of these
- [ ] Submission deadline strictness — 13:00 hard, or grace
- [ ] Demo opportunity — single live take, multiple takes, or recorded ahead
- [ ] Scoring weights — hardware utilization vs sensor integration vs agent quality (rough proportions)

**Constraints**
- [ ] Forbidden techniques — cloud models, scripted hard-codes, off-the-shelf agents
- [ ] On-site support availability during the build (just at start, or any time)

If the box stays unticked: ask. If it gets answered ambiguously: tick it
and put the verbatim quote in the bulk notes below — Claude flags
ambiguities when you say *"process the brief"*.

---

## Bulk notes

<!-- Type here. -->




---

> Below this line is an **optional template**. Don't fill it during the
> briefing. After you say *"process the brief"*, Claude will (if useful)
> reorganise your bulk notes above into the fields below. You can also
> pre-populate any field if it's already known (e.g. from a prior email).

---

## Optional structured fields

### Schedule
<!-- kickoff time, build window, submission deadline, jury, winner -->

### Robot
<!-- name, morphology, SDK, units, kill-switch, safety limits -->

### Sensors
<!-- cameras (count, resolution), mics, IMU, who owns each stream -->

### Network
<!-- ZGX A/B IPs, robot IP, internet access during build -->

### ZGX state
<!-- output of `hack recon` goes in runs/recon-latest.json — only note surprises -->

### Models / serving
<!-- vLLM / Ollama / NIM tags, ports, anything pre-installed -->

### Scoring / submission
<!-- time-weighted? live demo? submission format? checkpoints? -->

### Constraints
<!-- forbidden techniques, forbidden models, forbidden cloud, time cuts -->

### Quotes / emphasis
<!-- anything the presenter said twice or in a louder voice -->

### Open questions
<!-- ask the organizer; don't guess -->
