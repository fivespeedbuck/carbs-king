"""Pure calculations and compatibility helpers for training data."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from training_models import (
    TRAINING_SCHEMA_VERSION,
    SessionExercise,
    TrainingData,
    TrainingSession,
    TrainingSet,
    normalize_recording_mode,
    normalize_group_type,
)


def normalize_session_payload(session: Any) -> tuple[dict[str, Any], bool]:
    """Normalize a persisted session while preserving controller-owned runtime fields."""
    if not isinstance(session, Mapping):
        return {}, False
    result = copy.deepcopy(dict(session))
    changed = False
    raw_exercises = result.get("exercises", [])
    exercises = raw_exercises if isinstance(raw_exercises, list) else []
    if exercises is not raw_exercises:
        result["exercises"] = exercises
        changed = True
    valid_ids: list[str] = []
    for index, exercise in enumerate(exercises, 1):
        if not isinstance(exercise, dict):
            continue
        exercise_id = str(exercise.get("id") or _stable_id("session_exercise", result.get("id"), index, exercise.get("name")))
        if exercise.get("id") != exercise_id:
            exercise["id"] = exercise_id
            changed = True
        valid_ids.append(exercise_id)
        mode = normalize_recording_mode(exercise.get("recording_mode"))
        if exercise.get("recording_mode") != mode:
            exercise["recording_mode"] = mode
            changed = True
        if mode != "strength" and exercise.get("sets"):
            exercise["sets"] = []
            changed = True
        if mode != "strength":
            duration = int(max(0, _number_or_none(exercise.get("duration_seconds")) or 0))
            if exercise.get("duration_seconds") != duration:
                exercise["duration_seconds"] = duration
                changed = True
            distance = _number_or_none(exercise.get("distance_km"))
            distance = max(0.0, distance) if distance is not None else None
            if exercise.get("distance_km") != distance:
                exercise["distance_km"] = distance
                changed = True
            completed = bool(exercise.get("completed", False))
            if exercise.get("completed") is not completed:
                exercise["completed"] = completed
                changed = True
            raw_metrics = exercise.get("cardio_metrics", {})
            metrics = {
                str(key): max(0.0, value)
                for key, raw_value in raw_metrics.items()
                if str(key) and (value := _number_or_none(raw_value)) is not None
            } if isinstance(raw_metrics, Mapping) else {}
            if raw_metrics != metrics:
                exercise["cardio_metrics"] = metrics
                changed = True

    valid_set = set(valid_ids)
    groups: list[dict[str, Any]] = []
    claimed: set[str] = set()
    raw_groups = result.get("exercise_groups", result.get("groups", []))
    for index, raw_group in enumerate(raw_groups if isinstance(raw_groups, list) else [], 1):
        if not isinstance(raw_group, Mapping):
            changed = True
            continue
        group_type = normalize_group_type(raw_group.get("group_type", raw_group.get("type")))
        member_ids = [
            str(item) for item in raw_group.get("exercise_ids", [])
            if str(item) in valid_set and str(item) not in claimed
        ] if isinstance(raw_group.get("exercise_ids"), list) else []
        member_ids = list(dict.fromkeys(member_ids))
        if not group_type or len(member_ids) < 2:
            changed = True
            continue
        group_id = str(raw_group.get("id") or _stable_id("exercise_group", result.get("id"), index, *member_ids))
        groups.append({"id": group_id, "group_type": group_type, "order": len(groups) + 1, "exercise_ids": member_ids})
        claimed.update(member_ids)
    if result.get("exercise_groups") != groups:
        result["exercise_groups"] = groups
        changed = True
    by_id = {str(item.get("id") or ""): item for item in exercises if isinstance(item, dict)}
    membership = {
        exercise_id: (group["id"], order)
        for group in groups
        for order, exercise_id in enumerate(group["exercise_ids"], 1)
    }
    for exercise_id, exercise in by_id.items():
        group_id, group_order = membership.get(exercise_id, ("", None))
        if exercise.get("group_id", "") != group_id or exercise.get("group_order") != group_order:
            exercise["group_id"] = group_id
            exercise["group_order"] = group_order
            changed = True
    return result, changed


def raw_training_sessions(training: Any) -> list[dict[str, Any]]:
    """Return current and archived sessions once each, preserving raw UI fields."""
    if not isinstance(training, Mapping):
        return []
    candidates: list[Any] = []
    archived = training.get("sessions", [])
    if isinstance(archived, list):
        candidates.extend(archived)
    current = training.get("session")
    if isinstance(current, Mapping):
        candidates.append(current)

    result: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        session = dict(item)
        identity = str(session.get("id") or "")
        dedupe_key = identity or repr(session)
        if dedupe_key in positions:
            result[positions[dedupe_key]] = session
            continue
        positions[dedupe_key] = len(result)
        result.append(session)
    return result


def is_rapid_repeat(last_action_at: Any, current_action_at: Any, cooldown_seconds: float = 0.8) -> bool:
    """Return whether a second high-impact action should be ignored."""
    try:
        return float(current_action_at) - float(last_action_at) < max(0.0, float(cooldown_seconds))
    except (TypeError, ValueError):
        return False


def append_session_once(sessions: Any, session: Any) -> list[dict[str, Any]]:
    """Append a snapshot without replacing an earlier workout from the same day."""
    result = [copy.deepcopy(dict(item)) for item in sessions if isinstance(item, Mapping)] if isinstance(sessions, list) else []
    if not isinstance(session, Mapping):
        return result
    session_id = str(session.get("id") or "")
    for index, item in enumerate(result):
        if session_id and str(item.get("id") or "") == session_id:
            result[index] = copy.deepcopy(dict(session))
            return result
    result.append(copy.deepcopy(dict(session)))
    return result


def find_active_daily_session(records: Any) -> tuple[str | None, dict[str, Any] | None]:
    """Find an active workout even when it started on an earlier calendar day."""
    if not isinstance(records, Mapping):
        return None, None
    for record_date in sorted((str(key) for key in records.keys()), reverse=True):
        record = records.get(record_date)
        training = record.get("training", {}) if isinstance(record, Mapping) else {}
        for session in reversed(raw_training_sessions(training)):
            if session.get("status") == "active":
                return record_date, session
    return None, None


def set_volume(training_set: TrainingSet) -> float:
    if training_set.weight_kg is None or training_set.reps is None:
        return 0.0
    return round(max(0.0, training_set.weight_kg) * max(0, training_set.reps), 2)


def exercise_volume(exercise: SessionExercise, *, completed_only: bool = True, include_warmup: bool = True) -> float:
    return round(sum(
        set_volume(item)
        for item in exercise.sets
        if (not completed_only or item.completed) and (include_warmup or not item.warmup)
    ), 2)


def session_volume(session: TrainingSession, *, completed_only: bool = True, include_warmup: bool = True) -> float:
    return round(sum(
        exercise_volume(item, completed_only=completed_only, include_warmup=include_warmup)
        for item in session.exercises
    ), 2)


def planned_set_count(session: TrainingSession, *, include_warmup: bool = True) -> int:
    return sum(1 for exercise in session.exercises for item in exercise.sets if include_warmup or not item.warmup)


def completed_set_count(session: TrainingSession, *, include_warmup: bool = True) -> int:
    return sum(
        1 for exercise in session.exercises for item in exercise.sets
        if item.completed and (include_warmup or not item.warmup)
    )


def planned_work_count(session: TrainingSession, *, include_warmup: bool = True) -> int:
    """Count executable work without representing timed/cardio work as sets."""
    return planned_set_count(session, include_warmup=include_warmup) + sum(
        1 for exercise in session.exercises if exercise.recording_mode != "strength"
    )


def completed_work_count(session: TrainingSession, *, include_warmup: bool = True) -> int:
    return completed_set_count(session, include_warmup=include_warmup) + sum(
        1
        for exercise in session.exercises
        if exercise.recording_mode != "strength" and exercise.completed
    )


def session_work_progress(session: TrainingSession, *, include_warmup: bool = True) -> float:
    planned = planned_work_count(session, include_warmup=include_warmup)
    if planned == 0:
        return 0.0
    return round(completed_work_count(session, include_warmup=include_warmup) / planned, 4)


def rest_required_after_work(recording_mode: Any, *, grouped_round_complete: bool = False) -> bool:
    """Cardio/timed work rests only when it closes an explicit grouped round."""
    return bool(grouped_round_complete) or normalize_recording_mode(recording_mode) == "strength"


def session_progress(session: TrainingSession, *, include_warmup: bool = True) -> float:
    planned = planned_set_count(session, include_warmup=include_warmup)
    if planned == 0:
        return 0.0
    return round(completed_set_count(session, include_warmup=include_warmup) / planned, 4)


def session_completion_state(session: TrainingSession | Mapping[str, Any]) -> dict[str, Any]:
    """Return explicit end-state data for finish buttons and anti-repeat guards."""
    model = session if isinstance(session, TrainingSession) else TrainingSession.from_dict(session)
    planned_sets = planned_set_count(model)
    completed_sets = completed_set_count(model)
    planned = planned_work_count(model)
    completed = completed_work_count(model)
    remaining = max(0, planned - completed)
    remaining_sets = max(0, planned_sets - completed_sets)
    has_any_set = planned > 0
    all_sets_completed = has_any_set and remaining == 0
    has_completed_work = completed > 0
    return {
        "planned_sets": planned_sets,
        "completed_sets": completed_sets,
        "planned_work": planned,
        "completed_work": completed,
        "remaining_sets": remaining_sets,
        "remaining_work": remaining,
        "has_any_set": has_any_set,
        "has_completed_work": has_completed_work,
        "all_sets_completed": all_sets_completed,
        "finish_kind": "complete" if all_sets_completed else "incomplete",
        "needs_incomplete_confirmation": not all_sets_completed,
    }


def make_body_measurement(
    *, weight_kg: Any = None, bodyfat_percent: Any = None, measured_at: str
) -> dict[str, Any]:
    """Build a measurement payload where weight and body-fat can be measured separately."""
    result: dict[str, Any] = {"measured_at": str(measured_at).strip()}
    weight = _number_or_none(weight_kg)
    bodyfat = _number_or_none(bodyfat_percent)
    if weight is not None:
        result["weight_kg"] = weight
        result["weight_measured"] = True
    if bodyfat is not None:
        result["bodyfat_percent"] = bodyfat
        result["bodyfat_measured"] = True
    return result


def normalize_body_measurement(record: Any, record_date: str = "") -> dict[str, Any]:
    """Separate explicit weight/body-fat measurements from carried profile values."""
    source = record if isinstance(record, Mapping) else {}
    profile = source.get("profile") if isinstance(source.get("profile"), Mapping) else {}
    measurement = profile.get("measurement") if isinstance(profile.get("measurement"), Mapping) else {}
    measured_at = str(measurement.get("measured_at") or profile.get("measured_at") or "").strip()

    measured_weight = _number_or_none(measurement.get("weight_kg"))
    measured_bodyfat = _number_or_none(measurement.get("bodyfat_percent"))
    if measured_at and not measurement:
        measured_weight = _number_or_none(profile.get("weight_kg"))
        measured_bodyfat = _number_or_none(profile.get("bodyfat_percent"))

    weight_marked = bool(measurement.get("weight_measured", measured_weight is not None and bool(measured_at)))
    bodyfat_marked = bool(measurement.get("bodyfat_measured", measured_bodyfat is not None and bool(measured_at)))
    is_weight_measured = measured_weight is not None and weight_marked
    is_bodyfat_measured = measured_bodyfat is not None and bodyfat_marked
    return {
        "date": record_date,
        "measured_at": measured_at or None,
        "weight_kg": measured_weight if is_weight_measured else None,
        "bodyfat_percent": measured_bodyfat if is_bodyfat_measured else None,
        "carried_weight_kg": None if is_weight_measured else _number_or_none(profile.get("weight_kg")),
        "carried_bodyfat_percent": None if is_bodyfat_measured else _number_or_none(profile.get("bodyfat_percent")),
        "is_weight_measured": is_weight_measured,
        "is_bodyfat_measured": is_bodyfat_measured,
        "is_measured": is_weight_measured or is_bodyfat_measured,
    }


_CARB_LINK_BODY_PARTS = {
    "胸", "胸部", "chest",
    "肩", "肩部", "shoulder", "shoulders",
    "背", "背部", "back",
    "腿", "腿部", "leg", "legs",
    "臀", "臀部", "glute", "glutes",
}
_HIGH_INTENSITY_TEXT = {"高强度", "大重量", "力竭", "high", "hard", "heavy", "intense"}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _is_carb_link_part(value: Any) -> bool:
    text = _normalized_text(value)
    return any(alias.casefold() in text for alias in _CARB_LINK_BODY_PARTS)


def _is_high_intensity(value: Any) -> bool:
    text = _normalized_text(value)
    return any(marker.casefold() in text for marker in _HIGH_INTENSITY_TEXT)


def assess_training_carb_linkage(
    training: Any,
    *,
    min_formal_sets: int = 6,
    min_volume_kg: float = 2000.0,
) -> dict[str, Any]:
    """Assess substantial training that should participate in carb-day linkage.

    This is an independent compatibility helper because analytics_service keeps
    the older low-carb leg/back-specific contract.
    """
    target_sets = 0
    target_volume = 0.0
    target_actions: list[str] = []
    high_intensity_targets: list[str] = []
    has_linked_part = False
    value = training.get("training") if isinstance(training, Mapping) and "training" in training else training

    for raw in raw_training_sessions(value):
        session = TrainingSession.from_dict(raw)
        for exercise in session.exercises:
            if not _is_carb_link_part(exercise.body_part):
                continue
            has_linked_part = True
            if exercise.name and exercise.name not in target_actions:
                target_actions.append(exercise.name)
            completed = [item for item in exercise.sets if item.completed and not item.warmup and (item.reps or 0) > 0]
            target_sets += len(completed)
            target_volume += sum(max(0.0, item.weight_kg or 0.0) * max(0, item.reps or 0) for item in completed)
            if _is_high_intensity(exercise.legacy_intensity) and exercise.name not in high_intensity_targets:
                high_intensity_targets.append(exercise.name)

    if isinstance(value, Mapping):
        for target in value.get("targets", []) if isinstance(value.get("targets"), list) else []:
            if not isinstance(target, Mapping) or not _is_carb_link_part(target.get("target")):
                continue
            has_linked_part = True
            name = str(target.get("detail") or target.get("target") or "").strip()
            if name and name not in target_actions:
                target_actions.append(name)
            if _is_high_intensity(target.get("intensity")) and name and name not in high_intensity_targets:
                high_intensity_targets.append(name)

    set_trigger = target_sets >= max(1, int(min_formal_sets))
    volume_trigger = target_volume >= max(0.0, float(min_volume_kg))
    intensity_trigger = bool(high_intensity_targets)
    should_link = has_linked_part and (set_trigger or volume_trigger or intensity_trigger)
    return {
        "should_link": should_link,
        "has_linked_body_part": has_linked_part,
        "formal_sets": target_sets,
        "volume_kg": round(target_volume, 2),
        "exercises": target_actions,
        "high_intensity_exercises": high_intensity_targets,
        "reasons": [
            *([f"正式组达到{target_sets}组"] if set_trigger else []),
            *([f"训练容量达到{round(target_volume, 1):g}kg"] if volume_trigger else []),
            *(["高强度训练参与碳日联动"] if intensity_trigger else []),
        ],
    }


def recommend_carb_day(training_or_parts: Any) -> str | None:
    """Map recorded training parts to the user's fixed carb-cycle rule.

    Composite sessions use high > medium > low priority. Missing training stays
    ``None`` so it is never confused with an explicitly recorded rest day.
    """
    value = training_or_parts
    if isinstance(value, Mapping) and "training" in value:
        value = value.get("training")

    parts: list[str] = []
    explicit_rest = False
    if isinstance(value, Mapping):
        for raw in raw_training_sessions(value):
            session = TrainingSession.from_dict(raw)
            parts.extend(str(exercise.body_part or "").strip() for exercise in session.exercises)
        targets = value.get("targets", [])
        if isinstance(targets, list):
            for target in targets:
                if not isinstance(target, Mapping):
                    continue
                part = str(target.get("target") or "").strip()
                parts.append(part)
                explicit_rest = explicit_rest or part.casefold() in {"休息", "rest"}
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        parts.extend(str(part or "").strip() for part in value)

    normalized = [part.casefold() for part in parts if part]
    if any(any(marker in part for marker in ("背", "back", "腿", "leg", "臀", "glute")) for part in normalized):
        return "高碳日"
    if any(any(marker in part for marker in ("胸", "chest", "肩", "shoulder")) for part in normalized):
        return "中碳日"
    low_markers = ("二头", "三头", "手臂", "臂", "arm", "腹", "核心", "abs", "core", "有氧", "cardio", "跑", "骑", "游", "爬坡", "徒步", "球")
    if explicit_rest or any(any(marker in part for marker in low_markers) for part in normalized):
        return "低碳日"
    return None


def estimated_one_rep_max(weight_kg: float | int | None, reps: int | None) -> float | None:
    """Estimate 1RM with the Epley formula."""
    if weight_kg is None or reps is None or weight_kg <= 0 or reps <= 0:
        return None
    if reps == 1:
        return round(float(weight_kg), 2)
    return round(float(weight_kg) * (1 + reps / 30), 2)


def _matches(exercise: SessionExercise, exercise_id: str | None, exercise_name: str | None) -> bool:
    if exercise_id and exercise.exercise_id == exercise_id:
        return True
    return bool(exercise_name and exercise.name.strip().casefold() == exercise_name.strip().casefold())


def _completed_sets(exercise: SessionExercise) -> list[TrainingSet]:
    return [item for item in exercise.sets if item.completed and item.weight_kg is not None and item.reps is not None]


def last_performance(
    sessions: Iterable[TrainingSession],
    *,
    exercise_id: str | None = None,
    exercise_name: str | None = None,
    before_date: str | None = None,
) -> dict[str, Any] | None:
    candidates: list[tuple[str, str, TrainingSession, SessionExercise]] = []
    for session in sessions:
        if before_date and session.date >= before_date:
            continue
        for exercise in session.exercises:
            if _matches(exercise, exercise_id, exercise_name) and _completed_sets(exercise):
                candidates.append((session.date, session.ended_at or session.started_at, session, exercise))
    if not candidates:
        return None
    _, _, session, exercise = sorted(candidates, key=lambda item: (item[0], item[1]))[-1]
    sets = _completed_sets(exercise)
    return {
        "session_id": session.id,
        "date": session.date,
        "exercise_id": exercise.exercise_id,
        "exercise_name": exercise.name,
        "sets": [item.to_dict() for item in sets],
        "completed_sets": len(sets),
        "volume": exercise_volume(exercise),
    }


def personal_bests(
    sessions: Iterable[TrainingSession],
    *,
    exercise_id: str | None = None,
    exercise_name: str | None = None,
) -> dict[str, Any] | None:
    entries: list[tuple[TrainingSession, SessionExercise, TrainingSet]] = []
    matched_exercises: list[tuple[TrainingSession, SessionExercise]] = []
    for session in sessions:
        for exercise in session.exercises:
            if not _matches(exercise, exercise_id, exercise_name):
                continue
            completed = _completed_sets(exercise)
            if completed:
                matched_exercises.append((session, exercise))
                entries.extend((session, exercise, item) for item in completed)
    if not entries:
        return None

    def set_result(entry: tuple[TrainingSession, SessionExercise, TrainingSet]) -> dict[str, Any]:
        session, exercise, item = entry
        return {
            "session_id": session.id,
            "date": session.date,
            "exercise_id": exercise.exercise_id,
            "exercise_name": exercise.name,
            "set": item.to_dict(),
        }

    heaviest = max(entries, key=lambda entry: (entry[2].weight_kg or 0, entry[2].reps or 0, entry[0].date))
    most_reps = max(entries, key=lambda entry: (entry[2].reps or 0, entry[2].weight_kg or 0, entry[0].date))
    best_e1rm = max(entries, key=lambda entry: (estimated_one_rep_max(entry[2].weight_kg, entry[2].reps) or 0, entry[0].date))
    best_volume_session, best_volume_exercise = max(
        matched_exercises,
        key=lambda entry: (exercise_volume(entry[1]), entry[0].date),
    )
    return {
        "heaviest_set": set_result(heaviest),
        "most_reps_set": set_result(most_reps),
        "best_estimated_1rm": {
            **set_result(best_e1rm),
            "estimated_1rm_kg": estimated_one_rep_max(best_e1rm[2].weight_kg, best_e1rm[2].reps),
        },
        "best_session_volume": {
            "session_id": best_volume_session.id,
            "date": best_volume_session.date,
            "exercise_id": best_volume_exercise.exercise_id,
            "exercise_name": best_volume_exercise.name,
            "volume": exercise_volume(best_volume_exercise),
        },
    }


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}_{uuid5(NAMESPACE_URL, raw).hex}"


def migrate_legacy_training(training: Any, record_date: str) -> TrainingSession | None:
    """Convert the current app's dict/list training record without inventing set data."""
    if isinstance(training, Mapping) and isinstance(training.get("exercises"), list):
        source = copy.deepcopy(dict(training))
        source.setdefault("date", record_date)
        for exercise in source.get("exercises", []):
            if isinstance(exercise, dict):
                exercise["recording_mode"] = normalize_recording_mode(exercise.get("recording_mode"))
        session = TrainingSession.from_dict(source)
        has_exercises = any(
            exercise.name.strip() or exercise.body_part.strip() or exercise.sets
            for exercise in session.exercises
        )
        has_duration = (session.total_duration_min or 0) > 0
        has_note = bool(session.summary_note.strip())
        if not has_exercises and not has_duration and not has_note:
            return None
        return session

    if isinstance(training, list):
        targets = training
        source: Mapping[str, Any] = {}
    elif isinstance(training, Mapping):
        raw_targets = training.get("targets", [])
        targets = raw_targets if isinstance(raw_targets, list) else []
        source = training
    else:
        return None

    exercises: list[SessionExercise] = []
    for index, target in enumerate(targets, 1):
        if not isinstance(target, Mapping):
            continue
        body_part = str(target.get("target", "")).strip()
        detail = str(target.get("detail", "")).strip()
        note = str(target.get("note", "")).strip()
        if not body_part and not detail and not note:
            continue
        name = detail or body_part or f"旧训练 {index}"
        exercises.append(SessionExercise(
            id=_stable_id("session_exercise", record_date, index, body_part, detail),
            exercise_id="",
            name=name,
            body_part=body_part,
            order=index,
            sets=[],
            note=note,
            legacy_detail=detail,
            legacy_intensity=str(target.get("intensity", "中等")),
        ))

    duration = _number_or_none(source.get("total_duration_min"))
    calories = _number_or_none(source.get("total_calories_kcal"))
    summary_note = str(source.get("summary_note", "")).strip()
    fatigue_status = str(source.get("fatigue_status", ""))
    has_duration = duration is not None and duration > 0
    has_calories = calories is not None and calories > 0
    if not exercises and not has_duration and not has_calories and not summary_note:
        return None
    return TrainingSession(
        id=_stable_id("session", record_date, "legacy"),
        date=record_date,
        status="completed",
        total_duration_min=duration,
        exercises=exercises,
        summary_note=summary_note,
        fatigue_status=fatigue_status,
        legacy_calories_kcal=calories,
    )


def _number_or_none(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def migrate_daily_records(records: Mapping[str, Any]) -> list[TrainingSession]:
    sessions: list[TrainingSession] = []
    for record_date, record in sorted(records.items(), key=lambda item: str(item[0])):
        if not isinstance(record, Mapping):
            continue
        session = migrate_legacy_training(record.get("training"), str(record.get("date") or record_date))
        if session is not None:
            sessions.append(session)
    return sessions


def normalize_training_data(payload: Any) -> TrainingData:
    """Read the new store, a session list, or the app's date-keyed legacy records."""
    if isinstance(payload, TrainingData):
        return TrainingData.from_dict(payload.to_dict())
    if isinstance(payload, Mapping) and any(key in payload for key in ("schema_version", "sessions", "templates", "exercises")):
        return TrainingData.from_dict(payload)
    if isinstance(payload, Mapping):
        return TrainingData(schema_version=TRAINING_SCHEMA_VERSION, sessions=migrate_daily_records(payload))
    if isinstance(payload, list):
        sessions = [TrainingSession.from_dict(item) for item in payload if isinstance(item, Mapping)]
        return TrainingData(schema_version=TRAINING_SCHEMA_VERSION, sessions=sessions)
    return TrainingData()


def session_summary_title(session: Mapping[str, Any]) -> str:
    """Return the completion heading without conflating partial sessions."""
    state = session_completion_state(session)
    incomplete = bool(session.get("incomplete")) and not state["all_sets_completed"]
    return "未完整训练" if incomplete else "训练完成"
