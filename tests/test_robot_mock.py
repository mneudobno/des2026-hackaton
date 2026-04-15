import asyncio

from hack.robot import make


def test_mock_cycles_all_methods():
    async def go():
        async with make("mock") as r:
            await r.move(0.1, 0.0, 0.0)
            await r.move(0.0, 0.0, 0.5)
            await r.set_joint("arm_lift", 0.3)
            await r.grasp()
            await r.release()
            await r.emote("hello")
            s = await r.get_state()
            assert not s.gripper_closed
            assert s.joints["arm_lift"] == 0.3
            assert s.pose != (0.0, 0.0, 0.0)

    asyncio.run(go())


def test_make_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        make("nonexistent")
