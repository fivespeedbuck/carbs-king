"""Static achievement definitions for Carbs King."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


AchievementTier = Literal["bronze", "silver", "gold", "diamond"]
AchievementKind = Literal["ladder", "hidden"]


@dataclass(frozen=True, slots=True)
class AchievementDefinition:
    id: str
    title: str
    description: str
    metric: str
    target: float
    tier: AchievementTier | None
    kind: AchievementKind = "ladder"
    hidden: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_LADDERS: tuple[tuple[str, str, str, str, tuple[float, float, float, float]], ...] = (
    ("training_days", "训练天数", "在不同日期完成真实训练。", "training_days", (1, 7, 30, 100)),
    ("training_sessions", "训练场次", "完成有效训练场次。", "training_sessions", (1, 10, 50, 150)),
    ("formal_sets", "正式组数", "完成非热身的结构化正式组。", "formal_sets", (5, 50, 300, 1000)),
    ("volume_kg", "训练容量", "累计结构化训练容量。", "volume_kg", (1000, 10000, 50000, 150000)),
    ("duration_min", "训练时长", "累计有效训练分钟数。", "duration_min", (30, 300, 1500, 5000)),
    ("unique_exercises", "动作覆盖", "在已完成训练中使用不同动作。", "unique_exercises", (3, 10, 25, 50)),
    ("body_part_variety", "部位覆盖", "根据真实记录覆盖不同训练部位。", "body_part_variety", (2, 4, 6, 8)),
    ("training_streak", "规律训练周", "每周完成至少两天训练并保持周连续。", "training_week_streak", (1, 4, 12, 26)),
    ("completed_reps", "完成次数", "累计完成正式组中的动作次数。", "completed_reps", (50, 500, 3000, 10000)),
    ("loaded_sets", "负重训练", "累计完成重量大于零的正式组。", "loaded_sets", (5, 50, 300, 1000)),
    ("bodyweight_sets", "自重训练", "累计完成重量为零的正式组。", "bodyweight_sets", (5, 30, 100, 300)),
    ("training_weeks", "活跃训练周", "累计在不同自然周完成训练。", "training_weeks", (1, 4, 12, 36)),
    ("training_months", "活跃训练月", "累计在不同月份完成训练。", "training_months", (1, 3, 6, 12)),
    ("multi_part_sessions", "复合训练", "单次训练覆盖至少两个身体部位。", "multi_part_sessions", (1, 5, 20, 60)),
    ("chest_days", "胸部训练", "累计完成包含胸部的训练日。", "chest_days", (1, 5, 20, 60)),
    ("back_days", "背部训练", "累计完成包含背部的训练日。", "back_days", (1, 5, 20, 60)),
    ("shoulder_days", "肩部训练", "累计完成包含肩部的训练日。", "shoulder_days", (1, 5, 20, 60)),
    ("leg_days", "腿部训练", "累计完成包含腿部的训练日。", "leg_days", (1, 5, 20, 60)),
    ("arm_days", "手臂训练", "累计完成包含二头或三头的训练日。", "arm_days", (1, 5, 20, 60)),
    ("core_days", "核心训练", "累计完成包含腹部或核心的训练日。", "core_days", (1, 5, 20, 60)),
    ("nutrition_logged_days", "饮食记录", "记录餐食或每日营养总量。", "nutrition_logged_days", (1, 7, 30, 100)),
    ("meal_entries", "餐食条目", "累计保存真实餐食条目。", "meal_entries", (3, 30, 150, 500)),
    ("unique_foods", "食物探索", "累计记录不同名称的食物。", "unique_foods", (3, 15, 40, 80)),
    ("breakfast_days", "早餐记录", "累计记录早餐的天数。", "breakfast_days", (1, 7, 30, 100)),
    ("lunch_days", "午餐记录", "累计记录午餐的天数。", "lunch_days", (1, 7, 30, 100)),
    ("dinner_days", "晚餐记录", "累计记录晚餐的天数。", "dinner_days", (1, 7, 30, 100)),
    ("preworkout_days", "练前记录", "累计记录练前餐的天数。", "preworkout_days", (1, 5, 20, 60)),
    ("postworkout_days", "练后记录", "累计记录练后餐的天数。", "postworkout_days", (1, 5, 20, 60)),
    ("snack_days", "加餐记录", "累计如实记录偷吃或加餐的天数。", "snack_days", (1, 5, 20, 60)),
    ("macro_complete_days", "营养完整", "累计同时记录热量、碳水、蛋白质和脂肪的天数。", "macro_complete_days", (1, 7, 30, 100)),
    ("protein_logged_days", "蛋白质记录", "累计记录蛋白质摄入的天数。", "protein_logged_days", (1, 7, 30, 100)),
    ("carb_cycle_days", "碳循环记录", "累计明确记录高碳、中碳或低碳日。", "carb_cycle_days", (1, 7, 30, 100)),
    ("water_goal_days", "饮水达标", "单日饮水达到 2000 毫升。", "water_goal_days", (1, 7, 30, 100)),
    ("water_logged_days", "饮水记录", "累计记录实际饮水量的天数。", "water_logged_days", (1, 7, 30, 100)),
    ("water_liters", "累计饮水", "累计记录饮水升数。", "water_liters", (2, 20, 100, 300)),
    ("water_streak", "连续饮水记录", "连续记录实际饮水量。", "water_streak", (2, 7, 21, 60)),
    ("sleep_logged_days", "睡眠记录", "记录睡眠时长或睡眠细节。", "sleep_logged_days", (1, 7, 30, 100)),
    ("sleep_duration_days", "睡眠时长", "累计记录明确睡眠时长的天数。", "sleep_duration_days", (1, 7, 30, 100)),
    ("restful_sleep_days", "充足睡眠", "累计睡眠达到七至九小时的天数。", "restful_sleep_days", (1, 7, 30, 100)),
    ("sleep_hours", "累计睡眠", "累计记录的睡眠小时数。", "sleep_hours", (7, 50, 200, 700)),
    ("sleep_streak", "连续睡眠记录", "连续记录睡眠信息。", "sleep_streak", (2, 7, 21, 60)),
    ("recovery_logged_days", "恢复记录", "累计记录饮水、睡眠或疲劳状态的天数。", "recovery_logged_days", (1, 7, 30, 100)),
    ("measurement_days", "身体测量", "保存明确标记的身体测量。", "measurement_days", (1, 4, 12, 36)),
    ("weight_measurement_days", "体重测量", "累计明确记录体重的天数。", "weight_measurement_days", (1, 4, 12, 36)),
    ("bodyfat_measurement_days", "体脂测量", "累计明确记录体脂率的天数。", "bodyfat_measurement_days", (1, 4, 12, 36)),
    ("circumference_measurement_days", "围度测量", "累计明确记录身体围度的天数。", "circumference_measurement_days", (1, 4, 12, 36)),
    ("measurement_months", "月度复测", "累计在不同月份完成身体测量。", "measurement_months", (1, 3, 6, 12)),
    ("combined_measurement_days", "组合测量", "同一天明确记录至少两项身体指标。", "combined_measurement_days", (1, 3, 8, 20)),
)

_TIER_NAMES: tuple[AchievementTier, ...] = ("bronze", "silver", "gold", "diamond")
_TIER_LABELS: dict[AchievementTier, str] = {
    "bronze": "铜",
    "silver": "银",
    "gold": "金",
    "diamond": "钻石",
}


LADDER_ACHIEVEMENTS: tuple[AchievementDefinition, ...] = tuple(
    AchievementDefinition(
        id=f"{base_id}_{tier}",
        title=f"{title}·{_TIER_LABELS[tier]}",
        description=description,
        metric=metric,
        target=targets[index],
        tier=tier,
    )
    for base_id, title, description, metric, targets in _LADDERS
    for index, tier in enumerate(_TIER_NAMES)
)

HIDDEN_ACHIEVEMENTS: tuple[AchievementDefinition, ...] = (
    AchievementDefinition(
        id="hidden_double_session_day",
        title="复合搭档",
        description="单次训练覆盖至少两个身体部位。",
        metric="double_session_day",
        target=1,
        tier=None,
        kind="hidden",
        hidden=True,
    ),
    AchievementDefinition(
        id="hidden_seven_day_training_streak",
        title="规律一周",
        description="同一自然周至少完成两天训练。",
        metric="seven_day_training_streak",
        target=1,
        tier=None,
        kind="hidden",
        hidden=True,
    ),
    AchievementDefinition(
        id="hidden_hundred_k_volume",
        title="十万容量",
        description="累计结构化训练容量达到十万公斤。",
        metric="hundred_k_volume",
        target=1,
        tier=None,
        kind="hidden",
        hidden=True,
    ),
    AchievementDefinition(
        id="hidden_all_body_parts",
        title="全身地图",
        description="覆盖至少八个不同训练部位。",
        metric="all_body_parts",
        target=1,
        tier=None,
        kind="hidden",
        hidden=True,
    ),
    AchievementDefinition(
        id="hidden_balanced_week",
        title="均衡一周",
        description="任意七天内稳定记录训练、饮食、饮水和睡眠。",
        metric="balanced_week",
        target=1,
        tier=None,
        kind="hidden",
        hidden=True,
    ),
    AchievementDefinition(
        id="hidden_comeback",
        title="重新开练",
        description="间隔至少十四天后再次完成训练。",
        metric="comeback",
        target=1,
        tier=None,
        kind="hidden",
        hidden=True,
    ),
    AchievementDefinition(
        id="hidden_marathon_session",
        title="完整一练",
        description="单次训练完成至少三个正式组。",
        metric="marathon_session",
        target=1,
        tier=None,
        kind="hidden",
        hidden=True,
    ),
    AchievementDefinition(
        id="hidden_perfect_record_day",
        title="完整记录日",
        description="同一天记录饮食、训练、饮水、睡眠和身体测量。",
        metric="perfect_record_day",
        target=1,
        tier=None,
        kind="hidden",
        hidden=True,
    ),
)

ACHIEVEMENTS: tuple[AchievementDefinition, ...] = LADDER_ACHIEVEMENTS + HIDDEN_ACHIEVEMENTS


def achievement_definitions() -> tuple[AchievementDefinition, ...]:
    """Return all definitions in stable display order."""
    return ACHIEVEMENTS


__all__ = [
    "ACHIEVEMENTS",
    "HIDDEN_ACHIEVEMENTS",
    "LADDER_ACHIEVEMENTS",
    "AchievementDefinition",
    "AchievementKind",
    "AchievementTier",
    "achievement_definitions",
]
