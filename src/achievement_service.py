"""Achievement progress calculated from real app records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

from achievement_definitions import AchievementDefinition, achievement_definitions
from analytics_service import normalize_body_measurement, summarize_daily_training
from training_service import normalize_training_data


ACHIEVEMENT_STATE_VERSION = 2
_STATE_VERSION_KEY = "_state_version"
_CELEBRATED_KEY = "_celebrated"
_PENDING_KEY = "_pending"


@dataclass(frozen=True, slots=True)
class AchievementResult:
    id: str
    title: str
    description: str
    metric: str
    target: float
    current: float
    progress: float
    unlocked: bool
    tier: str | None
    kind: str
    hidden: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


_BODY_PART_ALIASES: dict[str, str] = {
    "胸": "胸",
    "胸部": "胸",
    "胸大肌": "胸",
    "chest": "胸",
    "pec": "胸",
    "pecs": "胸",
    "背": "背",
    "背部": "背",
    "背阔肌": "背",
    "back": "背",
    "lat": "背",
    "lats": "背",
    "肩": "肩",
    "肩部": "肩",
    "三角肌": "肩",
    "shoulder": "肩",
    "shoulders": "肩",
    "腿": "腿",
    "腿部": "腿",
    "下肢": "腿",
    "臀": "腿",
    "臀部": "腿",
    "leg": "腿",
    "legs": "腿",
    "glute": "腿",
    "glutes": "腿",
    "二头": "二头",
    "肱二头": "二头",
    "肱二头肌": "二头",
    "biceps": "二头",
    "bicep": "二头",
    "三头": "三头",
    "肱三头": "三头",
    "肱三头肌": "三头",
    "triceps": "三头",
    "tricep": "三头",
    "腹": "腹",
    "腹部": "腹",
    "核心": "腹",
    "core": "腹",
    "abs": "腹",
    "有氧": "有氧",
    "心肺": "有氧",
    "cardio": "有氧",
}


def _body_part(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    folded = text.casefold()
    if folded in _BODY_PART_ALIASES:
        return _BODY_PART_ALIASES[folded]
    if text in _BODY_PART_ALIASES:
        return _BODY_PART_ALIASES[text]
    for alias, normalized in sorted(_BODY_PART_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in folded or alias in text:
            return normalized
    return text


def _has_nutrition(record: Mapping[str, Any]) -> bool:
    meals = record.get("meals")
    if isinstance(meals, Mapping):
        for items in meals.values():
            if any(isinstance(item, Mapping) for item in _list(items)):
                return True
    total = _mapping(record.get("daily_total"))
    return any((_number(total.get(key)) or 0) > 0 for key in ("kcal", "carb", "protein", "fat"))


def _water_ml(record: Mapping[str, Any]) -> float:
    water = _mapping(record.get("water"))
    entries = [_number(item) for item in _list(water.get("records_ml"))]
    entries = [item for item in entries if item is not None]
    if entries:
        return round(sum(entries), 2)
    return round(max(0.0, _number(water.get("total_ml")) or 0.0), 2)


def _has_sleep(record: Mapping[str, Any]) -> bool:
    sleep = _mapping(record.get("sleep"))
    minutes = _number(sleep.get("total_minutes"))
    has_detail = bool(str(sleep.get("bed_time") or "").strip() or str(sleep.get("wake_time") or "").strip() or _list(sleep.get("naps")))
    return bool((minutes is not None and minutes > 0) or has_detail)


def _meal_items(record: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    meals = _mapping(record.get("meals"))
    result: dict[str, list[Mapping[str, Any]]] = {}
    for key, items in meals.items():
        result[str(key).strip()] = [item for item in _list(items) if isinstance(item, Mapping)]
    return result


def _meal_day(meals: Mapping[str, list[Mapping[str, Any]]], *aliases: str) -> bool:
    return any(bool(meals.get(alias)) for alias in aliases)


def _sleep_minutes(record: Mapping[str, Any]) -> float | None:
    minutes = _number(_mapping(record.get("sleep")).get("total_minutes"))
    return max(0.0, minutes) if minutes is not None and minutes > 0 else None


def _circumference_count(record: Mapping[str, Any]) -> int:
    profile = _mapping(record.get("profile"))
    measurement = _mapping(profile.get("measurement"))
    circumference = _mapping(profile.get("circumference"))
    measured_at = str(
        measurement.get("measured_at")
        or circumference.get("measured_at")
        or profile.get("measured_at")
        or ""
    ).strip()
    if not measured_at:
        return 0
    keys = ("waist_cm", "chest_cm", "hip_cm", "arm_cm", "thigh_cm", "calf_cm")
    return sum(
        1
        for key in keys
        if _number(measurement.get(key)) is not None
        or _number(circumference.get(key)) is not None
        or _number(profile.get(key)) is not None
    )


def _streak(dates: set[str]) -> int:
    parsed = sorted(date.fromisoformat(item) for item in dates if _is_iso_date(item))
    if not parsed:
        return 0
    best = current = 1
    for previous, item in zip(parsed, parsed[1:]):
        if (item - previous).days == 1:
            current += 1
        else:
            current = 1
        best = max(best, current)
    return best


def _training_week_stats(dates: set[str]) -> tuple[int, int]:
    weeks: dict[date, set[date]] = {}
    for value in dates:
        if not _is_iso_date(value):
            continue
        item = date.fromisoformat(value)
        monday = item - timedelta(days=item.weekday())
        weeks.setdefault(monday, set()).add(item)
    active = sorted(week for week, days in weeks.items() if len(days) >= 2)
    if not active:
        return len(weeks), 0
    best = current = 1
    for previous, item in zip(active, active[1:]):
        current = current + 1 if (item - previous).days == 7 else 1
        best = max(best, current)
    return len(weeks), best


def _session_detail(session: Mapping[str, Any]) -> dict[str, float]:
    stats = {"completed_reps": 0.0, "loaded_sets": 0.0, "bodyweight_sets": 0.0, "formal_sets": 0.0}
    for exercise in _list(session.get("exercises")):
        if not isinstance(exercise, Mapping):
            continue
        for training_set in _list(exercise.get("sets")):
            if not isinstance(training_set, Mapping) or not training_set.get("completed"):
                continue
            if training_set.get("warmup", training_set.get("is_warmup", False)):
                continue
            reps = _number(training_set.get("reps"))
            if reps is None or reps <= 0:
                continue
            weight = _number(training_set.get("weight_kg", training_set.get("weight"))) or 0
            stats["formal_sets"] += 1
            stats["completed_reps"] += reps
            stats["loaded_sets" if weight > 0 else "bodyweight_sets"] += 1
    return stats


def _raw_training_sessions(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    training = _mapping(record.get("training"))
    sessions = [item for item in _list(training.get("sessions")) if isinstance(item, Mapping)]
    current = training.get("session")
    if isinstance(current, Mapping):
        sessions.append(current)
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for session in sessions:
        identity = str(session.get("id") or "").strip()
        marker = f"id:{identity}" if identity else repr(dict(session))
        if marker not in seen:
            seen.add(marker)
            result.append(session)
    return result


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _comeback(dates: set[str]) -> bool:
    parsed = sorted(date.fromisoformat(item) for item in dates if _is_iso_date(item))
    return any((item - previous).days >= 14 for previous, item in zip(parsed, parsed[1:]))


def _balanced_week(day_flags: Mapping[str, Mapping[str, bool]]) -> bool:
    parsed = sorted(date.fromisoformat(item) for item in day_flags if _is_iso_date(item))
    for index, start in enumerate(parsed):
        window = [item.isoformat() for item in parsed[index:] if 0 <= (item - start).days <= 6]
        if len(window) < 5:
            continue
        training = sum(1 for key in window if day_flags[key]["training"])
        nutrition = sum(1 for key in window if day_flags[key]["nutrition"])
        water = sum(1 for key in window if day_flags[key]["water"])
        sleep = sum(1 for key in window if day_flags[key]["sleep"])
        if training >= 3 and nutrition >= 5 and water >= 5 and sleep >= 5:
            return True
    return False


def _apply_training_summary(
    metrics: dict[str, float],
    *,
    record_date: str,
    summary: Mapping[str, Any],
    training_dates: set[str],
    body_parts: set[str],
    exercises: set[str],
) -> None:
    if not summary.get("has_training"):
        return
    training_dates.add(record_date)
    metrics["training_sessions"] += _number(summary.get("session_count")) or 0
    metrics["formal_sets"] += _number(summary.get("formal_sets")) or 0
    metrics["volume_kg"] += _number(summary.get("volume_kg")) or 0
    metrics["duration_min"] += _number(summary.get("duration_min")) or 0
    for part in _list(summary.get("body_parts")):
        text = _body_part(part)
        if text:
            body_parts.add(text)
    for exercise in _list(summary.get("exercises")):
        text = str(exercise).strip()
        if text:
            exercises.add(text.casefold())


def achievement_metric_snapshot(records: Any, training_data: Any = None) -> dict[str, float]:
    """Build aggregate achievement metrics from daily records and training store data."""
    source = records if isinstance(records, Mapping) else {}
    metrics: dict[str, float] = {item.metric: 0.0 for item in achievement_definitions()}
    training_dates: set[str] = set()
    body_parts: set[str] = set()
    exercises: set[str] = set()
    foods: set[str] = set()
    measurement_months: set[str] = set()
    water_dates: set[str] = set()
    sleep_dates: set[str] = set()
    day_parts: dict[str, set[str]] = {}
    known_session_ids: set[str] = set()
    day_flags: dict[str, dict[str, bool]] = {}

    for key, raw_record in source.items():
        record_date = str(_mapping(raw_record).get("date") or key)
        record = _mapping(raw_record)
        summary = summarize_daily_training(record, record_date)
        _apply_training_summary(
            metrics,
            record_date=record_date,
            summary=summary,
            training_dates=training_dates,
            body_parts=body_parts,
            exercises=exercises,
        )
        parts_today = {_body_part(item) for item in _list(summary.get("body_parts")) if str(item).strip()}
        parts_today.discard("")
        day_parts.setdefault(record_date, set()).update(parts_today)
        for session in _list(summary.get("sessions")):
            if isinstance(session, Mapping) and str(session.get("id") or "").strip():
                known_session_ids.add(str(session.get("id")))
            if isinstance(session, Mapping) and len(_list(session.get("body_parts"))) >= 2:
                metrics["multi_part_sessions"] += 1
                metrics["double_session_day"] = 1
        for raw_session in _raw_training_sessions(record):
            details = _session_detail(raw_session)
            metrics["completed_reps"] += details["completed_reps"]
            metrics["loaded_sets"] += details["loaded_sets"]
            metrics["bodyweight_sets"] += details["bodyweight_sets"]
            if details["formal_sets"] >= 3:
                metrics["marathon_session"] = 1

        has_nutrition = _has_nutrition(record)
        meals = _meal_items(record)
        meal_items = [item for items in meals.values() for item in items]
        metrics["meal_entries"] += len(meal_items)
        for item in meal_items:
            name = str(item.get("name") or item.get("food_name") or "").strip().casefold()
            if name:
                foods.add(name)
        meal_aliases = {
            "breakfast_days": ("早餐", "breakfast"),
            "lunch_days": ("午餐", "lunch"),
            "dinner_days": ("晚餐", "dinner"),
            "preworkout_days": ("练前", "练前餐", "preworkout", "pre_workout"),
            "postworkout_days": ("练后", "练后餐", "postworkout", "post_workout"),
            "snack_days": ("偷吃", "加餐", "snack"),
        }
        for metric, aliases in meal_aliases.items():
            metrics[metric] += 1 if _meal_day(meals, *aliases) else 0
        daily_total = _mapping(record.get("daily_total"))
        macros = [_number(daily_total.get(key)) for key in ("kcal", "carb", "protein", "fat")]
        if all(value is not None and value >= 0 for value in macros) and any(value > 0 for value in macros):
            metrics["macro_complete_days"] += 1
        if (_number(daily_total.get("protein")) or 0) > 0:
            metrics["protein_logged_days"] += 1
        day_type = str(_mapping(record.get("profile")).get("day_type") or "").strip()
        if day_type in {"高碳日", "中碳日", "低碳日"}:
            metrics["carb_cycle_days"] += 1

        water_ml = _water_ml(record)
        has_water = water_ml > 0
        has_water_goal = water_ml >= 2000
        has_sleep = _has_sleep(record)
        sleep_minutes = _sleep_minutes(record)
        measurement = normalize_body_measurement(record, record_date)
        circumference_count = _circumference_count(record)
        has_measurement = measurement["is_measured"] or circumference_count > 0
        metrics["nutrition_logged_days"] += 1 if has_nutrition else 0
        metrics["water_logged_days"] += 1 if has_water else 0
        metrics["water_goal_days"] += 1 if has_water_goal else 0
        metrics["water_liters"] += water_ml / 1000
        metrics["sleep_logged_days"] += 1 if has_sleep else 0
        metrics["sleep_duration_days"] += 1 if sleep_minutes is not None else 0
        metrics["restful_sleep_days"] += 1 if sleep_minutes is not None and 420 <= sleep_minutes <= 540 else 0
        metrics["sleep_hours"] += (sleep_minutes or 0) / 60
        recovery = _mapping(record.get("recovery"))
        has_recovery = has_water or has_sleep or bool(str(recovery.get("fatigue") or "").strip())
        metrics["recovery_logged_days"] += 1 if has_recovery else 0
        metrics["measurement_days"] += 1 if has_measurement else 0
        metrics["weight_measurement_days"] += 1 if measurement["is_weight_measured"] else 0
        metrics["bodyfat_measurement_days"] += 1 if measurement["is_bodyfat_measured"] else 0
        metrics["circumference_measurement_days"] += 1 if circumference_count else 0
        metrics["combined_measurement_days"] += 1 if (
            int(measurement["is_weight_measured"])
            + int(measurement["is_bodyfat_measured"])
            + circumference_count
        ) >= 2 else 0
        if has_measurement and _is_iso_date(record_date):
            measurement_months.add(record_date[:7])
        if has_water and _is_iso_date(record_date):
            water_dates.add(record_date)
        if has_sleep and _is_iso_date(record_date):
            sleep_dates.add(record_date)
        day_flags[record_date] = {
            "training": summary.get("has_training", False),
            "nutrition": has_nutrition,
            "water": has_water_goal,
            "sleep": has_sleep,
            "measurement": bool(has_measurement),
        }
        if all(day_flags[record_date].values()):
            metrics["perfect_record_day"] = 1

    if training_data is not None:
        normalized = normalize_training_data(training_data)
        for session in normalized.sessions:
            if session.id and session.id in known_session_ids:
                continue
            summary = summarize_daily_training({"session": session.to_dict()}, session.date)
            _apply_training_summary(
                metrics,
                record_date=session.date,
                summary=summary,
                training_dates=training_dates,
                body_parts=body_parts,
                exercises=exercises,
            )
            if summary.get("has_training"):
                day_flags.setdefault(session.date, {"training": False, "nutrition": False, "water": False, "sleep": False, "measurement": False})
                day_flags[session.date]["training"] = True
                parts = {_body_part(item) for item in _list(summary.get("body_parts")) if str(item).strip()}
                parts.discard("")
                day_parts.setdefault(session.date, set()).update(parts)
                if len(parts) >= 2:
                    metrics["double_session_day"] = 1
                    metrics["multi_part_sessions"] += 1
            details = _session_detail(session.to_dict())
            metrics["completed_reps"] += details["completed_reps"]
            metrics["loaded_sets"] += details["loaded_sets"]
            metrics["bodyweight_sets"] += details["bodyweight_sets"]
            if details["formal_sets"] >= 3:
                metrics["marathon_session"] = 1

    metrics["training_days"] = float(len(training_dates))
    metrics["unique_exercises"] = float(len(exercises))
    metrics["unique_foods"] = float(len(foods))
    metrics["body_part_variety"] = float(len(body_parts))
    metrics["training_streak"] = float(_streak(training_dates))
    metrics["training_weeks"], metrics["training_week_streak"] = map(float, _training_week_stats(training_dates))
    metrics["training_months"] = float(len({item[:7] for item in training_dates if _is_iso_date(item)}))
    metrics["seven_day_training_streak"] = 1 if metrics["training_week_streak"] >= 1 else 0
    metrics["water_streak"] = float(_streak(water_dates))
    metrics["sleep_streak"] = float(_streak(sleep_dates))
    metrics["measurement_months"] = float(len(measurement_months))
    for record_date, parts in day_parts.items():
        if "胸" in parts:
            metrics["chest_days"] += 1
        if "背" in parts:
            metrics["back_days"] += 1
        if "肩" in parts:
            metrics["shoulder_days"] += 1
        if "腿" in parts:
            metrics["leg_days"] += 1
        if parts.intersection({"二头", "三头"}):
            metrics["arm_days"] += 1
        if "腹" in parts:
            metrics["core_days"] += 1
    metrics["hundred_k_volume"] = 1 if metrics["volume_kg"] >= 100000 else 0
    metrics["all_body_parts"] = 1 if metrics["body_part_variety"] >= 8 else 0
    metrics["balanced_week"] = 1 if _balanced_week(day_flags) else 0
    metrics["comeback"] = 1 if _comeback(training_dates) else 0
    return {key: round(value, 2) for key, value in metrics.items()}


def evaluate_achievement(definition: AchievementDefinition, metrics: Mapping[str, float]) -> AchievementResult:
    current = float(metrics.get(definition.metric, 0) or 0)
    target = max(0.0, float(definition.target))
    progress = 1.0 if target == 0 else min(1.0, current / target)
    return AchievementResult(
        id=definition.id,
        title=definition.title,
        description=definition.description,
        metric=definition.metric,
        target=definition.target,
        current=current,
        progress=round(progress, 4),
        unlocked=current >= target,
        tier=definition.tier,
        kind=definition.kind,
        hidden=definition.hidden,
    )


def evaluate_achievements(records: Any, training_data: Any = None) -> list[dict[str, Any]]:
    """Return all achievement states in stable definition order."""
    metrics = achievement_metric_snapshot(records, training_data)
    return [evaluate_achievement(item, metrics).to_dict() for item in achievement_definitions()]


def normalize_achievement_unlock_state(value: Any) -> dict[str, Any]:
    """Normalize legacy unlock timestamps and the v2 celebration queue."""
    source = dict(value) if isinstance(value, Mapping) else {}
    has_v2_metadata = any(key in source for key in (_STATE_VERSION_KEY, _CELEBRATED_KEY, _PENDING_KEY))
    unlock_times = {
        str(key): str(item)
        for key, item in source.items()
        if not str(key).startswith("_") and item not in (None, "")
    }

    def unique_ids(raw: Any) -> list[str]:
        values = raw if isinstance(raw, (list, tuple)) else []
        result: list[str] = []
        for item in values:
            identity = str(item or "").strip()
            if identity and identity not in result:
                result.append(identity)
        return result

    # Legacy files only stored unlock timestamps. Treat those entries as
    # already acknowledged so an upgrade never floods the user with old wins.
    celebrated = unique_ids(source.get(_CELEBRATED_KEY)) if has_v2_metadata else list(unlock_times)
    pending = [
        identity
        for identity in unique_ids(source.get(_PENDING_KEY))
        if identity in unlock_times and identity not in celebrated
    ]
    return {
        "version": ACHIEVEMENT_STATE_VERSION,
        "unlock_times": unlock_times,
        "celebrated": celebrated,
        "pending": pending,
    }


def encode_achievement_unlock_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Persist v2 metadata while keeping timestamps readable by old builds."""
    normalized = normalize_achievement_unlock_state({
        **dict(state.get("unlock_times") or {}),
        _STATE_VERSION_KEY: ACHIEVEMENT_STATE_VERSION,
        _CELEBRATED_KEY: list(state.get("celebrated") or []),
        _PENDING_KEY: list(state.get("pending") or []),
    })
    return {
        **normalized["unlock_times"],
        _STATE_VERSION_KEY: ACHIEVEMENT_STATE_VERSION,
        _CELEBRATED_KEY: normalized["celebrated"],
        _PENDING_KEY: normalized["pending"],
    }


def register_achievement_unlocks(
    results: Any,
    stored: Any,
    unlocked_at: str,
) -> dict[str, Any]:
    """Record newly unlocked achievements and enqueue every unseen celebration."""
    state = normalize_achievement_unlock_state(stored)
    valid_results = [item for item in _list(results) if isinstance(item, Mapping)]
    valid_ids = {str(item.get("id") or "").strip() for item in valid_results}
    state["pending"] = [identity for identity in state["pending"] if identity in valid_ids]

    for item in valid_results:
        identity = str(item.get("id") or "").strip()
        if not identity or not item.get("unlocked"):
            continue
        if identity not in state["unlock_times"]:
            state["unlock_times"][identity] = str(unlocked_at)
        if identity not in state["celebrated"] and identity not in state["pending"]:
            state["pending"].append(identity)
    return encode_achievement_unlock_state(state)


def achievement_unlock_times(stored: Any) -> dict[str, str]:
    return dict(normalize_achievement_unlock_state(stored)["unlock_times"])


def pending_achievement_results(results: Any, stored: Any) -> list[dict[str, Any]]:
    """Return pending unlocked achievements in durable queue order."""
    state = normalize_achievement_unlock_state(stored)
    by_id = {
        str(item.get("id") or "").strip(): dict(item)
        for item in _list(results)
        if isinstance(item, Mapping) and item.get("unlocked")
    }
    return [by_id[identity] for identity in state["pending"] if identity in by_id]


def acknowledge_achievement_celebration(stored: Any, achievement_id: Any) -> dict[str, Any]:
    """Mark one celebration as shown without discarding the rest of the queue."""
    identity = str(achievement_id or "").strip()
    state = normalize_achievement_unlock_state(stored)
    state["pending"] = [item for item in state["pending"] if item != identity]
    if identity and identity in state["unlock_times"] and identity not in state["celebrated"]:
        state["celebrated"].append(identity)
    return encode_achievement_unlock_state(state)


__all__ = [
    "ACHIEVEMENT_STATE_VERSION",
    "AchievementResult",
    "acknowledge_achievement_celebration",
    "achievement_metric_snapshot",
    "achievement_unlock_times",
    "encode_achievement_unlock_state",
    "evaluate_achievement",
    "evaluate_achievements",
    "normalize_achievement_unlock_state",
    "pending_achievement_results",
    "register_achievement_unlocks",
]
