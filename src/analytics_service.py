"""Pure analytics helpers for daily health and training records.

The functions in this module deliberately do not depend on Flet or application
state.  They accept JSON-compatible mappings and return JSON-compatible values.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
import math
from typing import Any

from training_clock_service import session_elapsed_seconds
from training_models import normalize_recording_mode


BODY_PART_ORDER = ("胸", "背", "肩", "腿", "二头", "三头", "腹", "有氧")
DAY_TYPES = {"高碳日", "中碳日", "低碳日"}

_BODY_PART_ALIASES = {
    "胸": "胸", "胸部": "胸", "胸大肌": "胸",
    "背": "背", "背部": "背", "背阔肌": "背",
    "肩": "肩", "肩部": "肩", "三角肌": "肩",
    "腿": "腿", "腿部": "腿", "下肢": "腿", "臀": "腿", "臀部": "腿",
    "二头": "二头", "肱二头": "二头", "肱二头肌": "二头",
    "三头": "三头", "肱三头": "三头", "肱三头肌": "三头",
    "腹": "腹", "腹部": "腹", "核心": "腹",
    "有氧": "有氧", "心肺": "有氧",
}


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


def normalize_body_part(value: Any) -> str:
    """Normalize common current and legacy body-part labels."""
    text = str(value or "").strip()
    if not text:
        return ""
    if text in _BODY_PART_ALIASES:
        return _BODY_PART_ALIASES[text]
    for alias in sorted(_BODY_PART_ALIASES, key=len, reverse=True):
        if alias in text:
            return _BODY_PART_ALIASES[alias]
    return text


def format_body_parts(parts: list[str] | tuple[str, ...], *, compact: bool = False) -> str:
    """Return a stable body-part combination such as ``胸 + 三头 + 腹``."""
    unique = {normalize_body_part(item) for item in parts}
    unique.discard("")
    ordered = [item for item in BODY_PART_ORDER if item in unique]
    ordered.extend(sorted(unique.difference(BODY_PART_ORDER)))
    if compact and len(ordered) > 2:
        return f"{ordered[0]}+{ordered[1]}+{len(ordered) - 2}"
    separator = "+" if compact else " + "
    return separator.join(ordered)


def _raw_sessions(training: Any) -> list[dict[str, Any]]:
    if not isinstance(training, Mapping):
        return []
    candidates = [item for item in _list(training.get("sessions")) if isinstance(item, Mapping)]
    current = training.get("session")
    if isinstance(current, Mapping):
        candidates.append(current)

    result: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for candidate in candidates:
        item = dict(candidate)
        identity = str(item.get("id") or "")
        key = f"id:{identity}" if identity else f"value:{item!r}"
        if key in positions:
            result[positions[key]] = item
        else:
            positions[key] = len(result)
            result.append(item)
    return result


def _completed_formal_sets(exercise: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if normalize_recording_mode(exercise.get("recording_mode")) != "strength":
        return []
    return [
        item for item in _list(exercise.get("sets"))
        if isinstance(item, Mapping)
        and bool(item.get("completed"))
        and not bool(item.get("warmup", item.get("is_warmup", False)))
        and (_number(item.get("reps")) or 0) > 0
    ]


def _structured_session_summary(session: Mapping[str, Any]) -> dict[str, Any] | None:
    exercises = [item for item in _list(session.get("exercises")) if isinstance(item, Mapping)]
    duration = _number(session.get("total_duration_min"))
    if str(session.get("status") or "").strip().lower() == "active":
        duration = round(session_elapsed_seconds(session, datetime.now()) / 60, 2)
    completed_sets: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    completed_cardio: list[Mapping[str, Any]] = []
    completed_timed: list[Mapping[str, Any]] = []
    meaningful_exercises: list[Mapping[str, Any]] = []
    for exercise in exercises:
        if str(exercise.get("name") or "").strip() or str(exercise.get("body_part") or "").strip():
            meaningful_exercises.append(exercise)
        completed_sets.extend((exercise, item) for item in _completed_formal_sets(exercise))
        mode = normalize_recording_mode(exercise.get("recording_mode"))
        if bool(exercise.get("completed")) and mode == "cardio":
            completed_cardio.append(exercise)
        elif bool(exercise.get("completed")) and mode == "timed":
            completed_timed.append(exercise)

    status = str(session.get("status") or "").strip().lower()
    has_completed_work = bool(completed_sets or completed_cardio or completed_timed)
    has_timed_work = duration is not None and duration > 0
    is_legacy = any(
        str(item.get("legacy_detail") or "").strip() or str(item.get("legacy_intensity") or "").strip()
        for item in meaningful_exercises
    )
    has_legacy_work = is_legacy and bool(meaningful_exercises)
    if not (has_completed_work or has_timed_work or has_legacy_work):
        return None
    if status == "planned" and not (has_completed_work or has_timed_work):
        return None

    names: list[str] = []
    parts: list[str] = []
    for exercise in meaningful_exercises:
        name = str(exercise.get("name") or exercise.get("legacy_detail") or "").strip()
        part = normalize_body_part(exercise.get("body_part"))
        if name and name not in names:
            names.append(name)
        if part and part not in parts:
            parts.append(part)

    volume = 0.0
    for _, training_set in completed_sets:
        weight = _number(training_set.get("weight_kg", training_set.get("weight")))
        reps = _number(training_set.get("reps"))
        if weight is not None and reps is not None:
            volume += max(0.0, weight) * max(0.0, reps)

    cardio_duration = sum(max(0.0, _number(item.get("duration_seconds")) or 0.0) for item in completed_cardio) / 60
    timed_duration = sum(max(0.0, _number(item.get("duration_seconds")) or 0.0) for item in completed_timed) / 60
    cardio_distance = sum(max(0.0, _number(item.get("distance_km")) or 0.0) for item in completed_cardio)

    return {
        "id": str(session.get("id") or ""),
        "status": status or "completed",
        "body_parts": parts,
        "exercises": names,
        "formal_sets": len(completed_sets),
        "volume_kg": round(volume, 2),
        "duration_min": round(max(0.0, duration or 0.0), 2),
        "cardio_duration_min": round(cardio_duration, 2),
        "timed_duration_min": round(timed_duration, 2),
        "distance_km": round(cardio_distance, 2),
        "cardio_exercises": len(completed_cardio),
        "timed_exercises": len(completed_timed),
        "structured": not is_legacy,
    }


def _legacy_training_summary(training: Any) -> dict[str, Any] | None:
    if isinstance(training, list):
        targets = training
        source: Mapping[str, Any] = {}
    elif isinstance(training, Mapping):
        targets = _list(training.get("targets"))
        source = training
    else:
        return None

    names: list[str] = []
    parts: list[str] = []
    for target in targets:
        if not isinstance(target, Mapping):
            continue
        part = normalize_body_part(target.get("target"))
        name = str(target.get("detail") or target.get("target") or "").strip()
        if not (part or name or str(target.get("note") or "").strip()):
            continue
        if name and name not in names:
            names.append(name)
        if part and part not in parts:
            parts.append(part)

    duration = _number(source.get("total_duration_min"))
    calories = _number(source.get("total_calories_kcal"))
    note = str(source.get("summary_note") or "").strip()
    if not (names or parts or (duration or 0) > 0 or (calories or 0) > 0 or note):
        return None
    return {
        "id": "legacy",
        "status": "completed",
        "body_parts": parts,
        "exercises": names,
        "formal_sets": 0,
        "volume_kg": 0.0,
        "duration_min": round(max(0.0, duration or 0.0), 2),
        "cardio_duration_min": 0.0,
        "timed_duration_min": 0.0,
        "distance_km": 0.0,
        "cardio_exercises": 0,
        "timed_exercises": 0,
        "structured": False,
    }


def summarize_daily_training(record_or_training: Any, record_date: str = "") -> dict[str, Any]:
    """Summarize all effective workouts in one day without inventing data."""
    value = record_or_training
    if isinstance(value, Mapping) and "training" in value:
        value = value.get("training")

    sessions = []
    if isinstance(value, Mapping):
        sessions = [
            summary for raw in _raw_sessions(value)
            if (summary := _structured_session_summary(raw)) is not None
        ]
    elif isinstance(value, list):
        sessions = []

    # Only use legacy targets when no structured/current session represents them.
    if not sessions:
        legacy = _legacy_training_summary(value)
        if legacy is not None:
            sessions = [legacy]

    parts: list[str] = []
    exercises: list[str] = []
    for session in sessions:
        for part in session["body_parts"]:
            if part not in parts:
                parts.append(part)
        for exercise in session["exercises"]:
            if exercise not in exercises:
                exercises.append(exercise)

    return {
        "date": record_date,
        "has_training": bool(sessions),
        "session_count": len(sessions),
        "body_parts": [part for part in BODY_PART_ORDER if part in parts]
        + sorted(set(parts).difference(BODY_PART_ORDER)),
        "body_part_label": format_body_parts(parts),
        "exercises": exercises,
        "formal_sets": sum(item["formal_sets"] for item in sessions),
        "volume_kg": round(sum(item["volume_kg"] for item in sessions), 2),
        "duration_min": round(sum(item["duration_min"] for item in sessions), 2),
        "cardio_duration_min": round(sum(item["cardio_duration_min"] for item in sessions), 2),
        "timed_duration_min": round(sum(item["timed_duration_min"] for item in sessions), 2),
        "distance_km": round(sum(item["distance_km"] for item in sessions), 2),
        "cardio_exercises": sum(item["cardio_exercises"] for item in sessions),
        "timed_exercises": sum(item["timed_exercises"] for item in sessions),
        "sessions": sessions,
    }


def assess_low_carb_training(
    record_or_training: Any,
    *,
    min_formal_sets: int = 6,
    min_volume_kg: float = 2000.0,
) -> dict[str, Any]:
    """Assess whether structured leg/back work is substantial for a low-carb day."""
    value = record_or_training
    if isinstance(value, Mapping) and "training" in value:
        value = value.get("training")
    target_parts = {"腿", "背"}
    target_sets = 0
    target_volume = 0.0
    target_actions: list[str] = []
    has_structured_target = False

    for raw_session in _raw_sessions(value):
        session = _structured_session_summary(raw_session)
        if session is None or not session["structured"]:
            continue
        for exercise in _list(raw_session.get("exercises")):
            if not isinstance(exercise, Mapping) or normalize_body_part(exercise.get("body_part")) not in target_parts:
                continue
            has_structured_target = True
            name = str(exercise.get("name") or "").strip()
            if name and name not in target_actions:
                target_actions.append(name)
            sets = _completed_formal_sets(exercise)
            target_sets += len(sets)
            for item in sets:
                weight = _number(item.get("weight_kg", item.get("weight")))
                reps = _number(item.get("reps"))
                if weight is not None and reps is not None:
                    target_volume += max(0.0, weight) * max(0.0, reps)

    set_trigger = target_sets >= max(1, int(min_formal_sets))
    volume_trigger = target_volume >= max(0.0, float(min_volume_kg))
    should_warn = has_structured_target and (set_trigger or volume_trigger)
    reasons = []
    if set_trigger:
        reasons.append(f"腿/背正式组达到{target_sets}组")
    if volume_trigger:
        reasons.append(f"腿/背容量达到{round(target_volume, 1):g}kg")
    return {
        "should_warn": should_warn,
        "has_structured_leg_or_back": has_structured_target,
        "formal_sets": target_sets,
        "volume_kg": round(target_volume, 2),
        "exercises": target_actions,
        "reasons": reasons,
    }


def normalize_body_measurement(record: Any, record_date: str = "") -> dict[str, Any]:
    """Separate explicit measurements from values merely carried into a record.

    Canonical write format is ``profile.measurement`` with ``measured_at`` and
    one or both metric values.  ``profile.measured_at`` plus profile values is
    also accepted for a lightweight migration path.  Unmarked legacy profile
    values are returned as carried values and excluded from trend metrics.
    """
    profile = _mapping(_mapping(record).get("profile"))
    measurement = _mapping(profile.get("measurement"))
    measured_at = str(measurement.get("measured_at") or profile.get("measured_at") or "").strip()
    measured_weight = _number(measurement.get("weight_kg"))
    measured_bodyfat = _number(measurement.get("bodyfat_percent"))
    if measured_at and not measurement:
        measured_weight = _number(profile.get("weight_kg"))
        measured_bodyfat = _number(profile.get("bodyfat_percent"))

    weight_marked = bool(measurement.get("weight_measured", measured_weight is not None and bool(measured_at)))
    bodyfat_marked = bool(measurement.get("bodyfat_measured", measured_bodyfat is not None and bool(measured_at)))
    is_weight_measured = measured_weight is not None and weight_marked
    is_bodyfat_measured = measured_bodyfat is not None and bodyfat_marked

    return {
        "date": record_date,
        "measured_at": measured_at or None,
        "weight_kg": measured_weight if is_weight_measured else None,
        "bodyfat_percent": measured_bodyfat if is_bodyfat_measured else None,
        "carried_weight_kg": None if is_weight_measured else _number(profile.get("weight_kg")),
        "carried_bodyfat_percent": None if is_bodyfat_measured else _number(profile.get("bodyfat_percent")),
        "is_weight_measured": is_weight_measured,
        "is_bodyfat_measured": is_bodyfat_measured,
        "is_measured": is_weight_measured or is_bodyfat_measured,
    }


def make_body_measurement(
    *, weight_kg: Any = None, bodyfat_percent: Any = None, measured_at: str
) -> dict[str, Any]:
    """Build the canonical value for ``profile.measurement``."""
    result: dict[str, Any] = {"measured_at": str(measured_at).strip()}
    weight = _number(weight_kg)
    bodyfat = _number(bodyfat_percent)
    if weight is not None:
        result["weight_kg"] = weight
        result["weight_measured"] = True
    if bodyfat is not None:
        result["bodyfat_percent"] = bodyfat
        result["bodyfat_measured"] = True
    return result


def _has_food(record: Mapping[str, Any]) -> bool:
    meals = record.get("meals")
    if isinstance(meals, Mapping) and any(
        any(isinstance(item, Mapping) for item in _list(items)) for items in meals.values()
    ):
        return True
    total = _mapping(record.get("daily_total"))
    return any(_number(total.get(key)) not in (None, 0) for key in ("kcal", "carb", "protein", "fat"))


def _sleep_minutes(record: Mapping[str, Any]) -> float | None:
    sleep = _mapping(record.get("sleep"))
    total = _number(sleep.get("total_minutes"))
    has_detail = bool(str(sleep.get("bed_time") or "").strip() or str(sleep.get("wake_time") or "").strip() or _list(sleep.get("naps")))
    return total if total is not None and (total > 0 or has_detail) else None


def _water_total(record: Mapping[str, Any]) -> float | None:
    water = _mapping(record.get("water"))
    records = [_number(item) for item in _list(water.get("records_ml"))]
    records = [item for item in records if item is not None]
    if records:
        return round(sum(records), 2)
    total = _number(water.get("total_ml"))
    return total if total is not None and total > 0 else None


def _diet_values(record: Mapping[str, Any]) -> dict[str, Any]:
    if not _has_food(record):
        return {"kcal": None, "carb": None, "protein": None, "fat": None, "compliant": None}
    total = _mapping(record.get("daily_total"))
    profile = _mapping(record.get("profile"))
    compliance = _mapping(profile.get("compliance"))
    status = str(compliance.get("status") or "").strip()
    compliant = True if status in {"达标", "已达标"} else False if status in {"未达标", "超标"} else None
    return {
        "kcal": _number(total.get("kcal")),
        "carb": _number(total.get("carb")),
        "protein": _number(total.get("protein")),
        "fat": _number(total.get("fat")),
        "compliant": compliant,
    }


def build_period_series(records: Any, *, end_date: str | date, days: int) -> list[dict[str, Any]]:
    """Build aligned 7/30/90-day series; missing records remain ``None``."""
    if days not in {7, 30, 90}:
        raise ValueError("days must be one of 7, 30, or 90")
    end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
    if not isinstance(end, date):
        raise TypeError("end_date must be an ISO date string or date")
    source = records if isinstance(records, Mapping) else {}
    start = end - timedelta(days=days - 1)
    result = []
    for offset in range(days):
        current = start + timedelta(days=offset)
        key = current.isoformat()
        raw = source.get(key)
        record = raw if isinstance(raw, Mapping) else None
        if record is None:
            result.append({"date": key, "body": None, "diet": None, "training": None, "recovery": None, "targets": None})
            continue

        measurement = normalize_body_measurement(record, key)
        body = {
            "weight_kg": measurement["weight_kg"],
            "bodyfat_percent": measurement["bodyfat_percent"],
            "measured_at": measurement["measured_at"],
        }
        if not measurement["is_measured"]:
            body = None

        diet_values = _diet_values(record)
        profile = _mapping(record.get("profile"))
        day_type = str(profile.get("day_type") or "").strip()
        diet = {**diet_values, "day_type": day_type if day_type in DAY_TYPES else None}
        if not _has_food(record) and diet["day_type"] is None:
            diet = None

        daily_training = summarize_daily_training(record, key)
        training = daily_training if daily_training["has_training"] else None
        water = _water_total(record)
        sleep = _sleep_minutes(record)
        recovery_data = _mapping(record.get("recovery"))
        fatigue = str(recovery_data.get("fatigue") or "").strip() or None
        if fatigue is None and training is not None:
            training_data = _mapping(record.get("training"))
            fatigue_text = str(training_data.get("fatigue_status") or "").strip()
            fatigue = fatigue_text or None
        water_target = _number(_mapping(record.get("water")).get("target_ml"))
        recovery = {"water_ml": water, "water_target_ml": water_target, "sleep_minutes": sleep, "fatigue": fatigue}
        if water is None and sleep is None and fatigue is None:
            recovery = None
        targets = dict(_mapping(profile.get("targets"))) or None
        result.append({"date": key, "body": body, "diet": diet, "training": training, "recovery": recovery, "targets": targets})
    return result


def calendar_day_summary(record: Any, record_date: str = "") -> dict[str, Any]:
    """Return the three-line calendar-cell data for one date."""
    rec = record if isinstance(record, Mapping) else {}
    profile = _mapping(rec.get("profile"))
    calorie_target = _number(_mapping(profile.get("targets")).get("calorie_target"))
    if calorie_target is not None and (not math.isfinite(calorie_target) or calorie_target <= 0):
        calorie_target = None
    day_type = str(profile.get("day_type") or "").strip()
    day_type = day_type if day_type in DAY_TYPES else None
    training = summarize_daily_training(rec, record_date)
    event = _mapping(rec.get("calendar_event"))
    event_type = str(event.get("type") or "").strip().lower()
    event_text = str(event.get("text") or "").strip()

    if training["has_training"]:
        activity_type = "training"
        activity = format_body_parts(training["body_parts"], compact=True)
    elif event_type == "rest":
        activity_type = "rest"
        activity = "休息"
    elif event_type == "custom" and event_text:
        activity_type = "custom"
        activity = event_text[:6]
    else:
        activity_type = None
        activity = None

    return {
        "date": record_date,
        "day_type": day_type,
        "activity_type": activity_type,
        "activity": activity,
        "body_parts": training["body_parts"],
        "session_count": training["session_count"],
        "calorie_target": calorie_target,
        "event_text": event_text or None,
        "lines": [item for item in (day_type, activity) if item],
    }


__all__ = [
    "assess_low_carb_training",
    "build_period_series",
    "calendar_day_summary",
    "format_body_parts",
    "make_body_measurement",
    "normalize_body_measurement",
    "normalize_body_part",
    "summarize_daily_training",
]
