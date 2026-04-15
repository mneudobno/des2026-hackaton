"""LeRobot adapter — maps our 6-method RobotAdapter onto LeRobot's
`connect / get_observation / send_action` interface.

LeRobot supports Reachy2, Unitree G1, SO100, Koch, HopeJR, OMX, EarthRover,
OpenARM, LeKiwi, and several teleop devices. If the event robot has a LeRobot
driver, this adapter is ~all we need.

Installed via the optional extra: `uv pip install -e ".[robot]"`.
Kept import-guarded so the base install works without lerobot.
"""

from __future__ import annotations

from typing import Any

from hack.robot.base import RobotAdapter, RobotState


class LeRobotAdapter(RobotAdapter):
    """Generic wrapper around any class implementing LeRobot's Robot protocol.

    Pass either an instantiated robot (`robot=<obj>`) or a dotted path
    (`robot_class="lerobot.robots.so100.SO100"`) with `config=<dict>`.
    """

    name = "lerobot"

    def __init__(
        self,
        robot: Any | None = None,
        robot_class: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        if robot is None and robot_class is None:
            raise ValueError("LeRobotAdapter needs either `robot=` or `robot_class=`")
        self._robot = robot
        self._robot_class = robot_class
        self._config = config or {}
        self._last_obs: dict[str, Any] = {}

    async def connect(self) -> None:
        if self._robot is None:
            assert self._robot_class
            mod_path, cls_name = self._robot_class.rsplit(".", 1)
            import importlib

            cls = getattr(importlib.import_module(mod_path), cls_name)
            self._robot = cls(config=self._config) if self._config else cls()
        # LeRobot's connect is synchronous — offload so we don't block the loop
        import asyncio

        await asyncio.to_thread(self._robot.connect)

    async def disconnect(self) -> None:
        if self._robot and hasattr(self._robot, "disconnect"):
            import asyncio

            await asyncio.to_thread(self._robot.disconnect)

    async def _send(self, action: dict[str, Any]) -> None:
        import asyncio

        assert self._robot is not None
        await asyncio.to_thread(self._robot.send_action, action)

    # --- RobotAdapter contract ---
    # LeRobot actions are robot-specific dicts. We translate our semantic
    # methods into likely key names; override in a subclass for quirks.

    # DAYOF: R — LeRobot action dicts are robot-specific; rename the keys here to match
    # the driver's expected keys (run `print(robot.action_features)` after connect).
    async def move(self, dx: float, dy: float, dtheta: float) -> None:
        await self._send({"dx": dx, "dy": dy, "dtheta": dtheta})

    async def grasp(self) -> None:
        await self._send({"gripper": 1.0})

    async def release(self) -> None:
        await self._send({"gripper": 0.0})

    async def set_joint(self, name: str, value: float) -> None:
        await self._send({name: value})

    async def get_state(self) -> RobotState:
        import asyncio

        assert self._robot is not None
        obs = await asyncio.to_thread(self._robot.get_observation)
        self._last_obs = obs if isinstance(obs, dict) else {"raw": obs}
        return RobotState(
            joints={k: float(v) for k, v in self._last_obs.items() if isinstance(v, (int, float))},
            extra=self._last_obs,
        )

    async def emote(self, label: str) -> None:
        # Most LeRobot drivers have no "emote" concept; expose it anyway so
        # the planner can try — some drivers (e.g. Reachy) accept named poses.
        await self._send({"emote": label})
