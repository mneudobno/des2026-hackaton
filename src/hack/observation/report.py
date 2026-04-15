"""Write a markdown observation report combining analyzer flags + UI snapshot + run summary."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from hack.observation.analyzer import AnalyzerResult


def write_report(
    scenario: str,
    analyzer: AnalyzerResult,
    summary_json: Path,
    ui_snapshot: dict[str, Any] | None,
    out_dir: Path = Path("runs"),
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = out_dir / f"observation-{scenario}-{ts}.md"
    s = json.loads(summary_json.read_text()) if summary_json.exists() else {}

    lines: list[str] = []
    lines.append(f"# Observation: {scenario}")
    lines.append(f"_{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(ts))}_\n")

    # --- Verdict
    worst = max((f.severity for f in analyzer.flags), key=_severity_rank, default="green")
    verdict = {"red": "❌ FAIL", "yellow": "⚠️ NEEDS WORK", "green": "✅ OK"}[worst]
    lines.append(f"**Verdict:** {verdict}  ·  {analyzer.summary_line}\n")

    # --- Run metrics
    lines.append("## Run metrics\n")
    lines.append(f"- scenario: `{scenario}`")
    lines.append(f"- success: **{s.get('success', 'unknown')}** — {s.get('success_reason', '')}")
    lines.append(f"- ticks run: {s.get('ticks_run', '?')}")
    vm = s.get("vlm_ms", {})
    pm = s.get("planner_ms", {})
    if vm.get("n"):
        lines.append(f"- VLM ms: n={vm['n']} mean={vm['mean']:.0f} p50={vm['p50']:.0f} p95={vm['p95']:.0f} max={vm['max']:.0f}")
    if pm.get("n"):
        lines.append(f"- Planner ms: n={pm['n']} mean={pm['mean']:.0f} p50={pm['p50']:.0f} p95={pm['p95']:.0f} max={pm['max']:.0f}")
    lines.append(f"- Tool calls: `{dict(analyzer.tool_calls)}`")
    lines.append(f"- Parse failures: vlm={s.get('vlm_parse_failures', 0)} plan={s.get('plan_parse_failures', 0)}\n")

    # --- Behaviour flags
    lines.append("## Behaviour flags\n")
    for f in analyzer.flags:
        icon = {"red": "🔴", "yellow": "🟡", "green": "🟢"}[f.severity]
        tick_note = f" (ticks {f.ticks[:10]}{'…' if len(f.ticks) > 10 else ''})" if f.ticks else ""
        lines.append(f"- {icon} **{f.code}** — {f.message}{tick_note}")
    lines.append("")

    # --- Live cues
    if analyzer.live_cues:
        lines.append("## Live cues received\n")
        for t, text in analyzer.live_cues:
            lines.append(f"- tick {t}: {text!r}")
        lines.append("")

    # --- UI snapshot
    lines.append("## UI snapshot\n")
    if ui_snapshot is None:
        lines.append("_No `runs/ui-latest.json` found — open the dashboard in Claude Code and have it call `hack.observation.ui_watcher.save_snapshot(...)` to include UI health here._\n")
    else:
        lines.append(f"- source URL: `{ui_snapshot.get('url', 'unknown')}`")
        lines.append(f"- mic state: `{ui_snapshot.get('mic_state', 'unknown')}`")
        cam = ui_snapshot.get('camera_img_status')
        lines.append(f"- camera image HTTP status: `{cam}`")
        errs = ui_snapshot.get("console_errors") or []
        lines.append(f"- console errors: {len(errs)}")
        for e in errs[:10]:
            lines.append(f"  - {e}")
        notes = ui_snapshot.get("notes") or []
        if notes:
            lines.append("- notes:")
            for n in notes:
                lines.append(f"  - {n}")
        shot = ui_snapshot.get("screenshot_path")
        if shot:
            lines.append(f"- screenshot: `{shot}`")
        lines.append("")

    # --- Pointers
    lines.append("## Artefacts\n")
    lines.append(f"- trace: `{analyzer.trace_path}`")
    lines.append(f"- summary: `{summary_json}`")
    lines.append("- watch it replay: `uv run hack demo play " + str(analyzer.trace_path) + "`\n")

    path.write_text("\n".join(lines) + "\n")
    return path


_SEV_ORDER = {"green": 0, "yellow": 1, "red": 2}


def _severity_rank(s: str) -> int:
    return _SEV_ORDER.get(s, -1)
