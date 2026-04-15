from __future__ import annotations

from hack.robot.base import RobotAdapter, RobotState


class ROS2Robot(RobotAdapter):
    """ROS2 stub. Day-of: import rclpy, spin executor in a thread, publish to /cmd_vel etc.

    Left intentionally minimal so the day-of import doesn't fail outside ROS environments.
    """

    name = "ros2"

    def __init__(self, namespace: str = "") -> None:
        self.namespace = namespace
        self._node = None  # set in connect()

    async def connect(self) -> None:
        # DAYOF: R — import rclpy; rclpy.init(); create Node; spin executor in a daemon thread.
        raise NotImplementedError(
            "ROS2 adapter is a day-of stub: import rclpy, init context, spin executor in a thread."
        )

    # DAYOF: R — map each method to the actual topics/services exposed by the robot.
    # Common patterns: Twist to /cmd_vel; JointState publisher; action clients for named motions.
    async def move(self, dx: float, dy: float, dtheta: float) -> None: ...
    async def grasp(self) -> None: ...
    async def release(self) -> None: ...
    async def set_joint(self, name: str, value: float) -> None: ...
    async def get_state(self) -> RobotState:
        # DAYOF: R — subscribe to /joint_states (or equivalent) and populate RobotState.joints here.
        return RobotState()
    async def emote(self, label: str) -> None: ...
