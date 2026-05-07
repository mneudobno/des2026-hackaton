"""Small DSL for composing virtual worlds.

Goal: make it trivial to describe obstacle layouts that genuinely force the
agent to navigate *around* things, not through them.

All helpers return ``list[WorldObject]`` you can splat into ``Scenario.objects``.
Obstacles are modelled as circles (the only primitive the physics layer knows
about), so walls and barriers are rendered as a dense chain of circles. The
swept-path collision in ``virtual_world.move`` then makes them physically
honest: the robot cannot teleport through a chain as long as the gap between
consecutive circles is ``< ROBOT_RADIUS``.
"""

from __future__ import annotations

import math
from dataclasses import replace

from hack.rehearsal.virtual_world import ROBOT_RADIUS, WorldObject


def goal(x: float, y: float, *, name: str = "goal", color: str = "green") -> WorldObject:
    return WorldObject(name=name, color=color, x=round(x, 3), y=round(y, 3), is_container=True)


def obstacle(x: float, y: float, *, radius: float = 0.1, name: str | None = None,
             color: str = "red") -> WorldObject:
    return WorldObject(
        name=name or "obs",
        color=color,
        x=round(x, 3), y=round(y, 3),
        is_obstacle=True, radius=round(radius, 3),
    )


def wall_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    thickness: float = 0.09,
    prefix: str = "wall",
    color: str = "red",
) -> list[WorldObject]:
    """Chain of circular obstacles approximating a solid line between `start` and `end`.

    ``thickness`` is the circle radius. Consecutive circles overlap so the gap
    is always < ROBOT_RADIUS (= impassable).
    """
    x0, y0 = start
    x1, y1 = end
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1e-6:
        return [obstacle(x0, y0, radius=thickness, name=f"{prefix}_0", color=color)]
    # Spacing must be strictly < ROBOT_RADIUS so nothing can slip through.
    spacing = max(0.05, min(thickness * 1.3, ROBOT_RADIUS - 0.02))
    n = max(2, int(math.ceil(length / spacing)) + 1)
    out: list[WorldObject] = []
    for i in range(n):
        t = i / (n - 1)
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        out.append(obstacle(x, y, radius=thickness, name=f"{prefix}_{i}", color=color))
    return out


def line_barrier(
    center: tuple[float, float],
    length: float,
    *,
    axis: str = "y",
    thickness: float = 0.09,
    gap: tuple[float, float] | None = None,
    prefix: str = "bar",
) -> list[WorldObject]:
    """Wall centred on `center`, aligned with x- or y-axis, optional passage gap.

    ``gap = (start, end)`` omits circles whose centre falls inside the interval,
    so the agent has to find the opening.
    """
    cx, cy = center
    half = length / 2
    if axis == "y":
        a = (cx, cy - half)
        b = (cx, cy + half)
    elif axis == "x":
        a = (cx - half, cy)
        b = (cx + half, cy)
    else:
        raise ValueError(f"axis must be 'x' or 'y', got {axis!r}")
    segs = wall_segment(a, b, thickness=thickness, prefix=prefix)
    if gap is None:
        return segs
    lo, hi = gap
    kept: list[WorldObject] = []
    for o in segs:
        v = o.y if axis == "y" else o.x
        if lo <= v <= hi:
            continue
        kept.append(o)
    # Rename sequentially so trace/log is tidy.
    return [replace(o, name=f"{prefix}_{i}") for i, o in enumerate(kept)]


def corridor(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    width: float = 0.5,
    thickness: float = 0.09,
    prefix: str = "corr",
) -> list[WorldObject]:
    """Two parallel walls forming a straight corridor from `start` to `end`.

    Robot must travel inside the corridor to reach something beyond it.
    """
    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return []
    # Perpendicular unit vector.
    nx, ny = -dy / length, dx / length
    half = width / 2
    left_a = (x0 + nx * half, y0 + ny * half)
    left_b = (x1 + nx * half, y1 + ny * half)
    right_a = (x0 - nx * half, y0 - ny * half)
    right_b = (x1 - nx * half, y1 - ny * half)
    left = wall_segment(left_a, left_b, thickness=thickness, prefix=f"{prefix}_L")
    right = wall_segment(right_a, right_b, thickness=thickness, prefix=f"{prefix}_R")
    return left + right


def horseshoe(
    mouth_center: tuple[float, float],
    depth: float,
    *,
    width: float = 0.8,
    opens: str = "+x",
    thickness: float = 0.09,
    prefix: str = "horse",
) -> list[WorldObject]:
    """U-shaped trap. The goal/target can sit at mouth_center; the horseshoe
    encloses it on three sides, forcing approach from the ``opens`` direction.

    ``opens``: "+x", "-x", "+y", "-y" — the side left open.
    """
    cx, cy = mouth_center
    half = width / 2
    if opens == "+x":
        back = wall_segment((cx - depth, cy - half), (cx - depth, cy + half),
                            thickness=thickness, prefix=f"{prefix}_back")
        top = wall_segment((cx - depth, cy + half), (cx, cy + half),
                           thickness=thickness, prefix=f"{prefix}_top")
        bot = wall_segment((cx - depth, cy - half), (cx, cy - half),
                           thickness=thickness, prefix=f"{prefix}_bot")
    elif opens == "-x":
        back = wall_segment((cx + depth, cy - half), (cx + depth, cy + half),
                            thickness=thickness, prefix=f"{prefix}_back")
        top = wall_segment((cx, cy + half), (cx + depth, cy + half),
                           thickness=thickness, prefix=f"{prefix}_top")
        bot = wall_segment((cx, cy - half), (cx + depth, cy - half),
                           thickness=thickness, prefix=f"{prefix}_bot")
    elif opens == "+y":
        back = wall_segment((cx - half, cy - depth), (cx + half, cy - depth),
                            thickness=thickness, prefix=f"{prefix}_back")
        top = wall_segment((cx - half, cy - depth), (cx - half, cy),
                           thickness=thickness, prefix=f"{prefix}_left")
        bot = wall_segment((cx + half, cy - depth), (cx + half, cy),
                           thickness=thickness, prefix=f"{prefix}_right")
    elif opens == "-y":
        back = wall_segment((cx - half, cy + depth), (cx + half, cy + depth),
                            thickness=thickness, prefix=f"{prefix}_back")
        top = wall_segment((cx - half, cy), (cx - half, cy + depth),
                           thickness=thickness, prefix=f"{prefix}_left")
        bot = wall_segment((cx + half, cy), (cx + half, cy + depth),
                           thickness=thickness, prefix=f"{prefix}_right")
    else:
        raise ValueError(f"opens must be one of +x/-x/+y/-y, got {opens!r}")
    return back + top + bot


def gate(
    center: tuple[float, float],
    *,
    opening: float = 0.3,
    length: float = 2.0,
    axis: str = "y",
    thickness: float = 0.09,
    prefix: str = "gate",
) -> list[WorldObject]:
    """Single barrier with a narrow passage at `center`. Robot must aim for the gap."""
    cx, cy = center
    half_opening = opening / 2
    if axis == "y":
        return line_barrier(center=(cx, cy), length=length, axis="y",
                            thickness=thickness,
                            gap=(cy - half_opening, cy + half_opening),
                            prefix=prefix)
    return line_barrier(center=(cx, cy), length=length, axis="x",
                        thickness=thickness,
                        gap=(cx - half_opening, cx + half_opening),
                        prefix=prefix)


def dedupe_names(objs: list[WorldObject]) -> list[WorldObject]:
    """Rename WorldObjects so all names are unique (keeps the first one, renames the rest)."""
    seen: dict[str, int] = {}
    out: list[WorldObject] = []
    for o in objs:
        base = o.name
        if base not in seen:
            seen[base] = 0
            out.append(o)
            continue
        seen[base] += 1
        out.append(replace(o, name=f"{base}__{seen[base]}"))
    return out
