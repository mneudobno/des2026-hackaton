"""Mock VLM adapter — returns ground-truth observations from VirtualWorldRobot.

No API call, no latency, deterministic. Pluggable via `vlm.provider: mock`.
Day-of: swap to `vlm.provider: ollama` (or gemini/nim) and the real VLM takes
over with the same Observation schema.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from hack.models.base import VLMAdapter

if TYPE_CHECKING:
    from hack.rehearsal.virtual_world import VirtualWorldRobot


class MockVLM(VLMAdapter):
    """Produces Observation JSON from the virtual world's ground truth.

    Pass the `VirtualWorldRobot` instance at construction time. The runner
    does this when `provider: mock` and `real_mode` is False.
    """

    name = "mock"

    def __init__(self, world_robot: "VirtualWorldRobot" | None = None, **kwargs: Any) -> None:
        super().__init__(model="mock", **{k: v for k, v in kwargs.items() if k in ("base_url", "base_urls", "prompt", "timeout", "api_key_env")})
        self.world = world_robot

    async def describe(self, image_b64: str, override_prompt: str | None = None) -> str:
        """Return a JSON string matching the Observation schema."""
        if self.world is None:
            return json.dumps({"objects": [], "scene": "no virtual world attached", "salient_event": None})
        return json.dumps(self._compute_observation())

    def _compute_observation(self) -> dict[str, Any]:
        assert self.world is not None
        nearby = self.world._nearby_obstacles(max_dist=0.6)
        objects: list[dict[str, Any]] = []
        for obs in nearby:
            objects.append({
                "label": "obstacle",
                "rough_position": obs["position"],
                "confidence": max(0.5, 1.0 - obs["distance"]),
            })
        # Also report non-obstacle objects (goals, cubes, etc.)
        x, y, th = self.world.pose
        import math
        for obj in self.world.objects.values():
            if obj.is_obstacle or obj.held:
                continue
            d = math.hypot(obj.x - x, obj.y - y)
            if d > 0.8:
                continue
            dx_w = obj.x - x
            dy_w = obj.y - y
            cos_t, sin_t = math.cos(th), math.sin(th)
            dx_b = dx_w * cos_t + dy_w * sin_t
            dy_b = -dx_w * sin_t + dy_w * cos_t
            if dx_b > abs(dy_b) * 0.5:
                pos = "ahead"
            elif dx_b < -abs(dy_b) * 0.5:
                pos = "behind"
            else:
                pos = ""
            if dy_b > 0.05:
                pos += "-left" if pos else "left"
            elif dy_b < -0.05:
                pos += "-right" if pos else "right"
            objects.append({
                "label": obj.name,
                "rough_position": pos or "nearby",
                "confidence": max(0.5, 1.0 - d * 0.5),
            })
        # Scene summary.
        obstacle_count = sum(1 for o in objects if o["label"] == "obstacle")
        scene_parts = []
        if obstacle_count:
            scene_parts.append(f"{obstacle_count} obstacle(s) nearby")
        goal_names = [o["label"] for o in objects if o["label"] != "obstacle"]
        if goal_names:
            scene_parts.append(f"objects: {', '.join(goal_names[:3])}")
        scene = "; ".join(scene_parts) if scene_parts else "clear path"
        salient = None
        ahead_obstacles = [o for o in objects if o["label"] == "obstacle" and "ahead" in o["rough_position"]]
        if ahead_obstacles:
            salient = f"obstacle {ahead_obstacles[0]['rough_position']} at ~{nearby[0]['distance']:.2f}m"
        return {
            "objects": objects,
            "scene": scene,
            "salient_event": salient,
        }
