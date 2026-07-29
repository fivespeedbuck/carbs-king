"""Stable metadata and recommended chains for user-created goal challenges."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any


LANES = ("food", "training", "recovery")
LANE_LABELS = {"food": "饮食挑战", "training": "训练挑战", "recovery": "恢复挑战"}
LEVELS = (
    {"name": "优秀", "color": "#2E9B62"},
    {"name": "精良", "color": "#2878C8"},
    {"name": "史诗", "color": "#7651B8"},
    {"name": "传说", "color": "#E0822B"},
    {"name": "精锐", "color": "#C73B3B"},
)

TYPE_LABELS = {
    "training_volume": "训练总容量",
    "max_weight": "单动作最大重量",
    "training_sessions": "完成训练次数",
    "training_days": "累计训练天数",
    "training_streak": "连续训练天数",
    "exercise_reps": "动作总次数",
    "training_sets": "训练总组数",
    "heavy_sets": "大重量组数",
    "effective_training_days": "有效训练天数",
    "effective_training_streak": "有效连续打卡",
    "cardio_sessions": "有氧耐力次数",
    "time_window_sessions": "定点训练次数",
    "special_day_sessions": "特殊日训练次数",
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
    "training_sets": "training",
    "heavy_sets": "training",
    "effective_training_days": "training",
    "effective_training_streak": "training",
    "cardio_sessions": "training",
    "time_window_sessions": "training",
    "special_day_sessions": "training",
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

CUSTOM_CHALLENGE_CATALOG = (
    {
        "group": "基础累积",
        "items": (
            {"title": "训练总容量 (kg/lbs)", "description": "累计所有训练容量", "challenge_type": "training_volume", "unit": "kg"},
            {"title": "动作总容量 (kg/lbs)", "description": "特定动作累计容量", "challenge_type": "training_volume", "unit": "kg", "action_required": True},
            {"title": "训练总次数 (次)", "description": "累计完成训练会话", "challenge_type": "training_sessions", "unit": "次"},
            {"title": "动作总次数 (次)", "description": "特定动作累计次数", "challenge_type": "exercise_reps", "unit": "次", "action_required": True},
            {"title": "训练总组数 (组)", "description": "累计所有正式组", "challenge_type": "training_sets", "unit": "组"},
            {"title": "动作总组数 (组)", "description": "特定动作累计正式组", "challenge_type": "training_sets", "unit": "组", "action_required": True},
        ),
    },
    {
        "group": "强度突破",
        "items": (
            {"title": "最大重量 (kg/lbs)", "description": "单次最大重量", "challenge_type": "max_weight", "unit": "kg", "action_required": True},
            {"title": "大重量组数 (组)", "description": "超过指定重量的正式组数", "challenge_type": "heavy_sets", "unit": "组", "action_required": True, "min_weight_required": True},
        ),
    },
    {
        "group": "密度效率",
        "items": (
            {"title": "训练频次 (天)", "description": "有训练记录的天数", "challenge_type": "training_days", "unit": "天"},
            {"title": "有效训练频次 (天)", "description": "达到指定时长的训练天数", "challenge_type": "effective_training_days", "unit": "天", "duration_required": True},
            {"title": "连续打卡 (天)", "description": "连续训练天数", "challenge_type": "training_streak", "unit": "天"},
            {"title": "有效连续打卡 (天)", "description": "达到指定时长的连续打卡", "challenge_type": "effective_training_streak", "unit": "天", "duration_required": True},
            {"title": "有氧耐力 (次)", "description": "达到指定时长的有氧训练", "challenge_type": "cardio_sessions", "unit": "次", "duration_required": True},
        ),
    },
    {
        "group": "游戏化",
        "items": (
            {"title": "定点训练 (次)", "description": "指定时间段内完成训练", "challenge_type": "time_window_sessions", "unit": "次", "time_window_required": True},
            {"title": "特殊日训练 (次)", "description": "周末、工作日或指定日期训练", "challenge_type": "special_day_sessions", "unit": "次", "date_rule_required": True},
        ),
    },
)


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


def _number(profile: Mapping[str, Any], key: str, minimum: float, maximum: float) -> float | None:
    try:
        value = float(profile.get(key))
    except (TypeError, ValueError):
        return None
    return value if minimum <= value <= maximum else None


def _rounded(value: float, step: float) -> float:
    return round(round(value / step) * step, 2)


def _profile_basis(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = profile if isinstance(profile, Mapping) else {}
    sex = str(raw.get("sex") or "")
    habit = str(raw.get("activity_habit") or "")
    goal = str(raw.get("macro_goal") or "")
    return {
        "weight": _number(raw, "weight", 30, 300),
        "bodyfat": _number(raw, "bodyfat", 3, 60),
        "height": _number(raw, "height", 120, 230),
        "sex": sex if sex in {"男", "女"} else "",
        "activity_habit": habit if habit in {"久坐少动", "偶尔运动", "规律训练", "高频训练"} else "",
        "macro_goal": goal if goal in {"减脂", "保持", "增肌"} else "减脂",
    }


def _basis_text(basis: Mapping[str, Any], *keys: str) -> str:
    labels = {
        "weight": lambda value: f"体重 {value:g} kg",
        "bodyfat": lambda value: f"体脂 {value:g}%",
        "height": lambda value: f"身高 {value:g} cm",
        "sex": lambda value: f"性别 {value}",
        "activity_habit": str,
        "macro_goal": lambda value: f"{value}目标",
    }
    parts = [labels[key](basis[key]) for key in keys if basis.get(key) not in (None, "")]
    return f"依据：{' · '.join(parts)}" if parts else "通用起步目标；完善个人资料后会自动个性化"


def _variable_chain(
    chain_id: str,
    group: str,
    lane: str,
    challenge_type: str,
    titles: tuple[str, ...],
    targets: tuple[float, ...],
    unit: str,
    configs: tuple[dict[str, Any], ...],
) -> list[ChallengeTemplate]:
    return [
        ChallengeTemplate(
            id=f"{chain_id}_{index}",
            chain_id=chain_id,
            title=title,
            group=group,
            lane=lane,
            challenge_type=challenge_type,
            target=target,
            unit=unit,
            level=index,
            config=dict(config),
        )
        for index, (title, target, config) in enumerate(zip(titles, targets, configs, strict=True))
    ]


def recommended_templates(profile: Mapping[str, Any] | None = None) -> tuple[ChallengeTemplate, ...]:
    """Return stable personalized chains; current records only choose the visible level."""
    basis = _profile_basis(profile)
    weight = basis["weight"] or 70.0
    height = basis["height"]
    bodyfat = basis["bodyfat"]
    sex = basis["sex"]
    habit = basis["activity_habit"]
    goal = basis["macro_goal"]
    weekly_sessions = {"久坐少动": 2, "偶尔运动": 3, "规律训练": 4, "高频训练": 5}.get(habit, 3)
    month_sessions = weekly_sessions * 4
    training_basis = _basis_text(basis, "weight", "activity_habit", "macro_goal")
    templates: list[ChallengeTemplate] = []

    # User-curated fixed challenges.  Repeatable challenges return unchanged
    # after completion; milestones are shown once and never silently escalate.
    templates += _chain(
        "monthly_100t", "可重复完成", "training", "training_volume",
        "百吨巨兽 · 一个月累计 100000 kg", (100000,), "kg",
        calendar_month=True, repeatable_same=True,
    )
    templates += _chain(
        "seven_day_training_streak", "可重复完成", "training", "training_streak",
        "钢铁意志 · 连续 7 天训练", (7,), "天",
        window_days=7, repeatable_same=True,
    )
    templates += _chain(
        "monthly_20_training_days", "可重复完成", "training", "training_days",
        "月度劳模 · 一个月训练 20 天", (20,), "天",
        calendar_month=True, repeatable_same=True,
    )
    templates += _chain(
        "monthly_3000_reps", "可重复完成", "training", "exercise_reps",
        "3000 次挑战 · 一个月累计完成 3000 次动作", (3000,), "次",
        calendar_month=True, repeatable_same=True,
    )
    templates += _chain(
        "monthly_squat_20000", "可重复完成", "training", "training_volume",
        "深蹲大师 · 一个月内深蹲累计 20000 kg", (20000,), "kg",
        action_id="杠铃深蹲", calendar_month=True, repeatable_same=True,
    )
    templates += _chain(
        "monthly_effective_15", "可重复完成", "training", "effective_training_days",
        "硬核出勤 · 一个月有效训练 15 天", (15,), "天",
        min_duration_min=40, calendar_month=True, repeatable_same=True,
    )
    templates += _chain(
        "five_day_intense_streak", "可重复完成", "training", "effective_training_streak",
        "魔鬼周 · 连续 5 天高强度打卡", (5,), "天",
        min_duration_min=45, window_days=5, repeatable_same=True,
    )
    templates += _chain(
        "monthly_cardio_12", "可重复完成", "training", "cardio_sessions",
        "有氧达人 · 一个月完成 12 次 40 分钟有氧", (12,), "次",
        min_duration_min=40, calendar_month=True, repeatable_same=True,
    )

    templates += _chain(
        "starter_monthly_5", "新手起步", "training", "training_sessions",
        "初出茅庐 · 本月完成 5 次训练", (5,), "次", calendar_month=True, one_time=True,
    )
    templates += _chain(
        "starter_three_day_streak", "新手起步", "training", "training_streak",
        "三日连胜 · 连续训练 3 天", (3,), "天", window_days=3, one_time=True,
    )
    templates += _chain(
        "starter_volume_5000", "新手起步", "training", "training_volume",
        "力量初探 · 一个月累计 5000 kg 容量", (5000,), "kg", calendar_month=True, one_time=True,
    )
    templates += _chain(
        "starter_week_four_days", "新手起步", "training", "training_days",
        "第一次全勤 · 一周训练 4 天", (4,), "天", window_days=7, one_time=True,
    )
    templates += _chain(
        "starter_same_action_500", "新手起步", "training", "exercise_reps",
        "动作初体验 · 同一个动作累计完成 500 次", (500,), "次", any_action=True, window_days=90, one_time=True,
    )

    templates += _chain(
        "strength_monthly_50000", "力量与增肌", "training", "training_volume",
        "钢铁洪流 · 一个月累计 50000 kg 容量", (50000,), "kg", calendar_month=True, one_time=True,
    )
    templates += _chain(
        "strength_monthly_1000_reps", "力量与增肌", "training", "exercise_reps",
        "千锤百炼 · 一个月内完成 1000 次动作重复", (1000,), "次", calendar_month=True, one_time=True,
    )
    templates += _chain(
        "strength_monthly_200_sets", "力量与增肌", "training", "training_sets",
        "超级组魔王 · 一个月完成 200 个正式组", (200,), "组", calendar_month=True, one_time=True,
    )
    templates += _chain(
        "strength_monthly_chest_10000", "力量与增肌", "training", "training_volume",
        "推胸狂人 · 一个月推胸达到 10000 kg", (10000,), "kg", body_part="胸", calendar_month=True, one_time=True,
    )

    templates += _chain(
        "training_sessions", "新手起步", "training", "training_sessions",
        "别再鸽了 · 30 天内完成 {target:g} 次训练",
        tuple(weekly_sessions * level for level in (1, 2, 3, 4)),
        "次", window_days=30, rationale=training_basis, display_name="别再鸽了",
    )
    consistency_windows = (7, 14, 28, 56)
    consistency_targets = tuple(weekly_sessions * weeks for weeks in (1, 2, 4, 8))
    templates += _variable_chain(
        "training_consistency", "新手起步", "training", "training_days",
        tuple(f"三天打鱼？ · {days} 天内完成 {target:g} 个训练日" for days, target in zip(consistency_windows, consistency_targets, strict=True)),
        consistency_targets,
        "天",
        tuple({"window_days": days, "rationale": training_basis, "display_name": "三天打鱼？"} for days in consistency_windows),
    )

    volume_per_session = weight * {"减脂": 36, "保持": 40, "增肌": 45}[goal]
    monthly_volume = _rounded(volume_per_session * month_sessions, 500)
    volume_targets = tuple(max(500.0, _rounded(monthly_volume * factor, 500)) for factor in (0.40, 0.60, 0.80, 1.00))
    templates += _chain(
        "training_volume", "力量与增肌", "training", "training_volume",
        "这点重量不够看 · 30 天累计训练容量 {target:g} kg", volume_targets, "kg",
        window_days=30, rationale=training_basis, display_name="这点重量不够看",
    )
    monthly_reps = month_sessions * {"减脂": 60, "保持": 70, "增肌": 80}[goal]
    rep_targets = tuple(_rounded(monthly_reps * factor, 50) for factor in (0.25, 0.50, 0.75, 1.00))
    templates += _chain(
        "exercise_reps", "力量与增肌", "training", "exercise_reps",
        "手还没酸 · 30 天累计完成 {target:g} 次动作", rep_targets, "次",
        window_days=30, rationale=training_basis, display_name="手还没酸",
    )
    strength_goal_factor = {"减脂": 0.95, "保持": 1.00, "增肌": 1.05}[goal]
    strength_chains = {
        "男": (
            ("bench_press_max_weight", "杠铃卧推", (0.40, 0.60, 0.80, 1.00)),
            ("squat_max_weight", "杠铃深蹲", (0.50, 0.75, 1.00, 1.25)),
            ("deadlift_max_weight", "杠铃硬拉", (0.60, 0.90, 1.20, 1.50)),
        ),
        "女": (
            ("bench_press_max_weight", "杠铃卧推", (0.25, 0.40, 0.55, 0.70)),
            ("squat_max_weight", "杠铃深蹲", (0.35, 0.55, 0.75, 1.00)),
            ("deadlift_max_weight", "杠铃硬拉", (0.45, 0.70, 0.95, 1.20)),
        ),
    }
    strength_sex = sex if sex in strength_chains else "男"
    strength_names = {
        "bench_press_max_weight": "杠铃还没服",
        "squat_max_weight": "别只蹲空气",
        "deadlift_max_weight": "地板钉住了？",
    }
    for chain_id, action_name, ratios in strength_chains[strength_sex]:
        strength_targets = tuple(
            max(10.0, _rounded(weight * ratio * strength_goal_factor, 2.5))
            for ratio in ratios
        )
        templates += _chain(
            chain_id, "三大项力量", "training", "max_weight",
            f"{strength_names[chain_id]} · {action_name}最大重量达到 {{target:g}} kg", strength_targets, "kg",
            action_id=action_name, window_days=90,
            rationale=_basis_text(basis, "weight", "sex", "macro_goal"), display_name=strength_names[chain_id],
        )

    hydration_rate = 30 + {"久坐少动": 0, "偶尔运动": 3, "规律训练": 5, "高频训练": 7}.get(habit, 3)
    hydration_rate += 2 if goal == "增肌" else 0
    daily_water = max(1500.0, _rounded(weight * hydration_rate, 100))
    templates += _chain(
        "water_streak", "饮食与补水", "recovery", "water_streak",
        f"水杯又失踪了 · 连续 {{target:g}} 天每天饮水 ≥ {daily_water:g} ml", (7, 14, 30, 90), "天",
        daily_target=daily_water, rationale=_basis_text(basis, "weight", "activity_habit"), display_name="水杯又失踪了",
    )
    lean_mass = weight * (1 - bodyfat / 100) if bodyfat is not None else None
    protein_target = _rounded(lean_mass * {"减脂": 2.2, "保持": 2.0, "增肌": 2.0}[goal], 5) if lean_mass else None
    protein_title = (
        f"鸡胸别白吃 · 连续 {{target:g}} 天蛋白质达到 {protein_target:g} g"
        if protein_target else "鸡胸别白吃 · 连续 {target:g} 天每天达到蛋白质目标"
    )
    protein_config: dict[str, Any] = {
        "indicator": "protein",
        "rationale": _basis_text(basis, "weight", "bodyfat", "macro_goal"),
        "display_name": "鸡胸别白吃",
    }
    if protein_target:
        protein_config["daily_target"] = protein_target
    templates += _chain(
        "protein_streak", "饮食与补水", "food", "nutrition_streak",
        protein_title, (7, 14, 30, 90), "天", **protein_config,
    )
    templates += _chain(
        "carb_cycle_streak", "饮食与补水", "food", "nutrition_streak",
        f"碳水别乱跑 · 连续 {{target:g}} 天达成{goal}碳循环目标", (3, 7, 14, 30), "天",
        indicator="carb_cycle", rationale=_basis_text(basis, "activity_habit", "macro_goal"), display_name="碳水别乱跑",
    )

    if sex and bodyfat is not None:
        bodyfat_targets_by_goal = {
            "男": {"减脂": (20, 18, 15, 12), "保持": (22, 20, 18, 15), "增肌": (24, 22, 20, 18)},
            "女": {"减脂": (28, 25, 22, 20), "保持": (30, 28, 25, 22), "增肌": (32, 30, 28, 25)},
        }
        bodyfat_targets = bodyfat_targets_by_goal[sex][goal]
        templates += _chain(
            "bodyfat_target", "身体目标", "recovery", "body_target",
            "腹肌还在加载 · 体脂调整至不高于 {target:g}%", bodyfat_targets, "%",
            metric="bodyfat", direction="at_most", window_days=90,
            rationale=_basis_text(basis, "sex", "bodyfat", "macro_goal"), display_name="腹肌还在加载",
        )
        if goal == "减脂":
            lean = weight * (1 - bodyfat / 100)
            weight_targets = tuple(_rounded(lean / (1 - target / 100), 0.5) for target in bodyfat_targets)
            templates += _chain(
                "weight_target", "身体目标", "recovery", "body_target",
                "秤先别得意 · 在尽量保留去脂体重下调整至 {target:g} kg", weight_targets, "kg",
                metric="weight", direction="at_most", window_days=90,
                rationale=_basis_text(basis, "weight", "bodyfat", "macro_goal"), display_name="秤先别得意",
            )
        elif goal == "增肌" and height is not None:
            bmi_targets = (21, 22, 23, 24) if sex == "男" else (20, 21, 22, 23)
            height_m = height / 100
            weight_targets = tuple(_rounded(bmi * height_m * height_m, 0.5) for bmi in bmi_targets)
            templates += _chain(
                "weight_target", "身体目标", "recovery", "body_target",
                "风别把你吹跑 · 体重稳步提升至 {target:g} kg", weight_targets, "kg",
                metric="weight", direction="at_least", window_days=90,
                rationale=_basis_text(basis, "height", "weight", "macro_goal"), display_name="风别把你吹跑",
            )

    if sex and height is not None:
        waist_ratios = (0.52, 0.50, 0.47, 0.44) if sex == "男" else (0.54, 0.51, 0.48, 0.45)
        waist_targets = tuple(_rounded(height * ratio, 0.5) for ratio in waist_ratios)
        templates += _chain(
            "waist_target", "身体目标", "recovery", "body_target",
            "裤腰先松口气 · 腰围调整至不高于 {target:g} cm", waist_targets, "cm",
            metric="waist_cm", direction="at_most", window_days=90,
            rationale=_basis_text(basis, "height", "sex", "macro_goal"), display_name="裤腰先松口气",
        )
        if goal == "增肌":
            arm_ratios = (0.18, 0.19, 0.20, 0.21) if sex == "男" else (0.15, 0.16, 0.17, 0.18)
            arm_targets = tuple(_rounded(height * ratio, 0.5) for ratio in arm_ratios)
            templates += _chain(
                "arm_target", "增肌围度", "recovery", "body_target",
                "袖口还很宽 · 上臂围提升至 {target:g} cm", arm_targets, "cm",
                metric="arm_cm", direction="at_least", window_days=90,
                rationale=_basis_text(basis, "height", "sex", "macro_goal"), display_name="袖口还很宽",
            )
    return tuple(templates)


def challenge_type_label(challenge_type: str) -> str:
    return TYPE_LABELS.get(str(challenge_type), "目标挑战")


def repeatable_template(chain: list[ChallengeTemplate], level: int) -> ChallengeTemplate:
    templates = sorted(chain, key=lambda item: item.level)
    if not templates or templates[-1].challenge_type == "body_target":
        raise ValueError("body target chains do not extend beyond their highest level")
    last = templates[-1]
    previous = templates[-2] if len(templates) > 1 else last
    step = max(1.0, last.target - previous.target)
    extra_levels = max(1, int(level) - last.level)
    target = last.target + step * extra_levels
    config = dict(last.config)
    challenge_type = last.challenge_type
    display_name = str(config.get("display_name") or "").strip()

    def named(description: str) -> str:
        return f"{display_name} · {description}" if display_name else description

    if challenge_type in {"training_sessions", "training_days"}:
        last_window = int(config.get("window_days", 30))
        previous_window = int(previous.config.get("window_days", last_window))
        window_step = max(7, last_window - previous_window)
        config["window_days"] = last_window + window_step * extra_levels
        noun = "次训练" if challenge_type == "training_sessions" else "个训练日"
        title = named(f"{config['window_days']} 天内完成 {target:g} {noun}")
    elif challenge_type == "training_streak":
        title = named(f"连续训练 {target:g} 天")
    elif challenge_type == "training_volume":
        title = named(f"{int(config.get('window_days', 30))} 天累计训练容量 {target:g} kg")
    elif challenge_type == "exercise_reps":
        title = named(f"周期内完成 {target:g} 次动作")
    elif challenge_type == "max_weight":
        title = named(f"{config.get('action_id', '指定动作')}最大重量达到 {target:g} kg")
    elif challenge_type == "water_streak":
        title = named(f"连续 {target:g} 天每天饮水 ≥ {float(config.get('daily_target', 2000)):g} ml")
    elif challenge_type == "nutrition_streak":
        indicator = str(config.get("indicator") or "protein")
        target_name = "当日碳循环目标" if indicator == "carb_cycle" else "蛋白质目标"
        title = named(f"连续 {target:g} 天每天达到{target_name}")
    else:
        title = f"{last.title} · {target:g} {last.unit}"
    return ChallengeTemplate(
        id=f"{last.chain_id}_{level}",
        chain_id=last.chain_id,
        title=title,
        group=last.group,
        lane=last.lane,
        challenge_type=challenge_type,
        target=target,
        unit=last.unit,
        level=int(level),
        config=config,
    )


def level_info(level: Any) -> dict[str, Any]:
    try:
        raw_level = max(0, int(level))
    except (TypeError, ValueError):
        raw_level = 0
    info = dict(LEVELS[min(4, raw_level)])
    if raw_level > 4:
        info["name"] = f"精锐 +{raw_level - 4}"
    return info


__all__ = [
    "BODY_METRICS", "CUSTOM_CHALLENGE_CATALOG", "ChallengeTemplate", "LANES", "LANE_LABELS", "LEVELS",
    "TYPE_LABELS", "TYPE_LANES", "challenge_type_label", "level_info",
    "recommended_templates", "repeatable_template",
]
