from __future__ import annotations

import httpx

from hack.robot.base import RobotAdapter, RobotState


class HTTPRobot(RobotAdapter):
    """Generic HTTP-controlled robot. POST /command, GET /state.

    Day-of: confirm the actual route names and payload shapes, then tweak `_post`/`_get`.
    """

    name = "http"

    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _post(self, action: str, **payload: float | str) -> None:
        # DAYOF: R — confirm route "/command" and JSON body shape match the actual robot API.
        # DAYOF: R — add auth header here if the robot requires it (e.g. self._client.headers["X-Auth"]=...).
        assert self._client is not None
        r = await self._client.post("/command", json={"action": action, **payload})
        r.raise_for_status()

    async def move(self, dx: float, dy: float, dtheta: float) -> None:
        await self._post("move", dx=dx, dy=dy, dtheta=dtheta)

    async def grasp(self) -> None:
        await self._post("grasp")

    async def release(self) -> None:
        await self._post("release")

    async def set_joint(self, name: str, value: float) -> None:
        await self._post("set_joint", name=name, value=value)

    async def get_state(self) -> RobotState:
        # DAYOF: R — confirm "/state" path and response shape; map to RobotState fields.
        assert self._client is not None
        r = await self._client.get("/state")
        r.raise_for_status()
        return RobotState(**r.json())

    async def emote(self, label: str) -> None:
        await self._post("emote", label=label)
