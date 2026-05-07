---
name: day-of-brief
description: Turn the free-text day-of brief (docs/DAY_OF_BRIEF.md) into actionable repo changes. Trigger on "we got the brief", "read the brief", "process the brief", or when the user opens DAY_OF_BRIEF.md right after the challenge intro. Outputs a missing-facts list, proposed config edits, adapter choice, and the first three DAY_OF_TASKS rows to start on.
---

# Day-of brief → decisions + edits

During the 30-minute challenge intro the typist writes free-form notes
into the **Bulk notes** section at the top of `docs/DAY_OF_BRIEF.md`.
The structured fields below the second `---` separator are **optional** —
treat them as low-priority hints. Your primary input is the bulk free
text. Bridge the gap in under 5 minutes of wall-clock time so the build
window starts on code, not on paperwork.

**Precondition:** the **Bulk notes** section in `docs/DAY_OF_BRIEF.md`
contains content (anything more than whitespace and the comment hint).
If it's empty, stop and tell the user to type into it first. The
optional structured fields can be empty — that's fine.

## Inputs to read (in order)

1. `docs/DAY_OF_BRIEF.md` — read the **Bulk notes** section as primary
   input. Then check the **Optional structured fields** below the second
   `---`; treat any non-empty field as a high-confidence supplement.
2. `docs/DAY_OF_DECISIONS.md` — the brief → repo-edit matrix.
3. `docs/DAY_OF_TASKS.md` — the role × 15-min grid.
4. `runs/recon-latest.json` if present — machine-authoritative facts about
   the two ZGX boxes. Trust it over anything typed in the brief about ZGX state.
5. `configs/agent.yaml` — current config; you will propose diffs, not rewrites.

## Reorganise bulk notes into structured fields (offer, don't auto-apply)

After producing the five-section response below, **offer** to reorganise
the bulk notes into the optional structured fields in the same file:

> "I can also rewrite your bulk notes into the structured fields below
> (Schedule / Robot / Sensors / etc.) — useful as a clean reference. Reply
> 'yes' or 'restructure' to apply."

If the user agrees, edit `docs/DAY_OF_BRIEF.md` so each structured field
is populated from the bulk notes. Keep the bulk notes section intact —
the structured version is a derived view, not a replacement. Don't
fabricate values: if a field has no source in the bulk notes, leave its
HTML comment placeholder alone.

## Output contract — produce ALL FIVE sections in one response

Respond in this exact order. The team reads top-to-bottom; put what unblocks
them first.

### 1. Missing facts (first, no exceptions)

One-line bullets for every intake section where the brief is silent or vague.
**Format:** `- §<N> <field>: <why it matters — one clause>`. Example:

```
- §3 kill-switch procedure: we cannot safely move without it
- §3 units: "radius 80 cm" — confirm all motion commands are metres
- §7 submission format: unknown — decide who goes back to ask organizers
```

Cap at 10 items. If more than 10 things are missing, list the top-10 and
flag "brief is unusually thin — someone should talk to the organizer now."

### 2. Filled intake summary

A compact table of what you *did* extract, one row per intake section. Use
the exact intake headings. Mark each cell one of:

- `<extracted fact>` — verbatim or lightly paraphrased from the brief
- `(recon)` — authoritative value came from `runs/recon-latest.json`
- `(unclear)` — brief mentioned it but ambiguously
- `(missing)` — not in the brief (also appears in section 1)

### 3. Proposed repo edits

Walk `DAY_OF_DECISIONS.md` top to bottom. For each section 1–10 that the
brief has enough data to decide, emit a fenced diff block or a single-line
action. Format:

```
§1 Robot adapter → <choice> (e.g. reachy_mini / unitree_go2 / lerobot / http / ros2 / new class)
```

```yaml
# configs/agent.yaml
llm:
  provider: openai-compat
  model: nvidia/Nemotron-3-Nano-Omni      # confirm with curl :8000/v1/models
  base_url: http://<zgx-a-ip>:8000/v1
  base_urls: [http://<zgx-b-ip>:8000/v1]
vlm:
  provider: openai-compat                  # multimodal Omni → same endpoint
  model: nvidia/Nemotron-3-Nano-Omni
  base_url: http://<zgx-a-ip>:8000/v1
```

For decisions you can't make from the brief, say so plainly:
`§5 audio: cannot decide — brief doesn't say whether STT is judged`.

**Do not apply edits automatically.** Emit them for the brain lead to commit.

### 4. First three DAY_OF_TASKS rows to start now

Pick three from the current stage (likely T+0:15 — parallel setup) that are
unblocked by the brief. List with the role tag. Example:

```
- (R) `bash scripts/bootstrap_zgx.sh --role primary` on ZGX A
- (R) Create src/hack/robot/reachy_mini.py stub; probe against the real host
- (B) Update configs/agent.yaml to the block in §3 above and commit
```

If fewer than three are unblocked, say so — don't pad.

### 5. Open questions for the organizer

Extract from §1 (missing facts). Keep to 1–3 items, in the exact wording
the team should use when they walk over to ask. Example:

```
- "Are cloud API calls allowed during the judged run, or local-only?"
- "Is there a wall-clock window for the demo, or do we pick when to present?"
```

## Rules

- **Don't invent facts.** If the brief doesn't say the kill-switch, list it
  as missing. Don't guess from the robot model.
- **Don't edit files in this pass.** Output is advisory. The brain lead
  commits after a 2-minute team read.
- **Favour defaults under uncertainty.** When a decision matrix says "default
  if blank", use it and note the default was invoked.
- **Flag safety surfaces explicitly.** Missing kill-switch, missing safety
  limits, missing coordinate frame → surface these even if the team didn't
  ask for them.
- **Be fast.** This entire pass should take ≤ 90 seconds of Claude time.
  Do not spawn agents. Do not re-read every file — read only what you need.

## After the team acts on your output

The brain lead commits the config edits, the robot lead starts on the
adapter, and the demo lead begins recording. The next time this skill is
invoked (e.g. "the brief got an update from organizers"), re-run the whole
pass — do not try to diff against your previous output.
