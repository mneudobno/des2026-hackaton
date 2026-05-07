"""Reachy Mini adapter — Pollen Robotics' desktop head.

SDK shape (as of v1.6.3, https://github.com/pollen-robotics/reachy_mini):
    from reachy_mini import ReachyMini
    with ReachyMini(host="reachy-mini.local", port=8000) as mini:
        mini.set_target(head=<4x4>, antennas=[r,l], body_yaw=<rad>)
        mini.goto_target(head=..., duration=0.5, method="minjerk")
        mini.play_move(emotes.get("happy"))
        frame = mini.media.get_frame()

The SDK is synchronous and uses a local daemon on port 8000. We wrap every
blocking call in ``asyncio.to_thread`` to keep the agent event loop responsive.

Semantic mapping for the 6-method RobotAdapter contract (Reachy Mini is
*stationary* — it's a head on a desk):
    move(dx, dy, dtheta)  → dtheta rotates the body yaw; dx/dy nudge the head's
                            pitch/yaw to emulate gaze (look ahead / look left).
    grasp() / release()   → antenna "perked" vs "relaxed" gesture (no gripper).
    set_joint(name, val)  → routed by name: body_rotation, stewart_N (IK via
                            head pose), left_antenna, right_antenna.
    get_state()           → head_pose (4x4) + joint positions + body_yaw + imu.
    emote(label)          → play_move from HF "reachy-mini-emotions-library"
                            (and "dances-library"). Unknown label raises.

Robot-adapter skill fills in the rest day-of (actual host IP, antenna gesture
choice, any venue-specific safety bounds). Every surface needing day-of
confirmation is marked `# DAYOF: R`.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

from hack.robot.base import RobotAdapter, RobotState


_DEFAULT_EMOTE_LIBRARY = "pollen-robotics/reachy-mini-emotions-library"
_DEFAULT_DANCE_LIBRARY = "pollen-robotics/reachy-mini-dances-library"


class ReachyMiniRobot(RobotAdapter):
    """Thin async wrapper over the synchronous ``reachy_mini`` SDK."""

    name = "reachy_mini"

    def __init__(
        self,
        host: str = "reachy-mini.local",
        port: int = 8000,
        connection_mode: str = "auto",
        emote_libraries: tuple[str, ...] = (_DEFAULT_EMOTE_LIBRARY, _DEFAULT_DANCE_LIBRARY),
        gaze_scale: float = 0.4,
    ) -> None:
        # DAYOF: R — confirm host/port from the venue's network (`reachy-mini.local`
        # only resolves if mDNS works; otherwise use the IP shown in the Pollen UI).
        self.host = host
        self.port = port
        self.connection_mode = connection_mode
        self.emote_libraries = emote_libraries
        self.gaze_scale = gaze_scale  # metres/radians → head-pose scaling
        self._mini: Any = None
        self._emotes: dict[str, Any] = {}
        self._body_yaw: float = 0.0  # tracked locally; SDK doesn't expose a getter

    # ---------- lifecycle ----------

    async def connect(self) -> None:
        def _open() -> tuple[Any, dict[str, Any]]:
            from reachy_mini import ReachyMini
            from reachy_mini.motion.recorded_move import RecordedMoves

            mini = ReachyMini(host=self.host, port=self.port, connection_mode=self.connection_mode)
            mini.__enter__()  # context-manager entry — performs the handshake
            emotes: dict[str, Any] = {}
            for lib in self.emote_libraries:
                try:
                    moves = RecordedMoves(lib)
                    for label in moves.list_moves():
                        emotes.setdefault(label, moves.get(label))
                except Exception:
                    # Lib fails to download → continue. emote() will reject unknown labels.
                    continue
            mini.wake_up()
            return mini, emotes

        self._mini, self._emotes = await asyncio.to_thread(_open)

    async def disconnect(self) -> None:
        if self._mini is None:
            return
        def _close() -> None:
            try:
                self._mini.goto_sleep()
            except Exception:
                pass
            try:
                self._mini.__exit__(None, None, None)
            except Exception:
                pass
        await asyncio.to_thread(_close)
        self._mini = None

    # ---------- motion ----------

    async def move(self, dx: float, dy: float, dtheta: float) -> None:
        """Reachy Mini is stationary; map translation to a gaze shift, rotation to body yaw.

        dtheta adds to the tracked ``_body_yaw`` and calls ``set_target_body_yaw``.
        dx becomes a head *pitch* offset (positive dx → tilt forward / look down);
        dy becomes a head *yaw* offset (positive dy → look left). Both in radians
        after ``gaze_scale``. The SDK auto-clamps to joint limits (head ±40° on
        pitch/roll, body yaw ±160°).
        """
        assert self._mini is not None, "call connect() first"
        self._body_yaw = _wrap_pi(self._body_yaw + dtheta)
        pitch = dx * self.gaze_scale
        yaw = dy * self.gaze_scale
        body_yaw = self._body_yaw

        def _apply() -> None:
            from reachy_mini.utils import create_head_pose
            head = create_head_pose(pitch=pitch, yaw=yaw, degrees=False)
            self._mini.goto_target(head=head, body_yaw=body_yaw, duration=0.3, method="minjerk")

        await asyncio.to_thread(_apply)

    async def grasp(self) -> None:
        """No gripper — map to a perked antenna posture (both antennas forward)."""
        assert self._mini is not None
        # DAYOF: R — tune antenna angles to whatever reads as "alert" on the robot.
        def _apply() -> None:
            self._mini.set_target_antenna_joint_positions([math.radians(30), math.radians(-30)])
        await asyncio.to_thread(_apply)

    async def release(self) -> None:
        """No gripper — antennas back to neutral."""
        assert self._mini is not None
        def _apply() -> None:
            self._mini.set_target_antenna_joint_positions([0.0, 0.0])
        await asyncio.to_thread(_apply)

    async def set_joint(self, name: str, value: float) -> None:
        """Route by joint name — Reachy Mini has no generic ``set_joint``.

        Accepted names:
          * ``body_rotation`` — radians, absolute.
          * ``left_antenna`` / ``right_antenna`` — radians, absolute.
          * ``head_pitch`` / ``head_yaw`` / ``head_roll`` — radians, absolute.
          * ``stewart_1`` .. ``stewart_6`` — rejected (set head pose instead).
        """
        assert self._mini is not None

        def _apply() -> None:
            from reachy_mini.utils import create_head_pose
            if name == "body_rotation":
                self._mini.set_target_body_yaw(value)
                self._body_yaw = _wrap_pi(value)
            elif name in ("left_antenna", "right_antenna"):
                left, right = self._mini.get_present_antenna_joint_positions()
                if name == "left_antenna":
                    left = value
                else:
                    right = value
                self._mini.set_target_antenna_joint_positions([left, right])
            elif name in ("head_pitch", "head_yaw", "head_roll"):
                kwargs = {name.split("_", 1)[1]: value}
                self._mini.set_target_head_pose(create_head_pose(**kwargs, degrees=False))
            else:
                raise ValueError(f"reachy_mini: unsupported joint {name!r}")

        await asyncio.to_thread(_apply)

    async def get_state(self) -> RobotState:
        assert self._mini is not None

        def _read() -> RobotState:
            head_pose = self._mini.get_current_head_pose().tolist()
            head_joints, antennas = self._mini.get_current_joint_positions()
            joints: dict[str, float] = {}
            for i, v in enumerate(head_joints):
                joints[f"stewart_{i+1}"] = float(v)
            joints["left_antenna"] = float(antennas[0])
            joints["right_antenna"] = float(antennas[1])
            joints["body_rotation"] = float(self._body_yaw)
            extra: dict[str, Any] = {"head_pose": head_pose}
            imu = getattr(self._mini, "imu", None)
            if imu is not None:
                # IMU fields exposed on the property — record whatever's available.
                for attr in ("quaternion", "gyro", "accel"):
                    val = getattr(imu, attr, None)
                    if val is not None:
                        extra[f"imu_{attr}"] = list(val) if hasattr(val, "__iter__") else val
            # pose is (x, y, theta); Reachy Mini doesn't translate so x=y=0, theta=body_yaw.
            return RobotState(pose=(0.0, 0.0, self._body_yaw), joints=joints, extra=extra)

        return await asyncio.to_thread(_read)

    async def emote(self, label: str) -> None:
        """Play a named recorded move. Unknown label raises — no fallback."""
        assert self._mini is not None
        move = self._emotes.get(label)
        if move is None:
            # DAYOF: R — if labels don't match cue text, add a mapping dict here
            # (e.g. {"wave": "hello", "nod": "yes"}).
            raise ValueError(
                f"reachy_mini: unknown emote {label!r}; known: {sorted(self._emotes)[:8]}..."
            )
        await asyncio.to_thread(self._mini.play_move, move, 1.0)


def _wrap_pi(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi
