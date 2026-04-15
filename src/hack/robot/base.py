from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class RobotState(BaseModel):
    pose: tuple[float, float, float] = Field(default=(0.0, 0.0, 0.0), description="x, y, theta in body frame")
    joints: dict[str, float] = Field(default_factory=dict)
    gripper_closed: bool = False
    battery: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class RobotAdapter(ABC):
    """Six-method contract every adapter must implement.

    Day-of: subclass this, map to the given SDK, register in ADAPTERS.
    Never widen this surface mid-hackathon — extend via `extra` on RobotState.
    """

    name: str = "abstract"

    async def __aenter__(self) -> "RobotAdapter":
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    @abstractmethod
    async def move(self, dx: float, dy: float, dtheta: float) -> None:
        """Body-frame translation (m) + yaw (rad). Adapters clamp to safety limits."""

    @abstractmethod
    async def grasp(self) -> None: ...

    @abstractmethod
    async def release(self) -> None: ...

    @abstractmethod
    async def set_joint(self, name: str, value: float) -> None: ...

    @abstractmethod
    async def get_state(self) -> RobotState: ...

    @abstractmethod
    async def emote(self, label: str) -> None:
        """LEDs / sounds / canned poses. No-op is acceptable."""
