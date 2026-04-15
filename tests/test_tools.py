import asyncio

from hack.agent.tools import ToolBox, ToolCall
from hack.robot import make


def test_toolbox_dispatches_to_robot():
    async def go():
        async with make("mock") as r:
            tb = ToolBox(robot=r)
            res = await tb.call(ToolCall(name="move", args={"dx": 0.1, "dy": 0.0, "dtheta": 0.0}))
            assert res.ok
            res = await tb.call(ToolCall(name="grasp"))
            assert res.ok
            res = await tb.call(ToolCall(name="remember", args={"key": "k", "value": "v"}))
            assert tb.memory["k"] == "v"
            res = await tb.call(ToolCall(name="bogus"))
            assert not res.ok

    asyncio.run(go())
