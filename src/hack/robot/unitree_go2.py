"""Unitree Go2 adapter — quadruped sport-mode high-level control.

SDK: https://github.com/unitreerobotics/unitree_sdk2_python (BSD-3). Uses
Cyclone DDS over a wired network interface — set via ``network_iface``.

    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
    from unitree_sdk2py.go2.sport.sport_client import SportClient
    ChannelFactoryInitialize(0, "eth0")
    sport = SportClient(); sport.SetTimeout(5.0); sport.Init()
    sport.Move(vx, vy, vyaw)      # fire-and-forget velocity; loop at ~10 Hz
    sport.StopMove()
    sport.Hello() / sport.Sit() / sport.Dance1() / sport.Stretch()

The SDK is synchronous; we wrap blocking calls in ``asyncio.to_thread``.

Semantic mapping for the 6-method RobotAdapter contract:
    move(dx, dy, dtheta)  → integrate body-frame velocity at 10 Hz over a short
                            window (``command_duration_s``), then ``StopMove``.
                            Speed bounds come from the runtime's safety clamp.
    grasp() / release()   → no gripper, no-op (Go2 is a quadruped).
    set_joint(name, val)  → rejected; sport-mode doesn't expose joints, and
                            low-level joint control is unsafe without tuning.
    get_state()           → read latest DDS ``rt/sportmodestate`` sample (pose,
                            velocity, IMU, foot forces, body_height).
    emote(label)          → map to the sport-mode preset (Hello/Sit/Stretch/
                            Dance1/Dance2/Heart/Content). Flips/HandStand are
                            gated behind ``allow_acrobatics=True`` — show-floor
                            unsafe by default.

Day-of wiring surfaces marked ``# DAYOF: R``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from hack.robot.base import RobotAdapter, RobotState


# Sport-mode preset map. Left-hand = cue-friendly label; right-hand = actual
# SportClient method name. Unknown labels are rejected (no fallback).
_SAFE_EMOTES: dict[str, str] = {
    "hello": "Hello",
    "wave": "Hello",
    "sit": "Sit",
    "rise": "RiseSit",
    "stand": "StandUp",
    "stand_down": "StandDown",
    "balance": "BalanceStand",
    "stretch": "Stretch",
    "content": "Content",
    "happy": "Content",
    "heart": "Heart",
    "dance": "Dance1",
    "dance1": "Dance1",
    "dance2": "Dance2",
    "scrape": "Scrape",
    "pose": "Pose",
}
_ACROBATIC_EMOTES: dict[str, str] = {
    "flip": "FrontFlip",
    "front_flip": "FrontFlip",
    "back_flip": "BackFlip",
    "left_flip": "LeftFlip",
    "front_jump": "FrontJump",
    "front_pounce": "FrontPounce",
    "handstand": "HandStand",
}


class UnitreeGo2Robot(RobotAdapter):
    name = "unitree_go2"

    def __init__(
        self,
        network_iface: str = "eth0",
        domain_id: int = 0,
        command_rate_hz: float = 10.0,
        command_duration_s: float = 0.5,
        allow_acrobatics: bool = False,
        stand_on_connect: bool = True,
    ) -> None:
        # DAYOF: R — confirm NIC (ip a / ifconfig). On Linux laptops a USB-Ethernet
        # dongle often appears as enx<MAC>; on DGX OS it may be enp2s0 or eth0.
        self.network_iface = network_iface
        self.domain_id = domain_id
        self.command_rate_hz = command_rate_hz
        self.command_duration_s = command_duration_s
        self.allow_acrobatics = allow_acrobatics
        self.stand_on_connect = stand_on_connect
        self._sport: Any = None
        self._video: Any = None
        self._state_sub: Any = None
        self._latest_state: Any = None

    # ---------- lifecycle ----------

    async def connect(self) -> None:
        def _open() -> tuple[Any, Any, Any]:
            from unitree_sdk2py.core.channel import (
                ChannelFactoryInitialize,
                ChannelSubscriber,
            )
            from unitree_sdk2py.go2.sport.sport_client import SportClient
            from unitree_sdk2py.go2.video.video_client import VideoClient
            from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

            ChannelFactoryInitialize(self.domain_id, self.network_iface)
            sport = SportClient()
            sport.SetTimeout(5.0)
            sport.Init()
            video = VideoClient()
            video.SetTimeout(3.0)
            video.Init()

            state_sub = ChannelSubscriber("rt/sportmodestate", SportModeState_)

            def _on_state(msg: Any) -> None:
                self._latest_state = msg

            state_sub.Init(_on_state, 10)
            if self.stand_on_connect:
                sport.StandUp()
                time.sleep(2.0)
                sport.BalanceStand()
            return sport, video, state_sub

        self._sport, self._video, self._state_sub = await asyncio.to_thread(_open)

    async def disconnect(self) -> None:
        if self._sport is None:
            return
        def _close() -> None:
            try:
                self._sport.StopMove()
            except Exception:
                pass
            try:
                self._sport.StandDown()
            except Exception:
                pass
            try:
                self._sport.Damp()
            except Exception:
                pass
        await asyncio.to_thread(_close)
        self._sport = None
        self._video = None
        self._state_sub = None

    # ---------- motion ----------

    async def move(self, dx: float, dy: float, dtheta: float) -> None:
        """Integrate dx/dy/dtheta over ``command_duration_s`` at ``command_rate_hz``.

        SportClient.Move is fire-and-forget velocity, so we convert the body-frame
        *displacement* the runtime hands us into a velocity command of magnitude
        ``disp / duration`` and hold it for ``duration`` seconds, then StopMove.
        The runtime's safety clamp caps dx/dy/dtheta before this function sees
        them — so we don't double-clamp here.
        """
        assert self._sport is not None, "call connect() first"
        duration = self.command_duration_s
        vx = dx / duration
        vy = dy / duration
        vyaw = dtheta / duration
        rate = 1.0 / self.command_rate_hz
        steps = max(1, int(duration * self.command_rate_hz))

        def _drive() -> None:
            for _ in range(steps):
                self._sport.Move(vx, vy, vyaw)
                time.sleep(rate)
            self._sport.StopMove()

        await asyncio.to_thread(_drive)

    async def grasp(self) -> None:
        # No gripper. Logged by the caller; silent here.
        return None

    async def release(self) -> None:
        # No gripper.
        return None

    async def set_joint(self, name: str, value: float) -> None:
        # Go2 sport-mode does not expose joint control. Low-level (`rt/lowcmd`)
        # exists but is unsafe without per-robot gain tuning — explicit reject.
        raise NotImplementedError(
            f"unitree_go2: set_joint({name!r}) not supported in sport mode. "
            "Use preset emotes (sit, stretch, dance1) or a velocity move."
        )

    async def get_state(self) -> RobotState:
        assert self._sport is not None
        msg = self._latest_state
        if msg is None:
            return RobotState()

        def _extract() -> RobotState:
            pos = list(getattr(msg, "position", (0.0, 0.0, 0.0)))
            imu = getattr(msg, "imu_state", None)
            # Reconstruct heading from the IMU quaternion if available.
            theta = 0.0
            if imu is not None:
                q = getattr(imu, "quaternion", None)
                if q is not None and len(q) >= 4:
                    w, x, y, z = q[0], q[1], q[2], q[3]
                    # yaw from quaternion (ZYX Euler)
                    import math
                    theta = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
            extra: dict[str, Any] = {
                "mode": getattr(msg, "mode", None),
                "gait_type": getattr(msg, "gait_type", None),
                "body_height": getattr(msg, "body_height", None),
                "foot_force": list(getattr(msg, "foot_force", []) or []),
                "velocity": list(getattr(msg, "velocity", []) or []),
            }
            return RobotState(pose=(float(pos[0]), float(pos[1]), float(theta)), extra=extra)

        return await asyncio.to_thread(_extract)

    async def emote(self, label: str) -> None:
        """Dispatch to a SportClient preset. Rejects unknown + unsafe-by-default."""
        assert self._sport is not None
        key = label.strip().lower()
        method = _SAFE_EMOTES.get(key)
        is_acrobatic = False
        if method is None:
            method = _ACROBATIC_EMOTES.get(key)
            is_acrobatic = method is not None
        if method is None:
            raise ValueError(
                f"unitree_go2: unknown emote {label!r}; known: {sorted(_SAFE_EMOTES)}"
            )
        if is_acrobatic and not self.allow_acrobatics:
            raise PermissionError(
                f"unitree_go2: emote {label!r} ({method}) is acrobatic. "
                "Set allow_acrobatics=True on the adapter to enable."
            )
        fn = getattr(self._sport, method, None)
        if fn is None:
            raise RuntimeError(f"unitree_go2: SportClient has no method {method!r}")
        await asyncio.to_thread(fn)

    # ---------- optional: camera snapshot for day-of demos ----------

    async def snap_camera(self) -> bytes | None:
        """Return the latest JPEG from the front fisheye, or None if unavailable."""
        if self._video is None:
            return None
        def _read() -> bytes | None:
            code, data = self._video.GetImageSample()
            return bytes(data) if code == 0 and data else None
        return await asyncio.to_thread(_read)
