from __future__ import annotations

import math

from rich.console import Console

from hack.robot.base import RobotAdapter, RobotState

_console = Console()


class MockRobot(RobotAdapter):
    name = "mock"

    def __init__(self) -> None:
        self._state = RobotState()

    async def move(self, dx: float, dy: float, dtheta: float) -> None:
        x, y, th = self._state.pose
        nx = x + dx * math.cos(th) - dy * math.sin(th)
        ny = y + dx * math.sin(th) + dy * math.cos(th)
        nth = (th + dtheta + math.pi) % (2 * math.pi) - math.pi
        self._state.pose = (nx, ny, nth)
        _console.print(f"[cyan]mock.move[/] dx={dx:+.2f} dy={dy:+.2f} dtheta={dtheta:+.2f} -> pose=({nx:.2f},{ny:.2f},{nth:.2f})")

    async def grasp(self) -> None:
        self._state.gripper_closed = True
        _console.print("[green]mock.grasp[/]")

    async def release(self) -> None:
        self._state.gripper_closed = False
        _console.print("[green]mock.release[/]")

    async def set_joint(self, name: str, value: float) -> None:
        self._state.joints[name] = value
        _console.print(f"[yellow]mock.set_joint[/] {name}={value:.3f}")

    async def get_state(self) -> RobotState:
        return self._state.model_copy(deep=True)

    async def emote(self, label: str) -> None:
        _console.print(f"[magenta]mock.emote[/] {label}")
