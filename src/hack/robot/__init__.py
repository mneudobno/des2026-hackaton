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


def make(name: str, **kwargs: object) -> RobotAdapter:
    if name not in ADAPTERS:
        raise KeyError(f"unknown robot adapter: {name!r}; known: {sorted(ADAPTERS)}")
    return ADAPTERS[name](**kwargs)


__all__ = ["RobotAdapter", "RobotState", "ADAPTERS", "make"]
