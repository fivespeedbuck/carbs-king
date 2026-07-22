"""Reusable data-page models and Flet views for analytics.

This module keeps the data page independent from ``main.py``.  The public
``build_data_page_view`` function accepts plain daily records plus small
callbacks, then returns a ready-to-mount Flet control.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import flet as ft

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
    ("arm_cm", "臂围"),
    ("chest_cm", "胸围"),
    ("hip_cm", "臀围"),
    ("thigh_cm", "腿围"),
)

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


@dataclass(frozen=True)
class DataPageConfig:
    """Small immutable state needed to rebuild the reusable data page."""

    period_days: int = 7
    active_tab: str = "趋势"
    chart_kind: str = "weight"
    body_part_filter: str = "全部"
    selected_date: str | None = None
    action_trend_open: bool = False
    selected_exercise: str | None = None
    raw_expanded: bool = False


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


def _calendar_labels(summary: Mapping[str, Any], state: str) -> list[str]:
    if state == "unrecorded":
        return ["无记录"]
    day_type = summary.get("day_type")
    activity_type = summary.get("activity_type")
    activity = summary.get("activity")
    labels = []
    if day_type:
        labels.append(str(day_type))
    if activity_type == "training" and activity:
        labels.append(str(activity))
    elif activity_type in {"rest", "custom"} and activity:
        labels.append(str(activity))
    return labels[:2]


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


def _trend_value(point: Mapping[str, Any], chart_kind: str) -> float | None:
    body = _mapping(point.get("body"))
    diet = _mapping(point.get("diet"))
    training = _mapping(point.get("training"))
    recovery = _mapping(point.get("recovery"))
    if chart_kind in {"body", "weight"}:
        return _number(body.get("weight_kg"))
    if chart_kind == "bodyfat":
        return _number(body.get("bodyfat_percent"))
    if chart_kind == "circumference":
        values = [_number(value) for value in _mapping(point.get("circumference")).values()]
        measured = [value for value in values if value is not None]
        return _avg(measured)
    if chart_kind == "diet":
        return _number(diet.get("kcal"))
    if chart_kind == "training":
        if int(training.get("formal_sets") or 0) <= 0:
            return None
        return _number(training.get("volume_kg"))
    if chart_kind == "recovery":
        sleep = _number(recovery.get("sleep_minutes"))
        return round(sleep / 60, 2) if sleep is not None else None
    return None


def _trend_label(point: Mapping[str, Any], chart_kind: str) -> str:
    value = _trend_value(point, chart_kind)
    if value is None:
        return "未记录"
    if chart_kind in {"body", "weight"}:
        return f"{value:g} kg"
    if chart_kind == "bodyfat":
        return f"{value:g}%"
    if chart_kind == "circumference":
        return f"{value:g} cm"
    if chart_kind == "diet":
        return f"{value:g} kcal"
    if chart_kind == "training":
        return f"{value:g} kg"
    return f"{value:g} h"


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
    source = records if isinstance(records, Mapping) else {}
    selected = cfg.selected_date or end.isoformat()
    series = build_period_series(source, end_date=end, days=cfg.period_days)
    for point in series:
        record = source.get(point["date"])
        point["circumference"] = _explicit_circumferences(record)
    calendar_items: list[dict[str, Any]] = []
    for item_date in _month_dates(end):
        if item_date is None:
            calendar_items.append({"date": None, "in_month": False})
            continue
        key = item_date.isoformat()
        record = source.get(key)
        summary = calendar_day_summary(record, key)
        activity_type = summary["activity_type"]
        state = "rest" if activity_type == "rest" else "recorded" if _has_record_content(record) else "unrecorded"
        calendar_items.append({
            **summary,
            "in_month": True,
            "record_state": state,
            "selected": key == selected,
            "compact_labels": _calendar_labels(summary, state),
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

    trend_points = [
        {
            "date": point["date"],
            "value": _trend_value(point, cfg.chart_kind),
            "label": _trend_label(point, cfg.chart_kind),
        }
        for point in series
    ]
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
        "series": series,
        "calendar": calendar_items,
        "calendar_summary": _month_summary(source, end),
        "selected_date": selected,
        "selected_day": _selected_calendar_detail(source, selected),
        "trend": {
            "chart_kind": cfg.chart_kind,
            "points": trend_points,
            "recorded_count": sum(1 for item in trend_points if item["value"] is not None),
            "empty_action_label": "+记录",
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


def _text(value: Any, *, size: int = 13, color: str = TEXT, weight: str | None = None) -> ft.Text:
    return ft.Text(str(value), size=size, color=color, weight=weight)


def _card(content: ft.Control, *, padding: int = 12) -> ft.Container:
    return ft.Container(content=content, bgcolor=WHITE, border=_border(BORDER), border_radius=8, padding=padding)


def _border(color: str, width: int = 1) -> ft.Border:
    side = ft.BorderSide(width=width, color=color)
    return ft.Border(top=side, right=side, bottom=side, left=side)


def _chip(label: str, selected: bool, on_click: Callable[[Any], None] | None = None) -> ft.Container:
    return ft.Container(
        content=ft.Text(label, size=14, weight="bold", color=WHITE if selected else PRIMARY, text_align="center", max_lines=1, overflow="ellipsis"),
        height=48,
        padding=ft.Padding(left=10, top=0, right=10, bottom=0),
        bgcolor=PRIMARY if selected else PRIMARY_SOFT,
        border=_border(PRIMARY if selected else BORDER),
        border_radius=8,
        alignment=ft.Alignment.CENTER,
        expand=True,
        ink=True,
        on_click=on_click,
    )


def _metric(label: str, value: Any, *, color: str = TEXT) -> ft.Container:
    return ft.Container(
        content=ft.Column([_text(label, size=12, color=SUB, weight="bold"), _text(value, size=18, color=color, weight="bold")], spacing=3),
        bgcolor=SURFACE,
        border=_border(BORDER),
        border_radius=8,
        padding=12,
        expand=True,
    )


def _chart_title(chart_kind: str) -> str:
    return dict(CHART_OPTIONS).get(chart_kind, "体重")


def _empty_entry(label: str, on_click: Callable[[Any], None] | None) -> ft.Container:
    return ft.Container(
        content=ft.Row([
            _text("暂无真实记录", size=14, color=SUB, weight="bold"),
            _chip(label, False, on_click),
        ], spacing=8),
        bgcolor=SURFACE,
        border_radius=8,
        padding=10,
    )


def _render_training_details(
    model: Mapping[str, Any],
    on_action_trend_open: Callable[[Any], None] | None,
    on_body_part_filter_change: Callable[[str], None] | None,
) -> list[ft.Control]:
    trend = _mapping(model.get("trend"))
    weekly = [item for item in trend.get("weekly_training", []) if isinstance(item, Mapping)]
    best_lifts = [item for item in trend.get("best_lifts", []) if isinstance(item, Mapping)]
    week_rows = [
        ft.Row([
            _text(item["label"], size=12, color=SUB),
            _text(f"{item['sets']} 组", size=13, weight="bold"),
            _text(f"{item['volume_kg']:g} kg", size=13, color=PRIMARY, weight="bold"),
        ], alignment="spaceBetween")
        for item in weekly
        if item.get("sets") or item.get("volume_kg")
    ]
    filter_row = ft.Row(
        [
            _chip(part, trend["body_part_filter"] == part, None if on_body_part_filter_change is None else lambda e, value=part: on_body_part_filter_change(value))
            for part in BODY_PART_FILTERS
        ],
        spacing=5,
        scroll=getattr(getattr(ft, "ScrollMode", object()), "AUTO", "auto"),
    )
    lift_rows = [
        ft.Container(
            content=ft.Row([
                ft.Column([
                    _text(f"{item['body_part']} · {item['exercise'] or '未命名动作'}", size=13, weight="bold"),
                    _text(item["date"], size=12, color=SUB),
                ], spacing=1, expand=True),
                _text(f"{item['weight_kg']:g} x {item['reps']:g}", size=13, weight="bold"),
                _text(f"1RM {item['epley_1rm_kg']:g}", size=13, color=PRIMARY, weight="bold"),
            ], spacing=8),
            bgcolor=SURFACE,
            border_radius=6,
            padding=8,
        )
        for item in best_lifts
    ]
    return [
        ft.Row([_metric("周总组数", sum(item.get("sets", 0) for item in weekly)), _metric("周总容量", f"{sum(item.get('volume_kg', 0) for item in weekly):g} kg")], spacing=8),
        ft.Container(content=ft.Column(week_rows or [_text("暂无真实完成组", size=13, color=SUB)], spacing=4), bgcolor=SURFACE, border_radius=8, padding=10),
        ft.Row([
            _text("动作趋势", size=16, weight="bold"),
            _chip("进入", False, on_action_trend_open),
        ], spacing=8),
        _text("按部位筛选最佳成绩", size=15, weight="bold"),
        filter_row,
        ft.Column(lift_rows or [_empty_entry("+记录训练", None)], spacing=6),
    ]


def _render_action_trend(
    model: Mapping[str, Any],
    on_action_trend_close: Callable[[Any], None] | None,
    on_selected_exercise_change: Callable[[str], None] | None,
    on_add_record: Callable[[str], None] | None,
) -> list[ft.Control]:
    trend = _mapping(_mapping(model.get("trend")).get("exercise_trend"))
    options = [item for item in trend.get("options", []) if isinstance(item, Mapping)]
    selected = str(trend.get("selected_exercise") or "")
    add_click = None if on_add_record is None else lambda e: on_add_record("training")
    if not options:
        return [
            ft.Row([
                _text("动作趋势", size=16, weight="bold"),
                _chip("返回训练汇总", False, on_action_trend_close),
            ], spacing=8),
            _empty_entry(str(trend.get("empty_action_label") or "+记录训练"), add_click),
        ]

    points = [item for item in trend.get("points", []) if isinstance(item, Mapping)]
    values = [_number(item.get("epley_1rm_kg")) for item in points]
    recorded = [item for item in values if item is not None]
    min_value = min(recorded) if recorded else 0
    max_value = max(recorded) if recorded else 1
    span = max(max_value - min_value, 1)
    bars = []
    for point, value in zip(points, values):
        height = 18 if value is None else 28 + int((value - min_value) / span * 78)
        bars.append(
            ft.Container(
                content=ft.Container(width=10, height=height, bgcolor=BORDER if value is None else PURPLE, border_radius=5),
                height=118,
                alignment=ft.Alignment.BOTTOM_CENTER,
                tooltip=f"{point['date']} · {point['label']}",
                expand=True,
            )
        )
    option_row = ft.Row(
        [
            _chip(
                str(item["exercise"]),
                selected == item["exercise"],
                None if on_selected_exercise_change is None else lambda e, value=str(item["exercise"]): on_selected_exercise_change(value),
            )
            for item in options
        ],
        spacing=5,
        scroll=getattr(getattr(ft, "ScrollMode", object()), "AUTO", "auto"),
    )
    return [
        ft.Row([
            _text("动作趋势", size=16, weight="bold"),
            _chip("返回训练汇总", False, on_action_trend_close),
        ], spacing=8),
        option_row,
        ft.Row([
            _metric("最佳重量", _value_or_empty(trend.get("best_weight_kg"), "kg")),
            _metric("最高次数", _value_or_empty(trend.get("best_reps"))),
            _metric("最佳 1RM", _value_or_empty(trend.get("best_epley_1rm_kg"), "kg")),
        ], spacing=8),
        ft.Row(bars, spacing=3, vertical_alignment="end"),
        _empty_entry(str(trend.get("empty_action_label") or "+记录训练"), add_click) if not recorded else ft.Container(height=0),
    ]


def _render_circumference_summary(model: Mapping[str, Any]) -> ft.Control:
    summary = _mapping(model.get("summary"))
    counts = _mapping(summary.get("circumference_measurements"))
    items = [
        _metric(label, counts.get(key, 0))
        for key, label in CIRCUMFERENCE_KEYS
    ]
    return ft.Column([ft.Row(items[index:index + 2], spacing=8) for index in range(0, len(items), 2)], spacing=8)


def _render_trend_chart(
    model: Mapping[str, Any],
    on_add_record: Callable[[str], None] | None,
    on_action_trend_open: Callable[[Any], None] | None,
    on_action_trend_close: Callable[[Any], None] | None,
    on_selected_exercise_change: Callable[[str], None] | None,
    on_body_part_filter_change: Callable[[str], None] | None,
) -> ft.Container:
    trend = _mapping(model.get("trend"))
    points = [item for item in trend.get("points", []) if isinstance(item, Mapping)]
    values = [_number(point.get("value")) for point in points]
    recorded = [item for item in values if item is not None]
    min_value = min(recorded) if recorded else 0
    max_value = max(recorded) if recorded else 1
    span = max(max_value - min_value, 1)
    bars: list[ft.Control] = []
    for point, value in zip(points, values):
        height = 18 if value is None else 28 + int((value - min_value) / span * 78)
        color = BORDER if value is None else PRIMARY
        bars.append(
            ft.Container(
                content=ft.Container(width=10, height=height, bgcolor=color, border_radius=5),
                height=118,
                alignment=ft.Alignment.BOTTOM_CENTER,
                tooltip=f"{point['date']} · {point['label']}",
                expand=True,
            )
        )
    chart_kind = str(trend["chart_kind"])
    add_click = None if on_add_record is None else lambda e, value=chart_kind: on_add_record(value)
    extra: list[ft.Control] = []
    if not recorded:
        extra.append(_empty_entry(str(trend["empty_action_label"]), add_click))
    if chart_kind == "training":
        exercise_trend = _mapping(trend.get("exercise_trend"))
        if exercise_trend.get("open"):
            extra = _render_action_trend(model, on_action_trend_close, on_selected_exercise_change, on_add_record)
            bars = []
        else:
            extra.extend(_render_training_details(model, on_action_trend_open, on_body_part_filter_change))
    elif chart_kind == "circumference":
        extra.append(_render_circumference_summary(model))

    return _card(
        ft.Column(
            [
                ft.Row([
                    _text(f"{_chart_title(trend['chart_kind'])}主图", size=15, weight="bold"),
                    ft.Row([
                        _text(f"{trend['recorded_count']} 天有数据", size=12, color=SUB),
                        _chip(str(trend["empty_action_label"]), False, add_click),
                    ], spacing=6),
                ], alignment="spaceBetween"),
                ft.Row(bars, spacing=3, vertical_alignment="end") if bars else ft.Container(height=0),
                *extra,
            ],
            spacing=10,
        )
    )


def _value_or_empty(value: Any, suffix: str = "") -> str:
    return "无数据" if value is None else f"{value:g}{suffix}" if isinstance(value, (int, float)) else str(value)


def _render_calendar_summary(model: Mapping[str, Any]) -> ft.Control:
    summary = _mapping(model.get("calendar_summary"))
    return ft.Column(
        [
            ft.Row([
                _metric("训练天数", _value_or_empty(summary.get("training_days"))),
                _metric("训练时长", _value_or_empty(summary.get("training_duration_min"), "分")),
            ], spacing=8),
            ft.Row([
                _metric("正式组数", _value_or_empty(summary.get("formal_sets"))),
                _metric("月总摄入", _value_or_empty(summary.get("total_kcal"), "kcal")),
            ], spacing=8),
            ft.Row([
                _metric("饮食记录日", _value_or_empty(summary.get("diet_recorded_days"))),
                _metric("记录日均摄入", _value_or_empty(summary.get("avg_kcal_on_diet_days"), "kcal")),
            ], spacing=8),
        ],
        spacing=8,
    )


def _render_selected_day_detail(
    model: Mapping[str, Any],
    on_calendar_event_change: Callable[[str, str], None] | None = None,
) -> ft.Control:
    detail = _mapping(model.get("selected_day"))
    training = _mapping(detail.get("training"))
    diet = _mapping(detail.get("diet"))
    if detail.get("record_state") == "unrecorded":
        lines = [_text("该日无记录", size=14, color=SUB, weight="bold")]
    else:
        lines = [
            _text(f"碳循环：{detail.get('day_type') or '未记录'}", size=13, color=TEXT),
            _text(f"事项：{detail.get('activity') or detail.get('event_text') or '无'}", size=13, color=TEXT),
            _text(
                f"训练：{training.get('body_part_label') or '无'} · {_value_or_empty(training.get('duration_min'), '分')} · {_value_or_empty(training.get('formal_sets'))}组"
                if training else "训练：无",
                size=13,
                color=TEXT,
            ),
            _text(
                f"饮食：{_value_or_empty(diet.get('kcal'), 'kcal')} · 碳 {_value_or_empty(diet.get('carb'))} 蛋 {_value_or_empty(diet.get('protein'))} 脂 {_value_or_empty(diet.get('fat'))}"
                if diet else "饮食：无",
                size=13,
                color=TEXT,
            ),
        ]
    return ft.Container(
        content=ft.Column([
            ft.Row([_text("选中日期", size=15, weight="bold"), _text(detail.get("date", ""), size=13, color=SUB)], alignment="spaceBetween"),
            *lines,
            ft.Row([
                _chip("标记休息", detail.get("record_state") == "rest", None if on_calendar_event_change is None else lambda e: on_calendar_event_change(str(detail.get("date", "")), "rest")),
                _chip("自定义事项", detail.get("activity_type") == "custom", None if on_calendar_event_change is None else lambda e: on_calendar_event_change(str(detail.get("date", "")), "custom")),
                _chip("清除事项", False, None if on_calendar_event_change is None else lambda e: on_calendar_event_change(str(detail.get("date", "")), "clear")),
            ], spacing=6),
        ], spacing=5),
        bgcolor=SURFACE,
        border_radius=8,
        padding=10,
    )


def _render_calendar(
    model: Mapping[str, Any],
    on_selected_date_change: Callable[[str], None] | None,
    on_calendar_event_change: Callable[[str, str], None] | None = None,
) -> ft.Container:
    cells: list[ft.Control] = []
    for item in model.get("calendar", []):
        if not item.get("in_month"):
            cells.append(ft.Container(height=74, bgcolor="#FBFCFB", border_radius=6, expand=True))
            continue
        state = item.get("record_state")
        selected = bool(item.get("selected"))
        state_color = PRIMARY if state == "recorded" else ORANGE if state == "rest" else BORDER
        day = str(item.get("date", ""))[-2:]
        labels = item.get("compact_labels") or []
        click = None if on_selected_date_change is None else lambda e, value=item.get("date"): on_selected_date_change(str(value))
        cells.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row([_text(day, size=12, weight="bold"), ft.Container(width=7, height=7, bgcolor=state_color, border_radius=4)], alignment="spaceBetween"),
                        _text(labels[0], size=12, color=TEXT, weight="bold") if len(labels) > 0 else ft.Container(height=13),
                        _text(labels[1], size=12, color=SUB) if len(labels) > 1 else ft.Container(height=13),
                    ],
                    spacing=2,
                ),
                height=74,
                padding=6,
                bgcolor=PRIMARY_SOFT if selected else WHITE,
                border=_border(PRIMARY if selected else state_color if state != "unrecorded" else BORDER, 2 if selected else 1),
                border_radius=6,
                expand=True,
                tooltip=item.get("event_text") or None,
                on_click=click,
            )
        )
    rows = [ft.Row(cells[index:index + 7], spacing=4) for index in range(0, len(cells), 7)]
    return _card(
        ft.Column([
            _render_calendar_summary(model),
            ft.Container(
                content=ft.Column([
                    ft.Row([_text(x, size=12, color=SUB, weight="bold") for x in ("一", "二", "三", "四", "五", "六", "日")], spacing=4),
                    *rows,
                ], spacing=4),
            ),
            _render_selected_day_detail(model, on_calendar_event_change),
        ], spacing=10)
    )


def _render_summary(model: Mapping[str, Any]) -> ft.Container:
    summary = _mapping(model.get("summary"))
    return _card(
        ft.Column(
            [
                ft.Row([_metric("体重实测", summary["weight_measurements"]), _metric("体脂实测", summary["bodyfat_measurements"])], spacing=8),
                ft.Row([_metric("饮食记录", summary["diet_recorded_days"]), _metric("训练天数", summary["training_days"])], spacing=8),
                ft.Row([_metric("休息日", summary["rest_days"], color=ORANGE), _metric("未记录", summary["unrecorded_days"], color=SUB)], spacing=8),
                ft.Row([_metric("平均热量", summary["avg_kcal"] or "无"), _metric("平均睡眠", f"{summary['avg_sleep_hours']}h" if summary["avg_sleep_hours"] is not None else "无")], spacing=8),
            ],
            spacing=8,
        )
    )


def _raw_day_line(item: Mapping[str, Any]) -> ft.Container:
    training = _mapping(item.get("training"))
    diet = _mapping(item.get("diet"))
    body = _mapping(item.get("body"))
    recovery = _mapping(item.get("recovery"))
    training_label = training.get("body_part_label") or ("休息" if not training else "")
    kcal = diet.get("kcal")
    weight = body.get("weight_kg")
    sleep = recovery.get("sleep_minutes")
    return ft.Container(
        content=ft.Row(
            [
                _text(item.get("date", ""), size=12, color=SUB),
                _text(f"{weight:g}kg" if isinstance(weight, (int, float)) else "身体未测", size=12, color=TEXT, weight="bold"),
                _text(f"{kcal:g}kcal" if isinstance(kcal, (int, float)) else "饮食未记", size=12, color=TEXT),
                _text(str(training_label or "训练未记"), size=12, color=TEXT),
                _text(f"{round(sleep / 60, 1):g}h" if isinstance(sleep, (int, float)) else "恢复未记", size=12, color=SUB),
            ],
            spacing=8,
        ),
        bgcolor=SURFACE,
        border_radius=6,
        padding=8,
    )


def _render_raw_list(model: Mapping[str, Any], on_toggle: Callable[[Any], None] | None) -> ft.Container:
    cfg: DataPageConfig = model["config"]
    rows = [_raw_day_line(item) for item in model.get("raw_days", [])] if cfg.raw_expanded else []
    return _card(
        ft.Column(
            [
                ft.Row([
                    _text("原始逐日列表", size=15, weight="bold"),
                    ft.IconButton(
                        icon=ft.Icons.EXPAND_LESS if cfg.raw_expanded else ft.Icons.EXPAND_MORE,
                        tooltip="收起" if cfg.raw_expanded else "展开",
                        icon_color=SUB,
                        on_click=on_toggle,
                    ),
                ], alignment="spaceBetween"),
                *rows,
            ],
            spacing=6,
        )
    )


def build_data_page_view(
    records: Any,
    *,
    end_date: str | date,
    config: DataPageConfig | None = None,
    on_period_change: Callable[[int], None] | None = None,
    on_tab_change: Callable[[str], None] | None = None,
    on_chart_change: Callable[[str], None] | None = None,
    on_add_record: Callable[[str], None] | None = None,
    on_exercise_trends: Callable[[Any], None] | None = None,
    on_action_trend_open: Callable[[Any], None] | None = None,
    on_action_trend_close: Callable[[Any], None] | None = None,
    on_selected_exercise_change: Callable[[str], None] | None = None,
    on_body_part_filter_change: Callable[[str], None] | None = None,
    on_selected_date_change: Callable[[str], None] | None = None,
    on_calendar_event_change: Callable[[str, str], None] | None = None,
    on_toggle_raw: Callable[[Any], None] | None = None,
) -> ft.Column:
    """Return a reusable Flet data page with trend, calendar, summary and raw rows."""

    cfg = config or DataPageConfig()
    model = build_data_page_model(records, end_date=end_date, config=cfg)
    period_row = ft.Row(
        [
            _chip(f"{days}天", cfg.period_days == days, None if on_period_change is None else lambda e, value=days: on_period_change(value))
            for days in PERIOD_OPTIONS
        ],
        spacing=6,
    )
    tab_row = ft.Row(
        [
            _chip(tab, cfg.active_tab == tab, None if on_tab_change is None else lambda e, value=tab: on_tab_change(value))
            for tab in VIEW_TABS
        ],
        spacing=6,
    )
    chart_row = ft.Row(
        [
            _chip(label, cfg.chart_kind == key, None if on_chart_change is None else lambda e, value=key: on_chart_change(value))
            for key, label in CHART_OPTIONS
        ],
        spacing=6,
    )

    body: ft.Control
    if cfg.active_tab == "月历":
        body = _render_calendar(model, on_selected_date_change, on_calendar_event_change)
    elif cfg.active_tab == "汇总":
        body = _render_summary(model)
    else:
        open_action_trend = on_action_trend_open or on_exercise_trends
        body = _render_trend_chart(
            model,
            on_add_record,
            open_action_trend,
            on_action_trend_close,
            on_selected_exercise_change,
            on_body_part_filter_change,
        )

    return ft.Column(
        [
            _card(ft.Column([ft.Row([_text("数据", size=20, weight="bold"), _text("默认7天，可切30/90", size=12, color=SUB, weight="bold")], alignment="spaceBetween"), period_row, tab_row], spacing=10)),
            chart_row if cfg.active_tab == "趋势" else ft.Container(height=0),
            body,
            _render_raw_list(model, on_toggle_raw),
        ],
        spacing=8,
    )


def build_main_data_page_hook(
    *,
    state_name: str = "data_page_state",
    records_name: str = "records",
    refresh_name: str = "refresh",
    selected_date_name: str = "selected_date",
) -> str:
    """Return the small ``main.py`` hook body needed to mount this component."""

    return f'''from analytics_views import DataPageConfig, build_data_page_view

{state_name} = {{"period_days": 7, "active_tab": "趋势", "chart_kind": "weight", "body_part_filter": "全部", "selected_date": None, "action_trend_open": False, "selected_exercise": None, "raw_expanded": False}}

def render_data_page():
    def set_period(days):
        {state_name}["period_days"] = days
        {refresh_name}()

    def set_tab(tab):
        {state_name}["active_tab"] = tab
        {refresh_name}()

    def set_chart(kind):
        {state_name}["chart_kind"] = kind
        {refresh_name}()

    def set_body_part(part):
        {state_name}["body_part_filter"] = part
        {refresh_name}()

    def open_action_trend(_):
        {state_name}["action_trend_open"] = True
        {refresh_name}()

    def close_action_trend(_):
        {state_name}["action_trend_open"] = False
        {refresh_name}()

    def set_exercise(exercise):
        {state_name}["selected_exercise"] = exercise
        {state_name}["action_trend_open"] = True
        {refresh_name}()

    def set_calendar_date(day):
        {state_name}["selected_date"] = day
        {refresh_name}()

    def toggle_raw(_):
        {state_name}["raw_expanded"] = not {state_name}.get("raw_expanded", False)
        {refresh_name}()

    return build_data_page_view(
        {records_name},
        end_date={selected_date_name},
        config=DataPageConfig(**{state_name}),
        on_period_change=set_period,
        on_tab_change=set_tab,
        on_chart_change=set_chart,
        on_add_record=lambda kind: set_view("recovery" if kind in {{"weight", "bodyfat", "circumference"}} else "training" if kind == "training" else "diet"),
        on_action_trend_open=open_action_trend,
        on_action_trend_close=close_action_trend,
        on_selected_exercise_change=set_exercise,
        on_body_part_filter_change=set_body_part,
        on_selected_date_change=set_calendar_date,
        on_toggle_raw=toggle_raw,
    )'''


__all__ = [
    "CHART_OPTIONS",
    "BODY_PART_FILTERS",
    "PERIOD_OPTIONS",
    "VIEW_TABS",
    "DataPageConfig",
    "build_data_page_model",
    "build_data_page_view",
    "build_main_data_page_hook",
]
