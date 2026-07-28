"""Stable metadata and recommended chains for user-created goal challenges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


LANES = ("food", "training", "recovery")
LANE_LABELS = {"food": "饮食挑战", "training": "训练挑战", "recovery": "恢复挑战"}
LEVELS = (
    {"name": "优秀", "color": "#2E9B62"},
    {"name": "精良", "color": "#2878C8"},
    {"name": "史诗", "color": "#7651B8"},
    {"name": "传说", "color": "#E0822B"},
)

TYPE_LABELS = {
    "training_volume": "训练总容量",
    "max_weight": "单动作最大重量",
    "training_sessions": "完成训练次数",
    "training_days": "累计训练天数",
    "training_streak": "连续训练天数",
    "exercise_reps": "动作总次数",
    "water_streak": "连续饮水达标",
    "nutrition_streak": "连续饮食达标",
    "body_target": "身体数值目标",
}

TYPE_LANES = {
    "training_volume": "training",
    "max_weight": "training",
    "training_sessions": "training",
    "training_days": "training",
    "training_streak": "training",
    "exercise_reps": "training",
    "water_streak": "recovery",
    "nutrition_streak": "food",
    "body_target": "recovery",
}

BODY_METRICS = {
    "weight": ("体重", "kg"),
    "bodyfat": ("体脂", "%"),
    "chest_cm": ("胸围", "cm"),
    "waist_cm": ("腰围", "cm"),
    "hip_cm": ("臀围", "cm"),
    "arm_cm": ("上臂围", "cm"),
    "thigh_cm": ("大腿围", "cm"),
    "calf_cm": ("小腿围", "cm"),
}


@dataclass(frozen=True)
class ChallengeTemplate:
    id: str
    chain_id: str
    title: str
    group: str
    lane: str
    challenge_type: str
    target: float
    unit: str
    level: int
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "template_id": self.id,
            "chain_id": self.chain_id,
            "title": self.title,
            "group": self.group,
            "lane": self.lane,
            "challenge_type": self.challenge_type,
            "target": self.target,
            "unit": self.unit,
            "level": self.level,
            "config": dict(self.config),
        }


def _chain(
    chain_id: str,
    group: str,
    lane: str,
    challenge_type: str,
    title: str,
    targets: tuple[float, ...],
    unit: str,
    **config: Any,
) -> list[ChallengeTemplate]:
    return [
        ChallengeTemplate(
            id=f"{chain_id}_{index}",
            chain_id=chain_id,
            title=title.format(target=target),
            group=group,
            lane=lane,
            challenge_type=challenge_type,
            target=target,
            unit=unit,
            level=index,
            config=dict(config),
        )
        for index, target in enumerate(targets)
    ]


def recommended_templates() -> tuple[ChallengeTemplate, ...]:
    """Return every chain level; visibility is decided from completed state."""
    templates: list[ChallengeTemplate] = []
    templates += _chain(
        "training_days", "新手起步", "training", "training_days",
        "30 天内累计训练 {target:g} 天", (5, 10, 20, 30), "天", window_days=30,
    )
    templates += _chain(
        "training_streak", "新手起步", "training", "training_streak",
        "连续训练 {target:g} 天", (3, 7, 14, 30), "天",
    )
    templates += _chain(
        "training_volume", "力量与增肌", "training", "training_volume",
        "30 天累计训练容量 {target:g} kg", (5000, 15000, 30000, 60000), "kg", window_days=30,
    )
    templates += _chain(
        "exercise_reps", "力量与增肌", "training", "exercise_reps",
        "周期内完成 {target:g} 次动作", (100, 300, 800, 1500), "次", window_days=30,
    )
    templates += _chain(
        "squat_max_weight", "力量与增肌", "training", "max_weight",
        "杠铃深蹲最大重量达到 {target:g} kg", (40, 60, 80, 100), "kg", action_id="杠铃深蹲", window_days=90,
    )
    templates += _chain(
        "water_streak", "饮食与补水", "recovery", "water_streak",
        "连续 {target:g} 天每天饮水 ≥ 2000 ml", (7, 14, 30, 90), "天", daily_target=2000,
    )
    templates += _chain(
        "protein_streak", "饮食与补水", "food", "nutrition_streak",
        "连续 {target:g} 天每天达到蛋白质目标", (7, 14, 30, 90), "天", indicator="protein",
    )
    templates += _chain(
        "carb_cycle_streak", "饮食与补水", "food", "nutrition_streak",
        "连续 {target:g} 天每天达成当日碳循环目标", (3, 7, 14, 30), "天", indicator="carb_cycle",
    )
    templates += _chain(
        "weight_target", "身体目标", "recovery", "body_target",
        "体重降低至 {target:g} kg", (80, 75, 70, 65), "kg", metric="weight", direction="at_most", window_days=90,
    )
    templates += _chain(
        "bodyfat_target", "身体目标", "recovery", "body_target",
        "体脂降低至 {target:g}%", (22, 20, 18, 15), "%", metric="bodyfat", direction="at_most", window_days=90,
    )
    templates += _chain(
        "waist_target", "身体目标", "recovery", "body_target",
        "腰围降低至 {target:g} cm", (90, 85, 80, 75), "cm", metric="waist_cm", direction="at_most", window_days=90,
    )
    return tuple(templates)


def challenge_type_label(challenge_type: str) -> str:
    return TYPE_LABELS.get(str(challenge_type), "目标挑战")


def level_info(level: Any) -> dict[str, Any]:
    try:
        index = max(0, min(3, int(level)))
    except (TypeError, ValueError):
        index = 0
    return dict(LEVELS[index])


__all__ = [
    "BODY_METRICS", "ChallengeTemplate", "LANES", "LANE_LABELS", "LEVELS",
    "TYPE_LABELS", "TYPE_LANES", "challenge_type_label", "level_info",
    "recommended_templates",
]
