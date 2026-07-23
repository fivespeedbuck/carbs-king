"""Pure analytics page model construction with no Flet dependency."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
import math
from typing import Any

from analytics_service import (
    build_period_series,
    calendar_day_summary,
    normalize_body_part,
    summarize_daily_training,
)


PERIOD_OPTIONS = (7, 30, 90)
VIEW_TABS = ("趋势", "月历", "汇总")
CHART_OPTIONS = (
    ("weight", "体重"),
    ("bodyfat", "体脂"),
    ("circumference", "围度"),
    ("diet", "饮食"),
    ("training", "训练"),
    ("recovery", "恢复"),
)
BODY_PART_FILTERS = ("全部", "胸", "背", "肩", "腿", "二头", "三头", "腹", "有氧")
CIRCUMFERENCE_KEYS = (
    ("waist_cm", "腰围"),
    ("arm_cm", "上臂围"),
    ("chest_cm", "胸围"),
    ("hip_cm", "臀围"),
    ("thigh_cm", "大腿围"),
    ("calf_cm", "小腿围"),
)

TREND_METRICS = {
    "weight": (("weight_kg", "体重"),),
    "bodyfat": (("bodyfat_percent", "体脂"),),
    "circumference": CIRCUMFERENCE_KEYS,
    "diet": (("kcal", "每日热量"), ("carb", "每日碳水"), ("protein", "每日蛋白"), ("fat", "每日脂肪")),
    "training": (
        ("volume_kg", "力量总容量"),
        ("formal_sets", "力量完成组数"),
        ("duration_min", "训练时长"),
        ("cardio_duration_min", "有氧时长"),
        ("distance_km", "有氧距离"),
    ),
    "recovery": (("sleep_hours", "睡眠时长"), ("water_ml", "饮水量")),
}

DEFAULT_TREND_METRIC = {
    "weight": "weight_kg",
    "bodyfat": "bodyfat_percent",
    "circumference": "waist_cm",
    "diet": "kcal",
    "training": "volume_kg",
    "recovery": "sleep_hours",
}

TEXT = "#182420"
SUB = "#4F5D58"
PRIMARY = "#116E59"
PRIMARY_SOFT = "#F1F7F5"
BORDER = "#CDD9D5"
SURFACE = "#F7FAF8"
WHITE = "#FFFFFF"
ORANGE = "#B96A18"
RED = "#D64545"
BLUE = "#2F80ED"
PURPLE = "#7C3AED"

# Calendar calorie bands use the target stored on the same historical day.
# Exact boundaries belong to the more favorable lower band:
# <80% gray, 80%-100% green, >100%-120% yellow, >120% red.
CALENDAR_KCAL_RATIO_THRESHOLDS = (0.8, 1.0, 1.2)
CALENDAR_KCAL_BAND_MISSING = "missing_target"
CALENDAR_KCAL_BAND_BELOW = "below_80"
CALENDAR_KCAL_BAND_TARGET = "target_80_100"
CALENDAR_KCAL_BAND_OVER = "over_100_120"
CALENDAR_KCAL_BAND_HIGH = "over_120"


@dataclass(frozen=True)
class DataPageConfig:
    """Small immutable state needed to rebuild the reusable data page."""

    period_days: int = 7
    active_tab: str = "趋势"
    chart_kind: str = "weight"
    body_part_filter: str = "全部"
    selected_date: str | None = None
    calendar_month: str | None = None
    action_trend_open: bool = False
    selected_exercise: str | None = None
    raw_expanded: bool = False
    metric_key: str | None = None
    selected_trend_date: str | None = None


def _number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _has_record_content(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    for value in record.values():
        if value in (None, "", [], {}):
            continue
        return True
    return False


def _has_food(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    meals = record.get("meals")
    if isinstance(meals, Mapping) and any(
        any(isinstance(item, Mapping) for item in _list(items)) for items in meals.values()
    ):
        return True
    total = _mapping(record.get("daily_total"))
    return any(_number(total.get(key)) not in (None, 0) for key in ("kcal", "carb", "protein", "fat"))


def _date_value(value: str | date) -> date:
    return date.fromisoformat(value) if isinstance(value, str) else value


def _month_anchor(value: str | None, fallback: date) -> date:
    if not value:
        return fallback.replace(day=1)
    try:
        return date.fromisoformat(f"{value}-01").replace(day=1)
    except (TypeError, ValueError):
        return fallback.replace(day=1)


def _shift_month(value: date, delta: int) -> date:
    month_index = value.year * 12 + value.month - 1 + delta
    return date(month_index // 12, month_index % 12 + 1, 1)


def _month_dates(month_anchor: date) -> list[date | None]:
    first = month_anchor.replace(day=1)
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = next_month - timedelta(days=1)
    days: list[date | None] = [None] * first.weekday()
    days.extend(first + timedelta(days=offset) for offset in range(last.day))
    while len(days) % 7:
        days.append(None)
    return days


def _actual_month_dates(month_anchor: date) -> list[date]:
    return [item for item in _month_dates(month_anchor) if item is not None and item.month == month_anchor.month]


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _explicit_circumferences(record: Any) -> dict[str, float | None]:
    profile = _mapping(_mapping(record).get("profile"))
    measurement = _mapping(profile.get("measurement"))
    circumference = _mapping(profile.get("circumference"))
    measured_at = str(
        measurement.get("measured_at")
        or circumference.get("measured_at")
        or profile.get("measured_at")
        or ""
    ).strip()
    if not measured_at:
        return {key: None for key, _ in CIRCUMFERENCE_KEYS}
    result = {}
    for key, _ in CIRCUMFERENCE_KEYS:
        value = _number(measurement.get(key))
        if value is None:
            value = _number(circumference.get(key))
        if value is None and measured_at:
            value = _number(profile.get(key))
        result[key] = value
    return result


def _raw_sessions(record: Any) -> list[Mapping[str, Any]]:
    training = _mapping(_mapping(record).get("training"))
    candidates = [item for item in _list(training.get("sessions")) if isinstance(item, Mapping)]
    current = training.get("session")
    if isinstance(current, Mapping):
        candidates.append(current)
    result: list[Mapping[str, Any]] = []
    positions: dict[str, int] = {}
    for candidate in candidates:
        identity = str(candidate.get("id") or "")
        key = f"id:{identity}" if identity else f"value:{candidate!r}"
        if key in positions:
            result[positions[key]] = candidate
        else:
            positions[key] = len(result)
            result.append(candidate)
    return result


def _completed_sets(record: Any, record_date: str = "") -> list[dict[str, Any]]:
    result = []
    for session in _raw_sessions(record):
        for exercise in _list(session.get("exercises")):
            if not isinstance(exercise, Mapping):
                continue
            if str(exercise.get("recording_mode") or "strength").strip().lower() != "strength":
                continue
            name = str(exercise.get("name") or "").strip()
            body_part = normalize_body_part(exercise.get("body_part"))
            for index, training_set in enumerate(_list(exercise.get("sets")), 1):
                if not isinstance(training_set, Mapping):
                    continue
                reps = _number(training_set.get("reps"))
                weight = _number(training_set.get("weight_kg", training_set.get("weight")))
                if (
                    not bool(training_set.get("completed"))
                    or bool(training_set.get("warmup", training_set.get("is_warmup", False)))
                    or reps is None
                    or reps <= 0
                    or weight is None
                    or weight < 0
                ):
                    continue
                result.append({
                    "date": record_date,
                    "exercise": name,
                    "body_part": body_part,
                    "set_index": index,
                    "weight_kg": weight,
                    "reps": reps,
                    "volume_kg": round(weight * reps, 2),
                    "epley_1rm_kg": round(weight * (1 + reps / 30), 2),
                })
    return result


def _training_week_totals(series: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    weeks: dict[tuple[int, int], dict[str, Any]] = {}
    for point in series:
        point_date = date.fromisoformat(str(point["date"]))
        iso_year, iso_week, _ = point_date.isocalendar()
        key = (iso_year, iso_week)
        entry = weeks.setdefault(key, {"label": f"{iso_year}-W{iso_week:02d}", "sets": 0, "volume_kg": 0.0})
        training = _mapping(point.get("training"))
        entry["sets"] += int(training.get("formal_sets") or 0)
        entry["volume_kg"] = round(entry["volume_kg"] + (_number(training.get("volume_kg")) or 0), 2)
    return list(weeks.values())


def _best_lifts(records: Mapping[str, Any], series: list[Mapping[str, Any]], body_part_filter: str) -> list[dict[str, Any]]:
    dates = {str(point["date"]) for point in series}
    best: dict[tuple[str, str], dict[str, Any]] = {}
    selected_part = "" if body_part_filter == "全部" else normalize_body_part(body_part_filter)
    for record_date in sorted(dates):
        record = records.get(record_date)
        for item in _completed_sets(record, record_date):
            if selected_part and item["body_part"] != selected_part:
                continue
            key = (item["body_part"], item["exercise"])
            candidate = dict(item)
            current = best.get(key)
            if current is None or (candidate["epley_1rm_kg"], candidate["weight_kg"], candidate["reps"]) > (
                current["epley_1rm_kg"],
                current["weight_kg"],
                current["reps"],
            ):
                best[key] = candidate
    return sorted(best.values(), key=lambda item: item["epley_1rm_kg"], reverse=True)[:8]


def _exercise_sets(records: Mapping[str, Any], series: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    dates = {str(point["date"]) for point in series}
    result: list[dict[str, Any]] = []
    for record_date in sorted(dates):
        result.extend(_completed_sets(records.get(record_date), record_date))
    return result


def _exercise_options(completed_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}
    for item in completed_sets:
        name = str(item.get("exercise") or "").strip()
        if not name:
            continue
        option = options.setdefault(name, {"exercise": name, "body_parts": [], "set_count": 0, "latest_date": ""})
        part = str(item.get("body_part") or "").strip()
        if part and part not in option["body_parts"]:
            option["body_parts"].append(part)
        option["set_count"] += 1
        option["latest_date"] = max(str(option["latest_date"] or ""), str(item.get("date") or ""))
    return sorted(options.values(), key=lambda item: (item["latest_date"], item["set_count"], item["exercise"]), reverse=True)


def _exercise_trend(records: Mapping[str, Any], series: list[Mapping[str, Any]], selected_exercise: str | None) -> dict[str, Any]:
    completed_sets = _exercise_sets(records, series)
    options = _exercise_options(completed_sets)
    selected = selected_exercise if any(item["exercise"] == selected_exercise for item in options) else (
        options[0]["exercise"] if options else None
    )
    if selected is None:
        return {
            "open": False,
            "selected_exercise": None,
            "options": [],
            "points": [],
            "recorded_count": 0,
            "best_weight_kg": None,
            "best_reps": None,
            "best_epley_1rm_kg": None,
            "empty_action_label": "+记录训练",
        }
    points = []
    for point in series:
        record_date = str(point["date"])
        sets = [
            item for item in completed_sets
            if item["date"] == record_date and item["exercise"] == selected
        ]
        if not sets:
            points.append({"date": record_date, "weight_kg": None, "reps": None, "epley_1rm_kg": None, "label": "未记录"})
            continue
        best = max(sets, key=lambda item: (item["epley_1rm_kg"], item["weight_kg"], item["reps"]))
        points.append({
            "date": record_date,
            "weight_kg": best["weight_kg"],
            "reps": best["reps"],
            "epley_1rm_kg": best["epley_1rm_kg"],
            "label": f"{best['weight_kg']:g} x {best['reps']:g}｜1RM {best['epley_1rm_kg']:g}",
        })
    recorded = [item for item in points if item["epley_1rm_kg"] is not None]
    return {
        "open": bool(selected_exercise or options) and bool(selected_exercise is not None or options),
        "selected_exercise": selected,
        "options": options,
        "points": points,
        "recorded_count": len(recorded),
        "best_weight_kg": max((item["weight_kg"] for item in recorded if item["weight_kg"] is not None), default=None),
        "best_reps": max((item["reps"] for item in recorded if item["reps"] is not None), default=None),
        "best_epley_1rm_kg": max((item["epley_1rm_kg"] for item in recorded if item["epley_1rm_kg"] is not None), default=None),
        "empty_action_label": "+记录训练",
    }


def _month_summary(records: Mapping[str, Any], month_anchor: date) -> dict[str, Any]:
    training_days = 0
    training_duration = 0.0
    formal_sets = 0
    kcal_values: list[float] = []
    for item_date in _actual_month_dates(month_anchor):
        key = item_date.isoformat()
        record = records.get(key)
        training = summarize_daily_training(record, key)
        if training["has_training"]:
            training_days += 1
            training_duration += _number(training.get("duration_min")) or 0
            formal_sets += int(training.get("formal_sets") or 0)
        if _has_food(record):
            kcal = _number(_mapping(_mapping(record).get("daily_total")).get("kcal"))
            if kcal is not None:
                kcal_values.append(kcal)
    return {
        "month": month_anchor.strftime("%Y-%m"),
        "training_days": training_days or None,
        "training_duration_min": round(training_duration, 2) if training_days else None,
        "formal_sets": formal_sets if formal_sets else None,
        "total_kcal": round(sum(kcal_values), 2) if kcal_values else None,
        "diet_recorded_days": len(kcal_values) or None,
        "avg_kcal_on_diet_days": _avg(kcal_values),
    }


def _compact_day_type(value: Any) -> str | None:
    text = str(value or "").strip()
    return {"高碳日": "高", "中碳日": "中", "低碳日": "低"}.get(text)


def _calendar_labels(summary: Mapping[str, Any], state: str, kcal: float | None) -> list[str]:
    if state == "unrecorded":
        return []
    day_type = _compact_day_type(summary.get("day_type"))
    event_text = str(summary.get("event_text") or "").strip()
    labels = []
    if day_type:
        labels.append(day_type)
    labels.extend(_calendar_activity_lines(summary, state))
    if kcal is not None:
        labels.append(f"{kcal:g}")
    if event_text and event_text not in labels and summary.get("activity_type") != "custom":
        labels.append(event_text)
    return labels


def _calendar_activity_lines(summary: Mapping[str, Any], state: str) -> list[str]:
    if state == "unrecorded":
        return []
    activity_type = summary.get("activity_type")
    if activity_type == "training":
        parts = [str(part).strip() for part in summary.get("body_parts", []) if str(part).strip()]
        if not parts:
            return ["训练"]
        if len(parts) <= 3:
            return parts
        return [parts[0], parts[1], f"{parts[2]} +{len(parts) - 3}"]
    if activity_type == "rest":
        return ["休息"]
    if activity_type == "custom":
        return [str(summary.get("activity") or "事项")[:3]]
    return []


def _calendar_kcal_band(kcal: float | None, target: float | None) -> tuple[str, float | None]:
    if (
        kcal is None
        or target is None
        or not math.isfinite(kcal)
        or not math.isfinite(target)
        or target <= 0
    ):
        return CALENDAR_KCAL_BAND_MISSING, None
    ratio = kcal / target
    below, target_max, over_max = CALENDAR_KCAL_RATIO_THRESHOLDS
    if ratio < below:
        band = CALENDAR_KCAL_BAND_BELOW
    elif ratio <= target_max:
        band = CALENDAR_KCAL_BAND_TARGET
    elif ratio <= over_max:
        band = CALENDAR_KCAL_BAND_OVER
    else:
        band = CALENDAR_KCAL_BAND_HIGH
    return band, round(ratio, 4)


def _selected_calendar_detail(records: Mapping[str, Any], selected_date: str) -> dict[str, Any]:
    record = records.get(selected_date)
    summary = calendar_day_summary(record, selected_date)
    training = summarize_daily_training(record, selected_date)
    diet = _mapping(_mapping(record).get("daily_total"))
    has_food = _has_food(record)
    state = (
        "rest" if summary.get("activity_type") == "rest"
        else "recorded" if _has_record_content(record)
        else "unrecorded"
    )
    return {
        "date": selected_date,
        "record_state": state,
        "day_type": summary.get("day_type"),
        "activity_type": summary.get("activity_type"),
        "activity": summary.get("activity"),
        "event_text": summary.get("event_text"),
        "training": training if training["has_training"] else None,
        "diet": {
            "kcal": _number(diet.get("kcal")),
            "carb": _number(diet.get("carb")),
            "protein": _number(diet.get("protein")),
            "fat": _number(diet.get("fat")),
        } if has_food else None,
    }


def _resolved_metric(chart_kind: str, metric_key: str | None) -> str:
    options = TREND_METRICS.get(chart_kind, TREND_METRICS["weight"])
    valid = {key for key, _ in options}
    return metric_key if metric_key in valid else DEFAULT_TREND_METRIC.get(chart_kind, options[0][0])


def _metric_meta(chart_kind: str, metric_key: str) -> dict[str, Any]:
    metadata = {
        "weight_kg": ("体重", "kg", "查看体重随时间的真实变化", "还没有体重记录，记录后可查看体重变化"),
        "bodyfat_percent": ("体脂", "%", "查看体脂率随时间的真实变化", "还没有体脂记录，记录后可查看体脂变化"),
        "waist_cm": ("腰围", "cm", "查看腰围随时间的真实变化", "还没有腰围记录，记录后可查看围度变化"),
        "arm_cm": ("上臂围", "cm", "查看上臂围随时间的真实变化", "还没有上臂围记录，记录后可查看围度变化"),
        "chest_cm": ("胸围", "cm", "查看胸围随时间的真实变化", "还没有胸围记录，记录后可查看围度变化"),
        "hip_cm": ("臀围", "cm", "查看臀围随时间的真实变化", "还没有臀围记录，记录后可查看围度变化"),
        "thigh_cm": ("大腿围", "cm", "查看大腿围随时间的真实变化", "还没有大腿围记录，记录后可查看围度变化"),
        "calf_cm": ("小腿围", "cm", "查看小腿围随时间的真实变化", "还没有小腿围记录，记录后可查看围度变化"),
        "kcal": ("每日热量", "kcal", "查看每日摄入与目标的差距", "还没有饮食记录，记录后可查看每日摄入与目标的差距"),
        "carb": ("每日碳水", "g", "查看每日摄入与目标的差距", "还没有碳水记录，记录后可查看每日摄入与目标的差距"),
        "protein": ("每日蛋白", "g", "查看每日摄入与目标的差距", "还没有蛋白记录，记录后可查看每日摄入与目标的差距"),
        "fat": ("每日脂肪", "g", "查看每日摄入与目标的差距", "还没有脂肪记录，记录后可查看每日摄入与目标的差距"),
        "volume_kg": ("力量总容量", "kg", "查看每日力量训练负荷变化", "还没有力量训练容量记录"),
        "formal_sets": ("力量完成组数", "组", "查看每日力量训练组数变化", "还没有力量训练完成组"),
        "duration_min": ("训练时长", "分钟", "查看每日训练量和负荷变化", "还没有训练时长记录，完成训练后可查看训练时长变化"),
        "cardio_duration_min": ("有氧时长", "分钟", "查看每日完成的有氧活动时长", "还没有完成的有氧时长记录"),
        "distance_km": ("有氧距离", "km", "查看每日完成的有氧活动距离", "还没有完成的有氧距离记录"),
        "sleep_hours": ("睡眠时长", "小时", "查看睡眠和饮水是否达到目标", "还没有睡眠记录，记录后可查看是否达到目标"),
        "water_ml": ("饮水量", "ml", "查看睡眠和饮水是否达到目标", "还没有饮水记录，记录后可查看是否达到目标"),
    }
    title, unit, description, empty_message = metadata[metric_key]
    return {
        "title": title,
        "unit": unit,
        "description": description,
        "empty_message": empty_message,
        "chart_type": "line",
    }


def _trend_value(point: Mapping[str, Any], chart_kind: str, metric_key: str) -> float | None:
    body = _mapping(point.get("body"))
    diet = _mapping(point.get("diet"))
    training = _mapping(point.get("training"))
    recovery = _mapping(point.get("recovery"))
    if metric_key == "weight_kg":
        return _number(body.get("weight_kg"))
    if metric_key == "bodyfat_percent":
        return _number(body.get("bodyfat_percent"))
    if chart_kind == "circumference":
        return _number(_mapping(point.get("circumference")).get(metric_key))
    if chart_kind == "diet":
        return _number(diet.get(metric_key))
    if chart_kind == "training":
        if not training:
            return None
        return _number(training.get(metric_key))
    if chart_kind == "recovery":
        if metric_key == "sleep_hours":
            sleep = _number(recovery.get("sleep_minutes"))
            return round(sleep / 60, 2) if sleep is not None else None
        return _number(recovery.get("water_ml"))
    return None


def _trend_label(point: Mapping[str, Any], chart_kind: str, metric_key: str, unit: str) -> str:
    value = _trend_value(point, chart_kind, metric_key)
    if value is None:
        return "未记录"
    return f"{value:g}{unit}" if unit == "%" else f"{value:g} {unit}"


def _trend_target(point: Mapping[str, Any], metric_key: str) -> tuple[float | None, float | None]:
    targets = _mapping(point.get("targets"))
    if metric_key == "kcal":
        value = _number(targets.get("calorie_target"))
        return value, value
    range_keys = {
        "carb": ("carb_min", "carb_max"),
        "protein": ("protein_min", "protein_max"),
        "fat": ("fat_min", "fat_max"),
    }
    if metric_key in range_keys:
        low_key, high_key = range_keys[metric_key]
        return _number(targets.get(low_key)), _number(targets.get(high_key))
    if metric_key == "sleep_hours":
        return 7.0, 9.0
    if metric_key == "water_ml":
        value = _number(_mapping(point.get("recovery")).get("water_target_ml")) or 2000.0
        return value, value
    return None, None


def _nice_axis(values: list[float], target_values: list[float] | None = None, tick_count: int = 4) -> dict[str, Any]:
    combined = [float(value) for value in values + list(target_values or []) if math.isfinite(float(value))]
    if not combined:
        return {"min": 0.0, "max": 1.0, "ticks": [0.0, 0.5, 1.0]}
    low = min(combined)
    high = max(combined)
    span = high - low
    if span <= 0:
        padding = max(abs(low) * 0.05, 1.0)
    else:
        padding = span * 0.12
    raw_low = low - padding
    raw_high = high + padding
    raw_step = max((raw_high - raw_low) / max(2, tick_count - 1), 1e-9)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    normalized = raw_step / magnitude
    nice_factor = 1 if normalized <= 1 else 2 if normalized <= 2 else 5 if normalized <= 5 else 10
    step = nice_factor * magnitude
    axis_min = math.floor(raw_low / step) * step
    axis_max = math.ceil(raw_high / step) * step
    if axis_min == axis_max:
        axis_max = axis_min + step
    elif span > 0:
        # Keep one full tick of breathing room below the series so the minimum
        # label can sit under its point without wasting space above the chart.
        axis_min -= step
    ticks = []
    cursor = axis_min
    while cursor <= axis_max + step * 0.01 and len(ticks) < 8:
        ticks.append(round(cursor, 6))
        cursor += step
    return {"min": axis_min, "max": axis_max, "ticks": ticks}


def _date_tick_indices(days: int) -> list[int]:
    if days <= 7:
        return list(range(days))
    count = 6
    return sorted({round(index * (days - 1) / (count - 1)) for index in range(count)})


def _weekly_review(records: Mapping[str, Any], end: date) -> dict[str, Any]:
    fourteen = build_period_series(records, end_date=end, days=30)[-14:]
    previous, current = fourteen[:7], fourteen[7:]

    weights = [
        (item["date"], _number(_mapping(item.get("body")).get("weight_kg")))
        for item in current
    ]
    weights = [(day, value) for day, value in weights if value is not None]
    weight_change = round(weights[-1][1] - weights[0][1], 2) if len(weights) >= 2 else None

    def training_totals(items: list[Mapping[str, Any]]) -> tuple[int, float]:
        trainings = [_mapping(item.get("training")) for item in items if item.get("training")]
        return sum(int(item.get("session_count") or 0) for item in trainings), round(sum(_number(item.get("volume_kg")) or 0 for item in trainings), 2)

    training_count, training_volume = training_totals(current)
    previous_count, previous_volume = training_totals(previous)
    volume_change_percent = None
    if training_count > 0 and previous_count > 0 and previous_volume > 0:
        volume_change_percent = round((training_volume - previous_volume) / previous_volume * 100, 1)

    diet_ratios: list[float] = []
    diet_pairs: list[tuple[float, float]] = []
    for item in current:
        actual = _number(_mapping(item.get("diet")).get("kcal"))
        target = _number(_mapping(item.get("targets")).get("calorie_target"))
        if actual is not None and target is not None and target > 0:
            diet_ratios.append(actual / target * 100)
            diet_pairs.append((actual, target))

    sleep_values = [
        round(value / 60, 2)
        for item in current
        if (value := _number(_mapping(item.get("recovery")).get("sleep_minutes"))) is not None
    ]
    avg_sleep = _avg(sleep_values)
    return {
        "weight": {
            "value": weight_change,
            "label": "暂无足够数据" if weight_change is None else f"{weight_change:+g} kg",
            "detail": f"{len(weights)} 次真实记录",
        },
        "training": {
            "count": training_count,
            "volume_kg": training_volume,
            "change_percent": volume_change_percent,
            "label": "暂无足够数据" if training_count == 0 else f"{training_count} 次 · {training_volume:g} kg",
            "detail": "前周数据不足" if volume_change_percent is None else f"较前周 {volume_change_percent:+g}%",
        },
        "diet": {
            "recorded_days": len(diet_ratios),
            "completion_percent": _avg(diet_ratios),
            "avg_actual": _avg([item[0] for item in diet_pairs]),
            "avg_target": _avg([item[1] for item in diet_pairs]),
            "label": "暂无足够数据" if not diet_ratios else f"平均 {_avg(diet_ratios):g}%",
            "detail": f"{len(diet_ratios)} 天有饮食和目标记录",
        },
        "sleep": {
            "recorded_days": len(sleep_values),
            "avg_hours": avg_sleep,
            "target_gap_hours": None if avg_sleep is None else round(avg_sleep - 7.0, 2),
            "label": "暂无足够数据" if avg_sleep is None else f"平均 {avg_sleep:g} 小时",
            "detail": f"{len(sleep_values)} 天记录" if avg_sleep is None else f"距 7 小时目标 {avg_sleep - 7:+g} 小时",
        },
    }


def build_data_page_model(
    records: Any,
    *,
    end_date: str | date,
    config: DataPageConfig | None = None,
) -> dict[str, Any]:
    """Build all backend data required by the data page.

    The model deliberately separates explicit rest days from unrecorded days,
    and keeps weight/body-fat measurement counts independent.
    """

    cfg = config or DataPageConfig()
    if cfg.period_days not in PERIOD_OPTIONS:
        raise ValueError("period_days must be one of 7, 30, or 90")
    if cfg.active_tab not in VIEW_TABS:
        raise ValueError("active_tab must be 趋势, 月历, or 汇总")
    if cfg.chart_kind not in {key for key, _ in CHART_OPTIONS} | {"body"}:
        raise ValueError("chart_kind must be weight, bodyfat, circumference, diet, training, or recovery")
    if cfg.body_part_filter not in BODY_PART_FILTERS:
        raise ValueError("body_part_filter must be a supported body part")

    end = _date_value(end_date)
    month_anchor = _month_anchor(cfg.calendar_month, end)
    source = records if isinstance(records, Mapping) else {}
    selected = cfg.selected_date or end.isoformat()
    try:
        selected_value = date.fromisoformat(selected)
    except (TypeError, ValueError):
        selected_value = month_anchor
        selected = selected_value.isoformat()
    if (selected_value.year, selected_value.month) != (month_anchor.year, month_anchor.month):
        selected_value = month_anchor
        selected = selected_value.isoformat()
    series = build_period_series(source, end_date=end, days=cfg.period_days)
    for point in series:
        record = source.get(point["date"])
        point["circumference"] = _explicit_circumferences(record)
    calendar_items: list[dict[str, Any]] = []
    for item_date in _month_dates(month_anchor):
        if item_date is None:
            calendar_items.append({"date": None, "in_month": False})
            continue
        key = item_date.isoformat()
        record = source.get(key)
        summary = calendar_day_summary(record, key)
        activity_type = summary["activity_type"]
        state = "rest" if activity_type == "rest" else "recorded" if _has_record_content(record) else "unrecorded"
        total = _mapping(_mapping(record).get("daily_total"))
        kcal = _number(total.get("kcal")) if _has_food(record) else None
        if kcal is not None and not math.isfinite(kcal):
            kcal = None
        calorie_target = _number(summary.get("calorie_target"))
        kcal_band, kcal_ratio = _calendar_kcal_band(kcal, calorie_target)
        calendar_items.append({
            **summary,
            "in_month": True,
            "record_state": state,
            "selected": key == selected,
            "kcal": kcal,
            "calorie_target": calorie_target,
            "kcal_ratio": kcal_ratio,
            "kcal_band": kcal_band,
            "compact_day_type": _compact_day_type(summary.get("day_type")),
            "activity_lines": _calendar_activity_lines(summary, state),
            "note_summary": str(summary.get("event_text") or "").strip() or None,
            "compact_labels": _calendar_labels(summary, state, kcal),
        })

    body_weights = [_number(_mapping(point.get("body")).get("weight_kg")) for point in series]
    body_fats = [_number(_mapping(point.get("body")).get("bodyfat_percent")) for point in series]
    kcal_values = [_number(_mapping(point.get("diet")).get("kcal")) for point in series]
    protein_values = [_number(_mapping(point.get("diet")).get("protein")) for point in series]
    water_values = [_number(_mapping(point.get("recovery")).get("water_ml")) for point in series]
    sleep_values = [_number(_mapping(point.get("recovery")).get("sleep_minutes")) for point in series]
    circumference_values = {
        key: [_number(_mapping(point.get("circumference")).get(key)) for point in series]
        for key, _ in CIRCUMFERENCE_KEYS
    }
    training_days = [point for point in series if point.get("training")]
    rest_days = [item for item in calendar_items if item.get("record_state") == "rest"]
    unrecorded_days = [item for item in calendar_items if item.get("record_state") == "unrecorded"]

    def period_change(values: list[float | None]) -> float | None:
        recorded_values = [value for value in values if value is not None]
        return round(recorded_values[-1] - recorded_values[0], 2) if len(recorded_values) >= 2 else None

    chart_kind = "weight" if cfg.chart_kind == "body" else cfg.chart_kind
    metric_key = _resolved_metric(chart_kind, cfg.metric_key)
    metric_meta = _metric_meta(chart_kind, metric_key)
    trend_points = [
        {
            "date": point["date"],
            "value": _trend_value(point, chart_kind, metric_key),
            "label": _trend_label(point, chart_kind, metric_key, metric_meta["unit"]),
            "target_min": _trend_target(point, metric_key)[0],
            "target_max": _trend_target(point, metric_key)[1],
        }
        for point in series
    ]
    recorded_points = [item for item in trend_points if item["value"] is not None]
    previous_real = None
    for item in trend_points:
        if item["value"] is None:
            continue
        item["previous_date"] = previous_real["date"] if previous_real else None
        item["change_from_previous"] = None if previous_real is None else round(item["value"] - previous_real["value"], 2)
        previous_real = item
    latest = recorded_points[-1] if recorded_points else None
    previous = recorded_points[-2] if len(recorded_points) > 1 else None
    earliest = recorded_points[0] if len(recorded_points) > 1 else None
    selected_trend_date = cfg.selected_trend_date if any(
        item["date"] == cfg.selected_trend_date and item["value"] is not None
        for item in trend_points
    ) else None
    target_values = [
        value for item in trend_points for value in (item["target_min"], item["target_max"])
        if value is not None
    ]
    axis = _nice_axis([item["value"] for item in recorded_points], target_values)
    exercise_trend = _exercise_trend(source, series, cfg.selected_exercise) if cfg.chart_kind == "training" else {
        "open": False,
        "selected_exercise": None,
        "options": [],
        "points": [],
        "recorded_count": 0,
        "best_weight_kg": None,
        "best_reps": None,
        "best_epley_1rm_kg": None,
        "empty_action_label": "+记录训练",
    }
    exercise_trend["open"] = bool(cfg.action_trend_open)

    return {
        "config": cfg,
        "weekly_review": _weekly_review(source, end),
        "series": series,
        "calendar": calendar_items,
        "calendar_month": month_anchor.strftime("%Y-%m"),
        "calendar_summary": _month_summary(source, month_anchor),
        "selected_date": selected,
        "selected_day": _selected_calendar_detail(source, selected),
        "trend": {
            "chart_kind": chart_kind,
            "metric_key": metric_key,
            "period_days": cfg.period_days,
            "window_start": trend_points[0]["date"] if trend_points else end.isoformat(),
            "window_end": trend_points[-1]["date"] if trend_points else end.isoformat(),
            "metric_options": [dict(key=key, label=label) for key, label in TREND_METRICS[chart_kind]],
            **metric_meta,
            "points": trend_points,
            "recorded_count": len(recorded_points),
            "latest": latest,
            "change": None if not (latest and previous) else round(latest["value"] - previous["value"], 2),
            "change_from_earliest": None if not (latest and earliest) else round(latest["value"] - earliest["value"], 2),
            "axis": axis,
            "date_tick_indices": _date_tick_indices(len(trend_points)),
            "selected_trend_date": selected_trend_date,
            "empty_action_label": {
                "weight": "记录体重",
                "bodyfat": "记录体脂",
                "circumference": "记录围度",
                "diet": "记录饮食",
                "training": "记录训练",
                "recovery": "记录恢复",
            }[chart_kind],
            "weekly_training": _training_week_totals(series) if cfg.chart_kind == "training" else [],
            "best_lifts": _best_lifts(source, series, cfg.body_part_filter) if cfg.chart_kind == "training" else [],
            "body_part_filter": cfg.body_part_filter,
            "exercise_trend_entry": cfg.chart_kind == "training",
            "exercise_trend": exercise_trend,
        },
        "summary": {
            "period_days": cfg.period_days,
            "weight_measurements": sum(1 for item in body_weights if item is not None),
            "bodyfat_measurements": sum(1 for item in body_fats if item is not None),
            "weight_change": period_change(body_weights),
            "bodyfat_change": period_change(body_fats),
            "avg_weight_kg": _avg([item for item in body_weights if item is not None]),
            "avg_bodyfat_percent": _avg([item for item in body_fats if item is not None]),
            "circumference_measurements": {
                key: sum(1 for item in values if item is not None)
                for key, values in circumference_values.items()
            },
            "diet_recorded_days": sum(1 for point in series if point.get("diet")),
            "avg_kcal": _avg([item for item in kcal_values if item is not None]),
            "avg_protein": _avg([item for item in protein_values if item is not None]),
            "training_days": len(training_days),
            "training_sessions": sum(_mapping(point.get("training")).get("session_count", 0) for point in training_days),
            "training_volume_kg": round(sum(_number(_mapping(point.get("training")).get("volume_kg")) or 0 for point in training_days), 2),
            "recovery_recorded_days": sum(1 for point in series if point.get("recovery")),
            "avg_water_ml": _avg([item for item in water_values if item is not None]),
            "avg_sleep_hours": _avg([round(item / 60, 2) for item in sleep_values if item is not None]),
            "rest_days": len(rest_days),
            "unrecorded_days": len(unrecorded_days),
        },
        "raw_days": [
            {
                "date": point["date"],
                "body": point.get("body"),
                "diet": point.get("diet"),
                "training": point.get("training"),
                "recovery": point.get("recovery"),
            }
            for point in reversed(series)
        ],
    }
