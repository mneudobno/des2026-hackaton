"""Contract tests for Reachy Mini + Unitree Go2 adapters.

The real SDKs aren't installed on CI. We install in-memory stubs under the
exact import paths the adapters use, then exercise each of the 6 RobotAdapter
methods. What we're asserting:

  * connect()/disconnect() call the SDK lifecycle methods we expect.
  * move / grasp / release / set_joint / get_state / emote dispatch to the
    documented SDK methods with the documented arguments (or raise for
    unsupported operations like Go2.set_joint).

No network, no hardware — pure shape verification.
"""

from __future__ import annotations

import asyncio
import math
import sys
import types
from typing import Any

import numpy as np
import pytest


# --------------------------------------------------------------------------
# Reachy Mini stub — covers reachy_mini, reachy_mini.utils,
# reachy_mini.motion.recorded_move. The adapter imports these lazily inside
# connect(), so we just need them registered in sys.modules when that runs.
# --------------------------------------------------------------------------


class _StubReachyMini:
    instances: list["_StubReachyMini"] = []

    def __init__(self, host: str = "", port: int = 0, connection_mode: str = "auto") -> None:
        self.host = host
        self.port = port
        self.connection_mode = connection_mode
        self.calls: list[tuple[str, Any]] = []
        self.entered = False
        self.exited = False
        self._body_yaw = 0.0
        self._antennas = (0.0, 0.0)
        _StubReachyMini.instances.append(self)

    def __enter__(self) -> "_StubReachyMini":
        self.entered = True
        return self

    def __exit__(self, *exc: object) -> None:
        self.exited = True

    # Match the real API surface used by the adapter.
    def wake_up(self) -> None: self.calls.append(("wake_up", None))
    def goto_sleep(self) -> None: self.calls.append(("goto_sleep", None))
    def goto_target(self, **kw: Any) -> None: self.calls.append(("goto_target", kw))
    def set_target(self, **kw: Any) -> None: self.calls.append(("set_target", kw))
    def set_target_head_pose(self, p: Any) -> None: self.calls.append(("set_target_head_pose", p))
    def set_target_body_yaw(self, v: float) -> None:
        self._body_yaw = v
        self.calls.append(("set_target_body_yaw", v))
    def set_target_antenna_joint_positions(self, pair: list[float]) -> None:
        self._antennas = (pair[0], pair[1])
        self.calls.append(("set_target_antenna_joint_positions", list(pair)))
    def get_present_antenna_joint_positions(self) -> tuple[float, float]:
        return self._antennas
    def get_current_head_pose(self) -> np.ndarray:
        return np.eye(4)
    def get_current_joint_positions(self) -> tuple[list[float], list[float]]:
        return ([0.0] * 7, list(self._antennas))
    def play_move(self, move: Any, duration: float = 1.0) -> None:
        self.calls.append(("play_move", (move, duration)))

    imu = None


class _StubRecordedMoves:
    def __init__(self, library: str) -> None:
        self.library = library
        self._moves = {"wave": object(), "nod": object(), "happy": object()}
    def list_moves(self) -> list[str]: return list(self._moves)
    def get(self, name: str) -> Any: return self._moves[name]


def _install_reachy_stub() -> None:
    pkg = types.ModuleType("reachy_mini")
    pkg.ReachyMini = _StubReachyMini  # type: ignore[attr-defined]
    utils = types.ModuleType("reachy_mini.utils")
    utils.create_head_pose = lambda **kw: ("head_pose", kw)  # type: ignore[attr-defined]
    motion = types.ModuleType("reachy_mini.motion")
    recorded = types.ModuleType("reachy_mini.motion.recorded_move")
    recorded.RecordedMoves = _StubRecordedMoves  # type: ignore[attr-defined]
    sys.modules["reachy_mini"] = pkg
    sys.modules["reachy_mini.utils"] = utils
    sys.modules["reachy_mini.motion"] = motion
    sys.modules["reachy_mini.motion.recorded_move"] = recorded


@pytest.fixture
def reachy(monkeypatch: pytest.MonkeyPatch) -> Any:
    _install_reachy_stub()
    _StubReachyMini.instances.clear()
    from hack.robot.reachy_mini import ReachyMiniRobot
    robot = ReachyMiniRobot(host="test", port=0)
    asyncio.run(robot.connect())
    yield robot
    asyncio.run(robot.disconnect())


def test_reachy_mini_connect_sets_up_emotes_and_wakes(reachy: Any) -> None:
    stub = _StubReachyMini.instances[-1]
    assert stub.entered is True
    assert ("wake_up", None) in stub.calls
    # Emotes loaded from both libraries.
    assert "wave" in reachy._emotes


def test_reachy_mini_move_routes_to_goto_target_and_body_yaw(reachy: Any) -> None:
    stub = _StubReachyMini.instances[-1]
    asyncio.run(reachy.move(dx=0.1, dy=-0.2, dtheta=math.radians(10)))
    call = next(c for c in stub.calls if c[0] == "goto_target")
    kw = call[1]
    assert "head" in kw and "body_yaw" in kw and kw["duration"] == 0.3
    assert math.isclose(kw["body_yaw"], math.radians(10), abs_tol=1e-6)


def test_reachy_mini_grasp_release_antennas(reachy: Any) -> None:
    stub = _StubReachyMini.instances[-1]
    asyncio.run(reachy.grasp())
    asyncio.run(reachy.release())
    posts = [c[1] for c in stub.calls if c[0] == "set_target_antenna_joint_positions"]
    # grasp→non-zero, release→zeros.
    assert any(any(v != 0 for v in p) for p in posts)
    assert [0.0, 0.0] in posts


def test_reachy_mini_set_joint_dispatch(reachy: Any) -> None:
    stub = _StubReachyMini.instances[-1]
    asyncio.run(reachy.set_joint("body_rotation", 0.5))
    asyncio.run(reachy.set_joint("left_antenna", 0.3))
    asyncio.run(reachy.set_joint("head_pitch", 0.1))
    kinds = {c[0] for c in stub.calls}
    assert {"set_target_body_yaw", "set_target_antenna_joint_positions", "set_target_head_pose"} <= kinds
    with pytest.raises(ValueError):
        asyncio.run(reachy.set_joint("stewart_3", 0.0))


def test_reachy_mini_get_state_shape(reachy: Any) -> None:
    asyncio.run(reachy.set_joint("body_rotation", 0.25))
    state = asyncio.run(reachy.get_state())
    assert state.pose[2] == pytest.approx(0.25)
    assert "left_antenna" in state.joints and "right_antenna" in state.joints
    assert "head_pose" in state.extra


def test_reachy_mini_emote_known_and_unknown(reachy: Any) -> None:
    stub = _StubReachyMini.instances[-1]
    asyncio.run(reachy.emote("wave"))
    assert any(c[0] == "play_move" for c in stub.calls)
    with pytest.raises(ValueError):
        asyncio.run(reachy.emote("definitely-not-a-real-emote"))


# --------------------------------------------------------------------------
# Unitree Go2 stub — covers unitree_sdk2py.core.channel + go2.sport.sport_client
# + go2.video.video_client + idl.unitree_go.msg.dds_ .
# --------------------------------------------------------------------------


class _StubSportClient:
    instances: list["_StubSportClient"] = []
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.initialised = False
        self.timeout = 0.0
        _StubSportClient.instances.append(self)
    def SetTimeout(self, t: float) -> None: self.timeout = t
    def Init(self) -> None: self.initialised = True
    def Move(self, vx: float, vy: float, vyaw: float) -> None:
        self.calls.append(("Move", (vx, vy, vyaw)))
    def StopMove(self) -> None: self.calls.append(("StopMove", ()))
    def StandUp(self) -> None: self.calls.append(("StandUp", ()))
    def StandDown(self) -> None: self.calls.append(("StandDown", ()))
    def BalanceStand(self) -> None: self.calls.append(("BalanceStand", ()))
    def Damp(self) -> None: self.calls.append(("Damp", ()))
    def Hello(self) -> None: self.calls.append(("Hello", ()))
    def Sit(self) -> None: self.calls.append(("Sit", ()))
    def Stretch(self) -> None: self.calls.append(("Stretch", ()))
    def Dance1(self) -> None: self.calls.append(("Dance1", ()))
    def FrontFlip(self) -> None: self.calls.append(("FrontFlip", ()))


class _StubVideoClient:
    def SetTimeout(self, t: float) -> None: pass
    def Init(self) -> None: pass
    def GetImageSample(self) -> tuple[int, bytes]: return 0, b"\xff\xd8\xff\xd9"


class _StubChannelSubscriber:
    def __init__(self, topic: str, kind: type) -> None:
        self.topic = topic
    def Init(self, cb: Any, depth: int) -> None:
        # Immediately push a synthetic state so get_state() has data.
        msg = types.SimpleNamespace(
            position=(1.0, 2.0, 0.3),
            imu_state=types.SimpleNamespace(quaternion=(1.0, 0.0, 0.0, 0.0)),
            mode=1, gait_type=1, body_height=0.3,
            foot_force=(10.0, 11.0, 12.0, 13.0),
            velocity=(0.1, 0.0, 0.0),
        )
        cb(msg)


def _install_unitree_stub() -> None:
    root = types.ModuleType("unitree_sdk2py")
    core = types.ModuleType("unitree_sdk2py.core")
    channel = types.ModuleType("unitree_sdk2py.core.channel")
    channel.ChannelFactoryInitialize = lambda domain, iface: None  # type: ignore[attr-defined]
    channel.ChannelSubscriber = _StubChannelSubscriber  # type: ignore[attr-defined]
    go2 = types.ModuleType("unitree_sdk2py.go2")
    sport_mod = types.ModuleType("unitree_sdk2py.go2.sport")
    sport_client_mod = types.ModuleType("unitree_sdk2py.go2.sport.sport_client")
    sport_client_mod.SportClient = _StubSportClient  # type: ignore[attr-defined]
    video_mod = types.ModuleType("unitree_sdk2py.go2.video")
    video_client_mod = types.ModuleType("unitree_sdk2py.go2.video.video_client")
    video_client_mod.VideoClient = _StubVideoClient  # type: ignore[attr-defined]
    idl = types.ModuleType("unitree_sdk2py.idl")
    idl_ug = types.ModuleType("unitree_sdk2py.idl.unitree_go")
    idl_ug_msg = types.ModuleType("unitree_sdk2py.idl.unitree_go.msg")
    idl_ug_msg_dds = types.ModuleType("unitree_sdk2py.idl.unitree_go.msg.dds_")
    idl_ug_msg_dds.SportModeState_ = object  # type: ignore[attr-defined]
    for name, mod in [
        ("unitree_sdk2py", root),
        ("unitree_sdk2py.core", core),
        ("unitree_sdk2py.core.channel", channel),
        ("unitree_sdk2py.go2", go2),
        ("unitree_sdk2py.go2.sport", sport_mod),
        ("unitree_sdk2py.go2.sport.sport_client", sport_client_mod),
        ("unitree_sdk2py.go2.video", video_mod),
        ("unitree_sdk2py.go2.video.video_client", video_client_mod),
        ("unitree_sdk2py.idl", idl),
        ("unitree_sdk2py.idl.unitree_go", idl_ug),
        ("unitree_sdk2py.idl.unitree_go.msg", idl_ug_msg),
        ("unitree_sdk2py.idl.unitree_go.msg.dds_", idl_ug_msg_dds),
    ]:
        sys.modules[name] = mod


@pytest.fixture
def go2() -> Any:
    _install_unitree_stub()
    _StubSportClient.instances.clear()
    from hack.robot.unitree_go2 import UnitreeGo2Robot
    robot = UnitreeGo2Robot(network_iface="lo", command_duration_s=0.05, command_rate_hz=20)
    asyncio.run(robot.connect())
    yield robot
    asyncio.run(robot.disconnect())


def test_unitree_connect_stands(go2: Any) -> None:
    sport = _StubSportClient.instances[-1]
    assert sport.initialised
    names = [c[0] for c in sport.calls]
    assert "StandUp" in names and "BalanceStand" in names


def test_unitree_move_integrates_velocity_and_stops(go2: Any) -> None:
    sport = _StubSportClient.instances[-1]
    sport.calls.clear()
    asyncio.run(go2.move(dx=0.2, dy=0.0, dtheta=0.0))
    move_calls = [c for c in sport.calls if c[0] == "Move"]
    assert move_calls, "expected at least one Move call"
    vx = move_calls[0][1][0]
    assert vx == pytest.approx(0.2 / 0.05)  # disp / duration
    assert sport.calls[-1][0] == "StopMove"


def test_unitree_grasp_release_noop(go2: Any) -> None:
    sport = _StubSportClient.instances[-1]
    sport.calls.clear()
    asyncio.run(go2.grasp())
    asyncio.run(go2.release())
    assert sport.calls == []  # no SDK calls — quadruped has no gripper


def test_unitree_set_joint_rejected(go2: Any) -> None:
    with pytest.raises(NotImplementedError):
        asyncio.run(go2.set_joint("FR_0", 0.1))


def test_unitree_get_state_reads_latest_dds_sample(go2: Any) -> None:
    state = asyncio.run(go2.get_state())
    assert state.pose[0] == pytest.approx(1.0)
    assert state.pose[1] == pytest.approx(2.0)
    assert "body_height" in state.extra
    assert state.extra["foot_force"] == [10.0, 11.0, 12.0, 13.0]


def test_unitree_emote_safe_vs_acrobatic(go2: Any) -> None:
    sport = _StubSportClient.instances[-1]
    sport.calls.clear()
    asyncio.run(go2.emote("hello"))
    asyncio.run(go2.emote("dance"))
    assert ("Hello", ()) in sport.calls
    assert ("Dance1", ()) in sport.calls
    # Acrobatic is gated.
    with pytest.raises(PermissionError):
        asyncio.run(go2.emote("flip"))
    with pytest.raises(ValueError):
        asyncio.run(go2.emote("definitely-not-real"))


def test_unitree_emote_acrobatic_when_enabled() -> None:
    _install_unitree_stub()
    _StubSportClient.instances.clear()
    from hack.robot.unitree_go2 import UnitreeGo2Robot
    robot = UnitreeGo2Robot(network_iface="lo", allow_acrobatics=True, stand_on_connect=False)
    asyncio.run(robot.connect())
    try:
        sport = _StubSportClient.instances[-1]
        sport.calls.clear()
        asyncio.run(robot.emote("flip"))
        assert ("FrontFlip", ()) in sport.calls
    finally:
        asyncio.run(robot.disconnect())


def test_both_adapters_registered() -> None:
    from hack.robot import ADAPTERS
    assert "reachy_mini" in ADAPTERS
    assert "unitree_go2" in ADAPTERS
