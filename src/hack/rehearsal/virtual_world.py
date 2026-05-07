"""Virtual world + robot — repeatable smoke tests without a physical robot or webcam.

The world has:
- a set of named coloured objects with (x, y) positions on a 2D table
- a robot with (x, y) pose and a gripper state
- a scripted sequence of voice "utterances" delivered on a tick schedule
- a render that produces a synthetic camera frame (numpy BGR array)
- a success criterion so the rehearsal runner can score the agent

The robot exposes the regular `RobotAdapter` 6-method interface so the agent
runtime can't tell it's virtual.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np

from hack.robot.base import RobotAdapter, RobotState


COLORS: dict[str, tuple[int, int, int]] = {  # BGR
    "red": (0, 0, 220),
    "green": (0, 200, 0),
    "blue": (230, 80, 0),
    "yellow": (0, 220, 220),
    "bin": (40, 40, 40),
}


ROBOT_RADIUS = 0.08  # approximate robot body radius for collision checks


@dataclass
class WorldObject:
    name: str
    color: str
    x: float
    y: float
    held: bool = False
    is_target: bool = False
    is_container: bool = False
    is_obstacle: bool = False
    radius: float = 0.1  # collision radius (circular)


@dataclass
class VoiceCue:
    at_tick: int
    text: str


@dataclass
class Scenario:
    name: str
    description: str
    objects: list[WorldObject]
    cues: list[VoiceCue] = field(default_factory=list)
    frame_size: tuple[int, int] = (480, 480)
    max_ticks: int = 40
    # Default success: target object's final position near the container.
    success_target: str = "red_cube"
    success_container: str = "bin"
    success_radius: float = 0.12  # world units
    # Optional custom evaluator. If set, overrides target/container scoring.
    # Signature: (robot, tool_calls_counter) -> (ok: bool, reason: str)
    evaluate: Callable[["VirtualWorldRobot", Counter], tuple[bool, str]] | None = None
    # Optional scenario-specific text appended to the system prompt.
    system_prompt_suffix: str = ""
    # World bounds: robot position is clamped to [-world_radius, +world_radius].
    world_radius: float = 1.0
    # Trajectory-efficiency gate (used by efficiency_evaluate). 0 = don't grade.
    # efficiency = optimal_length / actual_path_length; must be >= min_efficiency.
    min_efficiency: float = 0.0
    # Lower bound on the path length the robot *must* travel. Defaults to the
    # straight-line distance from (0,0) to the goal. Override when obstacles
    # make the straight line infeasible (e.g. the U-trap horseshoe).
    optimal_length: float | None = None
    # Progress watchdog: end the run if distance-to-goal hasn't improved by at
    # least `stall_progress_epsilon` metres for this many ticks. 0 = disabled.
    # `max_ticks` still applies as an absolute ceiling.
    stall_timeout_ticks: int = 30
    stall_progress_epsilon: float = 0.02

    def initial_poses(self) -> dict[str, tuple[float, float]]:
        return {o.name: (o.x, o.y) for o in self.objects}


class VirtualWorldRobot(RobotAdapter):
    """Robot that lives in a Scenario and renders its state."""

    name = "virtual"

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.pose: tuple[float, float, float] = (0.0, 0.0, 0.0)  # x, y, theta
        self.gripper_closed = False
        self.held_object: str | None = None
        self.objects: dict[str, WorldObject] = {o.name: o for o in scenario.objects}
        self.tick = 0
        self.utterances: list[str] = []
        # Per-tick snapshots (for dance scoring and any motion-variety analysis).
        self.pose_history: list[tuple[float, float, float]] = [self.pose]
        self.emotes: list[str] = []
        # Records when move() is clamped by world bounds — analyzer uses this
        # to flag "planner wanted X but world said no".
        self.clamp_events: list[dict] = []
        # Records collisions with obstacles.
        self.collision_events: list[dict] = []

    # ---- RobotAdapter contract ----
    async def move(self, dx: float, dy: float, dtheta: float) -> None:
        x, y, th = self.pose
        ix = x + dx * math.cos(th) - dy * math.sin(th)
        iy = y + dx * math.sin(th) + dy * math.cos(th)
        # Swept-path collision — sample the segment from (x,y) to (ix,iy) so a large
        # single step can't teleport through an obstacle. On the first sample that
        # enters any obstacle's clearance zone we stop the robot just before it.
        seg_len = math.hypot(ix - x, iy - y)
        obstacles = [o for o in self.objects.values() if o.is_obstacle]
        sx, sy = x, y
        if seg_len > 1e-6 and obstacles:
            # Step along the path at ~half the robot radius (or finer for tiny segs).
            sample_step = max(0.02, min(ROBOT_RADIUS * 0.5, seg_len / 2.0))
            n_samples = max(1, int(math.ceil(seg_len / sample_step)))
            ux, uy = (ix - x) / seg_len, (iy - y) / seg_len
            blocked = False
            for i in range(1, n_samples + 1):
                t = min(seg_len, i * sample_step)
                px, py = x + ux * t, y + uy * t
                hit = None
                for obj in obstacles:
                    d = _dist((px, py), (obj.x, obj.y))
                    clearance = obj.radius + ROBOT_RADIUS
                    if d < clearance:
                        hit = (obj, clearance)
                        break
                if hit is not None:
                    obj, clearance = hit
                    # Back off along the travel direction until we're clear.
                    back_t = t
                    while back_t > 0:
                        back_t -= sample_step * 0.5
                        bx, by = x + ux * back_t, y + uy * back_t
                        if _dist((bx, by), (obj.x, obj.y)) >= clearance:
                            sx, sy = bx, by
                            break
                    else:
                        sx, sy = x, y
                    self.collision_events.append({
                        "tick": self.tick,
                        "obstacle": obj.name,
                        "intended": [ix, iy],
                        "stopped_at": [round(sx, 4), round(sy, 4)],
                        "obstacle_pos": [obj.x, obj.y],
                        "travelled": round(_dist((x, y), (sx, sy)), 4),
                        "requested": round(seg_len, 4),
                    })
                    blocked = True
                    break
            if not blocked:
                sx, sy = ix, iy
        else:
            sx, sy = ix, iy
        # World bounds clamp.
        wr = self.scenario.world_radius
        nx = max(-wr, min(wr, sx))
        ny = max(-wr, min(wr, sy))
        nth = (th + dtheta + math.pi) % (2 * math.pi) - math.pi
        if nx != sx or ny != sy:
            self.clamp_events.append({
                "tick": self.tick,
                "requested": [dx, dy, dtheta],
                "intended": [ix, iy],
                "actual": [nx, ny],
                "pose_before": [x, y, th],
            })
        self.pose = (nx, ny, nth)
        self.pose_history.append(self.pose)
        if self.held_object and self.held_object in self.objects:
            self.objects[self.held_object].x = nx
            self.objects[self.held_object].y = ny

    async def grasp(self) -> None:
        self.gripper_closed = True
        if self.held_object is not None:
            return
        # find nearest graspable object within reach (0.18 world units).
        for obj in self.objects.values():
            if obj.is_container or obj.held:
                continue
            if _dist((obj.x, obj.y), self.pose[:2]) < 0.18:
                obj.held = True
                self.held_object = obj.name
                return

    async def release(self) -> None:
        self.gripper_closed = False
        if self.held_object is None:
            return
        o = self.objects[self.held_object]
        o.held = False
        o.x, o.y = self.pose[:2]
        self.held_object = None

    async def set_joint(self, name: str, value: float) -> None:
        # virtual robot has no joints; store anyway for the agent's sake
        pass

    async def get_state(self) -> RobotState:
        import math as _m
        dist = _m.hypot(self.pose[0], self.pose[1])
        # Nearby obstacles for the mock VLM / planner.
        nearby_obstacles = self._nearby_obstacles(max_dist=0.5)
        return RobotState(
            pose=self.pose,
            gripper_closed=self.gripper_closed,
            extra={
                "held": self.held_object,
                "tick": self.tick,
                "dist_from_origin": round(dist, 3),
                "on_stage": dist < 0.3,
                "nearby_obstacles": nearby_obstacles,
                "collision_count": len(self.collision_events),
            },
        )

    def _nearby_obstacles(self, max_dist: float = 0.5) -> list[dict]:
        """Return obstacles within max_dist with relative positions."""
        result = []
        x, y, th = self.pose
        for obj in self.objects.values():
            if not obj.is_obstacle:
                continue
            d = _dist((x, y), (obj.x, obj.y))
            if d > max_dist:
                continue
            # Compute relative position in body frame.
            dx_w = obj.x - x
            dy_w = obj.y - y
            cos_t, sin_t = math.cos(th), math.sin(th)
            dx_b = dx_w * cos_t + dy_w * sin_t
            dy_b = -dx_w * sin_t + dy_w * cos_t
            # Classify position.
            if dx_b > abs(dy_b) * 0.5:
                pos = "ahead"
            elif dx_b < -abs(dy_b) * 0.5:
                pos = "behind"
            else:
                pos = ""
            if dy_b > 0.05:
                pos += "-left" if pos else "left"
            elif dy_b < -0.05:
                pos += "-right" if pos else "right"
            result.append({
                "name": obj.name,
                "distance": round(d, 3),
                "position": pos or "nearby",
                "body_dx": round(dx_b, 3),
                "body_dy": round(dy_b, 3),
            })
        return sorted(result, key=lambda o: o["distance"])

    async def emote(self, label: str) -> None:
        self.utterances.append(f"[emote:{label}]")
        self.emotes.append(label)

    # ---- rendering ----
    def render_frame(self) -> np.ndarray:
        h, w = self.scenario.frame_size
        img = np.full((h, w, 3), 245, dtype=np.uint8)  # light background

        # Autoscale: fit a square viewport around (robot + objects + success radius)
        # with a 15% margin, minimum span 1.4 so the view doesn't zoom in too far.
        xs = [self.pose[0]] + [o.x for o in self.objects.values()]
        ys = [self.pose[1]] + [o.y for o in self.objects.values()]
        sc = self.scenario
        if any(o.name == sc.success_container for o in self.objects.values()) and sc.success_radius <= 1.0:
            con = next(o for o in self.objects.values() if o.name == sc.success_container)
            xs += [con.x - sc.success_radius, con.x + sc.success_radius]
            ys += [con.y - sc.success_radius, con.y + sc.success_radius]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1.4) * 1.15  # 15% margin, min 1.4 units
        half = span / 2

        def xy_to_px(x: float, y: float) -> tuple[int, int]:
            # centred square viewport; y flipped so +y is up
            return (
                int((x - (cx - half)) / span * w),
                int((1.0 - (y - (cy - half)) / span) * h),
            )

        # Grid lines for spatial reference (every 0.5 world units within the viewport)
        import math as _m
        lo = _m.floor(min(cx - half, cy - half) / 0.5) * 0.5
        hi = _m.ceil(max(cx + half, cy + half) / 0.5) * 0.5
        g = lo
        while g <= hi + 1e-6:
            px, _ = xy_to_px(g, cy)
            cv2.line(img, (px, 0), (px, h), (225, 225, 225), 1)
            _, py = xy_to_px(cx, g)
            cv2.line(img, (0, py), (w, py), (225, 225, 225), 1)
            g += 0.5

        # Success-radius circle (only when the criterion is a small-area rule).
        if sc.success_radius <= 0.5 and any(o.name == sc.success_container for o in self.objects.values()):
            con = next(o for o in self.objects.values() if o.name == sc.success_container)
            ccx_px, ccy_px = xy_to_px(con.x, con.y)
            # radius scales with the dynamic viewport
            r_px = int(sc.success_radius / span * w)
            _draw_dashed_circle(img, (ccx_px, ccy_px), r_px, (160, 160, 200), thickness=1, gap=6)

        # Objects — sizes also scale with the viewport so they look stable
        scale = w / span
        for obj in self.objects.values():
            color = COLORS.get(obj.color, (100, 100, 100))
            px, py = xy_to_px(obj.x, obj.y)
            if obj.is_obstacle:
                # Obstacles: filled circle + dashed exclusion zone.
                r_px = max(6, int(obj.radius * scale))
                cv2.circle(img, (px, py), r_px, color, -1)
                cv2.circle(img, (px, py), r_px, (20, 20, 20), 1)
                # Exclusion zone = radius + robot radius.
                exc_px = max(8, int((obj.radius + ROBOT_RADIUS) * scale))
                _draw_dashed_circle(img, (px, py), exc_px, (180, 80, 80), thickness=1, gap=5)
                cv2.putText(img, obj.name, (px - r_px, py - r_px - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)
            elif obj.is_container:
                half_world = 0.12
                r = max(6, int(half_world * scale))
                cv2.rectangle(img, (px - r, py - r), (px + r, py + r), color, 2)
                cv2.putText(img, obj.name, (px - r, py - r - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.44, color, 1, cv2.LINE_AA)
            else:
                half_world = 0.08
                r = max(6, int(half_world * scale))
                cv2.rectangle(img, (px - r, py - r), (px + r, py + r), color, -1)
                cv2.rectangle(img, (px - r, py - r), (px + r, py + r), (20, 20, 20), 1)

        # Robot trail — last 12 positions, fading.
        trail = self.pose_history[-12:]
        for i in range(1, len(trail)):
            a = xy_to_px(trail[i - 1][0], trail[i - 1][1])
            b = xy_to_px(trail[i][0], trail[i][1])
            shade = 180 - int(140 * (i / len(trail)))
            cv2.line(img, a, b, (shade, shade, shade), 1, cv2.LINE_AA)

        # Robot — scaled with viewport
        rx, ry = xy_to_px(self.pose[0], self.pose[1])
        r_radius = max(8, int(0.06 * scale))
        arrow_len = max(12, int(0.10 * scale))
        cv2.circle(img, (rx, ry), r_radius, (0, 0, 0), 2)
        th = self.pose[2]
        tx = int(rx + arrow_len * math.cos(th))
        ty = int(ry - arrow_len * math.sin(th))  # y flipped
        cv2.line(img, (rx, ry), (tx, ty), (0, 0, 0), 2)
        if self.gripper_closed:
            cv2.circle(img, (tx, ty), max(3, r_radius // 3), (0, 0, 0), -1)
        else:
            cv2.circle(img, (tx, ty), max(3, r_radius // 3), (0, 0, 0), 1)
        return img

    def success(self) -> tuple[bool, str]:
        tgt = self.objects.get(self.scenario.success_target)
        con = self.objects.get(self.scenario.success_container)
        if tgt is None or con is None:
            return False, f"missing object(s): target={tgt} container={con}"
        d = _dist((tgt.x, tgt.y), (con.x, con.y))
        ok = d < self.scenario.success_radius and not tgt.held
        return ok, f"target-to-container distance={d:.3f}m (threshold {self.scenario.success_radius}); held={tgt.held}"


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _draw_dashed_circle(img, center, radius, color, thickness=1, gap=6):
    """Simple dashed-circle approximation using short line segments."""
    import math as _m
    n = max(16, int(2 * _m.pi * radius / max(gap, 1)))
    for i in range(n):
        if i % 2 == 0:
            continue
        a0 = 2 * _m.pi * i / n
        a1 = 2 * _m.pi * (i + 1) / n
        p0 = (int(center[0] + radius * _m.cos(a0)), int(center[1] + radius * _m.sin(a0)))
        p1 = (int(center[0] + radius * _m.cos(a1)), int(center[1] + radius * _m.sin(a1)))
        cv2.line(img, p0, p1, color, thickness, cv2.LINE_AA)
