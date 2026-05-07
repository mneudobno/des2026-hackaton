from __future__ import annotations

from typing import Callable

from hack.robot.base import RobotAdapter, RobotState
from hack.robot.http import HTTPRobot
from hack.robot.mock import MockRobot
from hack.robot.ros2 import ROS2Robot

ADAPTERS: dict[str, Callable[..., RobotAdapter]] = {
    "mock": MockRobot,
    "http": HTTPRobot,
    "ros2": ROS2Robot,
}

# Optional SDK-backed adapters. Import modules unconditionally (they only
# *import* the real SDK at connect() time via asyncio.to_thread), so the class
# is discoverable even when the SDK isn't installed — `hack robot probe` can
# then report a clean error instead of "unknown adapter".
try:
    from hack.robot.lerobot_adapter import LeRobotAdapter
    ADAPTERS["lerobot"] = LeRobotAdapter
except ImportError:  # pragma: no cover
    pass

from hack.robot.reachy_mini import ReachyMiniRobot  # noqa: E402
ADAPTERS["reachy_mini"] = ReachyMiniRobot

from hack.robot.unitree_go2 import UnitreeGo2Robot  # noqa: E402
ADAPTERS["unitree_go2"] = UnitreeGo2Robot


def make(name: str, **kwargs: object) -> RobotAdapter:
    if name not in ADAPTERS:
        raise KeyError(f"unknown robot adapter: {name!r}; known: {sorted(ADAPTERS)}")
    return ADAPTERS[name](**kwargs)


__all__ = ["RobotAdapter", "RobotState", "ADAPTERS", "make"]
