"""Translate app state into the normalized dynamic-carb engine contract."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from dynamic_carb_engine import calculate_daily_target, project_daily_target_for_ui, validate_exercise_parameters
from training_models import SessionExercise, TrainingSession
from training_service import raw_training_sessions


APP_SNAPSHOT_VERSION = 1
FORMAL_DAY_TYPES = {"低碳日", "中碳日", "高碳日"}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_profile(state: Mapping[str, Any], effective_date: str | None = None) -> dict[str, Any]:
    profile = {
        "weight_kg": _number(state.get("weight")),
        "height_cm": _number(state.get("height")),
        "age_years": _number(state.get("age")),
        "sex": state.get("sex"),
        "activity_habit": state.get("activity_habit"),
        "goal": state.get("macro_goal", "减脂"),
    }
    bodyfat = _number(state.get("bodyfat"))
    measurement = state.get("measurement") if isinstance(state.get("measurement"), Mapping) else {}
    measured_bodyfat = _number(measurement.get("bodyfat_percent"))
    measured_at = str(measurement.get("measured_at") or "")[:10]
    target = _iso_date(effective_date)
    observed = measured_bodyfat is not None
    if observed:
        bodyfat = measured_bodyfat
    if bodyfat is not None:
        profile["bodyfat_percent"] = bodyfat
        profile["bodyfat_status"] = "observed" if observed else "carried"
        measured_date = _iso_date(measured_at)
        profile["bodyfat_age_days"] = max(0, (target - measured_date).days) if target and measured_date else 91
    else:
        profile["bodyfat_status"] = "unknown"
    return profile


def normalize_training(training: Mapping[str, Any] | None) -> dict[str, Any]:
    source = training if isinstance(training, Mapping) else {}
    sessions = [TrainingSession.from_dict(item) for item in raw_training_sessions(source)]
    explicit_rest = any(
        str(item.get("target") or "").strip().casefold() in {"休息", "rest"}
        for item in source.get("targets", [])
        if isinstance(item, Mapping)
    )

    resistance_sets = 0
    muscle_sets: Counter[str] = Counter()
    cardio_duration = 0.0
    cardio_intensities: list[str] = []
    total_duration = 0.0
    valid_sessions = 0
    has_pending = False
    has_completed_session = False
    has_active_session = False

    for session in sessions:
        completed_session = session.status == "completed"
        active_session = session.status == "active"
        has_completed_session = has_completed_session or completed_session
        has_active_session = has_active_session or active_session
        session_has_work = False
        for exercise in session.exercises:
            raw_exercise = exercise.to_dict()
            if completed_session:
                raw_exercise["sets"] = [item.to_dict() for item in exercise.sets if item.completed]
                raw_exercise["completed"] = exercise.completed
                ready = validate_exercise_parameters(raw_exercise, require_confirmation=False)["ready"]
            else:
                ready = validate_exercise_parameters(raw_exercise)["ready"]
            if not ready:
                has_pending = True
                continue
            if exercise.recording_mode == "strength":
                selected_sets = [
                    item for item in exercise.sets
                    if not item.warmup and (not completed_session or item.completed)
                ]
                count = len(selected_sets)
                if count:
                    resistance_sets += count
                    muscle_sets[exercise.body_part or exercise.name or "未分类"] += count
                    session_has_work = True
            else:
                duration = max(0.0, float(exercise.duration_seconds or 0) / 60)
                if duration > 0 and (not completed_session or exercise.completed):
                    cardio_duration += duration
                    cardio_intensities.append(_cardio_intensity(exercise))
                    session_has_work = True
        if session_has_work:
            valid_sessions += 1
            if session.total_duration_min is not None:
                total_duration += max(0.0, session.total_duration_min)

    has_valid_work = resistance_sets > 0 or cardio_duration > 0
    if has_valid_work:
        if has_completed_session and not has_active_session:
            status = "completed"
        elif has_active_session:
            status = "active"
        else:
            status = "planned_confirmed"
    elif explicit_rest:
        status = "explicit_rest"
    elif has_completed_session:
        status = "outcome_unknown"
    elif sessions or has_pending:
        status = "planned_pending"
    else:
        status = "unknown"

    result: dict[str, Any] = {"status": status, "sessions": max(1, valid_sessions)}
    if resistance_sets:
        result["resistance"] = {
            "work_sets_total": resistance_sets,
            "peak_primary_muscle_sets": max(muscle_sets.values(), default=0),
            "duration_min": total_duration or None,
        }
    if cardio_duration:
        result["cardio"] = {
            "duration_min": cardio_duration,
            "intensity": _highest_intensity(cardio_intensities),
        }
    return result


def calculate_app_snapshot(
    state: Mapping[str, Any],
    *,
    effective_date: str | None = None,
    existing: Mapping[str, Any] | None = None,
    freeze_shown: bool = False,
    calculated_at: str | None = None,
) -> dict[str, Any]:
    selected_date = effective_date or str(state.get("date") or "") or None
    profile = normalize_profile(state, selected_date)
    training = normalize_training(state.get("training") if isinstance(state.get("training"), Mapping) else {})
    training_state = state.get("training") if isinstance(state.get("training"), Mapping) else {}
    manual_day = state.get("day_type") if training_state.get("carb_mode") == "manual" else None
    inputs = {"profile": profile, "training": training, "manual_day_type": manual_day, "effective_date": selected_date}
    revision = hashlib.sha256(
        json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    try:
        engine = calculate_daily_target(profile, training, effective_date=selected_date, manual_day_type=manual_day)
        projection = project_daily_target_for_ui(engine)
        error = None
    except ValueError as exc:
        engine = None
        projection = {
            "ui_contract_version": 1,
            "effective_date": selected_date,
            "status": "unavailable",
            "day_label": state.get("day_type") if state.get("day_type") in FORMAL_DAY_TYPES else "低碳日",
            "macro_targets": None,
        }
        error = str(exc)

    previous = existing if isinstance(existing, Mapping) else {}
    previous_shown = previous.get("shown_target_snapshot")
    shown = copy.deepcopy(previous_shown) if freeze_shown and isinstance(previous_shown, Mapping) else copy.deepcopy(projection)
    now = calculated_at or datetime.now().isoformat(timespec="seconds")
    return {
        "snapshot_version": APP_SNAPSHOT_VERSION,
        "input_revision": revision,
        "calculated_at": now,
        "effective_date": selected_date,
        "profile_facts": profile,
        "training_facts": training,
        "engine_snapshot": engine,
        "ui_projection": projection,
        "shown_target_snapshot": shown,
        "recomputed_actual_ledger": {
            "calculated_at": now,
            "input_revision": revision,
            "training_facts": copy.deepcopy(training),
            "recommended_day": engine.get("recommended_day") if isinstance(engine, Mapping) else None,
        },
        "error": error,
    }


def targets_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, float] | None:
    projection = snapshot.get("ui_projection") if isinstance(snapshot.get("ui_projection"), Mapping) else {}
    macros = projection.get("macro_targets") if isinstance(projection.get("macro_targets"), Mapping) else None
    if projection.get("status") == "unavailable" or not macros:
        return None
    return {
        "calorie_target": float(projection["energy_kcal"]),
        "carb": float(macros["carb"]["center_g"]),
        "carb_min": float(macros["carb"]["min_g"]),
        "carb_max": float(macros["carb"]["max_g"]),
        "protein": float(macros["protein"]["center_g"]),
        "protein_min": float(macros["protein"]["min_g"]),
        "protein_max": float(macros["protein"]["max_g"]),
        "fat": float(macros["fat"]["center_g"]),
        "fat_min": float(macros["fat"]["min_g"]),
        "fat_max": float(macros["fat"]["max_g"]),
    }


def _cardio_intensity(exercise: SessionExercise) -> str:
    text = str(exercise.legacy_intensity or "").strip().casefold()
    if any(item in text for item in ("高", "大", "high", "hard")):
        return "high"
    if any(item in text for item in ("低", "恢复", "轻", "low", "easy")):
        return "low"
    return "moderate"


def _highest_intensity(values: list[str]) -> str:
    order = {"low": 0, "moderate": 1, "high": 2}
    return max(values, key=lambda item: order.get(item, 1), default="moderate")


def _iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


__all__ = [
    "APP_SNAPSHOT_VERSION",
    "calculate_app_snapshot",
    "normalize_profile",
    "normalize_training",
    "targets_from_snapshot",
]
