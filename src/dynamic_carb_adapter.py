"""Translate app state into the normalized dynamic-carb engine contract."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, MutableMapping
from datetime import date, datetime
from typing import Any

from dynamic_carb_engine import (
    calculate_daily_target,
    classify_training,
    create_phase_baseline,
    project_daily_target_for_ui,
    validate_exercise_parameters,
)
from training_models import SessionExercise, TrainingSession
from training_service import raw_training_sessions


APP_SNAPSHOT_VERSION = 3
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
    measured_at = str(
        (
            measurement.get("measured_at")
            if measured_bodyfat is not None
            else state.get("bodyfat_measured_at")
        )
        or ""
    )[:10]
    target = _iso_date(effective_date)
    measured_date = _iso_date(measured_at)
    future_measurement = bool(target and measured_date and measured_date > target)
    observed = measured_bodyfat is not None and not future_measurement
    if observed:
        bodyfat = measured_bodyfat
    if bodyfat is not None and not future_measurement:
        profile["bodyfat_percent"] = bodyfat
        profile["bodyfat_status"] = "observed" if observed else "carried"
        profile["bodyfat_age_days"] = (target - measured_date).days if target and measured_date else 91
        if measured_date is not None:
            profile["bodyfat_records"] = [{
                "record_id": f"profile-bodyfat-{measured_date.isoformat()}",
                "date": measured_date.isoformat(),
                "bodyfat_percent": bodyfat,
                "source": "daily_measurement" if observed else "profile_carried",
            }]
    elif future_measurement:
        profile["bodyfat_status"] = "future_unavailable"
    else:
        profile["bodyfat_status"] = "unknown"
    if target is not None:
        profile["as_of_date"] = target.isoformat()
    phase = _phase_for_date(
        state.get("carb_phase") if isinstance(state.get("carb_phase"), Mapping) else None,
        target,
    )
    if phase and _phase_matches(phase, profile, target):
        _apply_phase(profile, phase)
    return profile


def _goal_key(value: Any) -> str:
    return {
        "减脂": "cut_standard", "保持": "recomp", "增肌": "gain_controlled",
        "cut_standard": "cut_standard", "recomp": "recomp", "gain_controlled": "gain_controlled",
    }.get(str(value or ""), "cut_standard")


def _phase_matches(phase: Mapping[str, Any], profile: Mapping[str, Any], target: date | None) -> bool:
    if _goal_key(phase.get("goal")) != _goal_key(profile.get("goal")):
        return False
    effective = _iso_date(phase.get("effective_from", phase.get("started_at")))
    return effective is not None and (target is None or effective <= target)


def _phase_for_date(phase: Mapping[str, Any] | None, target: date | None) -> Mapping[str, Any] | None:
    if not phase:
        return None
    pending = phase.get("pending_refresh")
    if isinstance(pending, Mapping):
        effective = _iso_date(pending.get("effective_from"))
        if effective is not None and (target is None or effective <= target):
            return pending
    return phase


def _apply_phase(profile: dict[str, Any], phase: Mapping[str, Any]) -> None:
    profile.update({
        "phase_id": phase.get("phase_id"),
        "phase_baseline_weight_kg": phase.get("baseline_weight_kg"),
        "phase_maintenance_kcal": phase.get("maintenance_kcal"),
        "phase_protein_g": phase.get("protein_g"),
        "phase_fat_anchor_g": phase.get("fat_anchor_g"),
        "phase_ffm_kg": phase.get("ffm_kg"),
    })


def normalize_training(training: Mapping[str, Any] | None, *, completed_only: bool = False) -> dict[str, Any]:
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
    cardio_effective_minutes = 0.0
    cardio_intensities: list[str] = []
    resistance_duration = 0.0
    valid_sessions = 0
    medium_or_higher_sessions = 0
    has_pending = False
    has_completed_session = False
    has_active_session = False
    has_planned_work = False
    considered_sessions = 0
    legacy_positive_load_inference_count = 0
    legacy_unknown_load_counted_sets = 0
    legacy_unknown_load_counted_exercises = 0

    for session in sessions:
        completed_session = session.status == "completed"
        active_session = session.status == "active"
        if completed_only and not completed_session:
            continue
        considered_sessions += 1
        has_completed_session = has_completed_session or completed_session
        has_active_session = has_active_session or active_session
        session_has_work = False
        session_resistance_sets = 0
        session_muscle_sets: Counter[str] = Counter()
        session_cardio_duration = 0.0
        session_cardio_effective_minutes = 0.0
        session_cardio_intensities: list[str] = []
        for exercise in session.exercises:
            raw_exercise = exercise.to_dict()
            if completed_session:
                raw_exercise["sets"] = [item.to_dict() for item in exercise.sets if item.completed]
                raw_exercise["completed"] = exercise.completed
                legacy_unknown_load_ready = None
                if raw_exercise.get("recording_mode") == "strength" and raw_exercise.get("load_kind") == "unknown":
                    completed_work_sets = [item for item in exercise.sets if item.completed and not item.warmup]
                    if any(float(item.weight_kg or 0) > 0 for item in completed_work_sets):
                        raw_exercise["load_kind"] = "external"
                        legacy_positive_load_inference_count += 1
                    elif completed_work_sets:
                        # Completed resistance work is still a training fact even
                        # when an old record cannot say whether zero meant
                        # bodyweight or an omitted external-load value.  The
                        # demand classifier uses valid work sets, not kilograms.
                        legacy_unknown_load_ready = all(int(item.reps or 0) > 0 for item in completed_work_sets)
                        if legacy_unknown_load_ready:
                            legacy_unknown_load_counted_sets += len(completed_work_sets)
                            legacy_unknown_load_counted_exercises += 1
                ready = (
                    legacy_unknown_load_ready
                    if legacy_unknown_load_ready is not None
                    else validate_exercise_parameters(raw_exercise, require_confirmation=False)["ready"]
                )
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
                    session_resistance_sets += count
                    session_muscle_sets[exercise.body_part or exercise.name or "未分类"] += count
                    session_has_work = True
            elif exercise.recording_mode == "cardio":
                duration = max(0.0, float(exercise.duration_seconds or 0) / 60)
                if duration > 0 and (not completed_session or exercise.completed):
                    cardio_duration += duration
                    intensity = _cardio_intensity(exercise)
                    cardio_intensities.append(intensity)
                    cardio_effective_minutes += duration * _cardio_effective_factor(intensity)
                    session_cardio_duration += duration
                    session_cardio_effective_minutes += duration * _cardio_effective_factor(intensity)
                    session_cardio_intensities.append(intensity)
                    session_has_work = True
        if session_has_work:
            valid_sessions += 1
            has_planned_work = has_planned_work or (not completed_session and not active_session)
            session_facts: dict[str, Any] = {"status": "completed" if completed_session else "planned_confirmed"}
            if session_resistance_sets:
                session_facts["resistance"] = {
                    "work_sets_total": session_resistance_sets,
                    "peak_body_part_sets": max(session_muscle_sets.values(), default=0),
                    "duration_min": session.total_duration_min if not session_cardio_duration else None,
                }
            if session_cardio_duration:
                session_facts["cardio"] = {
                    "duration_min": session_cardio_duration,
                    "effective_minutes": session_cardio_effective_minutes,
                    "intensity": _highest_intensity(session_cardio_intensities),
                }
            session_demand = classify_training(session_facts).get("demand_key")
            if session_demand in {
                "resistance_medium", "resistance_high", "cardio_moderate", "cardio_high",
                "endurance_long", "endurance_extreme", "mixed_high",
            }:
                medium_or_higher_sessions += 1
            if session.total_duration_min is not None:
                if session_resistance_sets and not session_cardio_duration:
                    resistance_duration += max(0.0, session.total_duration_min)

    has_valid_work = resistance_sets > 0 or cardio_duration > 0
    if has_valid_work:
        if has_active_session:
            status = "active"
        elif has_planned_work:
            status = "planned_confirmed"
        elif has_completed_session:
            status = "completed"
        else:
            status = "planned_confirmed"
    elif has_completed_session:
        status = "outcome_unknown"
    elif considered_sessions or has_pending:
        status = "planned_pending"
    elif explicit_rest:
        status = "explicit_rest"
    else:
        status = "unknown"

    result: dict[str, Any] = {"status": status, "sessions": max(1, valid_sessions)}
    migration_flags: list[str] = []
    if legacy_positive_load_inference_count:
        migration_flags.append("legacy_positive_weight_unknown_load_inferred_external")
        result["legacy_load_inference_count"] = legacy_positive_load_inference_count
    if legacy_unknown_load_counted_sets:
        migration_flags.append("legacy_completed_unknown_load_counted_without_load_semantics")
        result["legacy_unknown_load_counted_sets"] = legacy_unknown_load_counted_sets
        result["legacy_unknown_load_counted_exercises"] = legacy_unknown_load_counted_exercises
    if migration_flags:
        result["migration_flags"] = migration_flags
    if medium_or_higher_sessions:
        result["medium_or_higher_sessions"] = medium_or_higher_sessions
    if resistance_sets:
        result["resistance"] = {
            "work_sets_total": resistance_sets,
            "peak_body_part_sets": max(muscle_sets.values(), default=0),
            "duration_min": resistance_duration or None,
        }
    if cardio_duration:
        result["cardio"] = {
            "duration_min": cardio_duration,
            "effective_minutes": cardio_effective_minutes,
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
    target_date = _iso_date(selected_date)
    stored_phase = state.get("carb_phase") if isinstance(state.get("carb_phase"), Mapping) else None
    active_phase = _phase_for_date(stored_phase, target_date)
    if (
        isinstance(state, MutableMapping)
        and active_phase is not None
        and active_phase is not stored_phase
        and target_date == date.today()
    ):
        state["carb_phase"] = copy.deepcopy(active_phase)
    profile = normalize_profile(state, selected_date)
    phase_created: dict[str, Any] | None = None
    if str(state.get("macro_mode") or "auto") != "custom" and not profile.get("phase_id"):
        phase_date = _iso_date(selected_date) or date.today()
        try:
            phase_created = create_phase_baseline(profile, phase_date)
        except ValueError:
            phase_created = None
        if phase_created is not None:
            _apply_phase(profile, phase_created)
            if isinstance(state, MutableMapping) and phase_date == date.today():
                state["carb_phase"] = copy.deepcopy(phase_created)
    raw_training = state.get("training") if isinstance(state.get("training"), Mapping) else {}
    training = normalize_training(raw_training)
    actual_training = normalize_training(raw_training, completed_only=True)
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

    now = calculated_at or datetime.now().isoformat(timespec="seconds")
    engine_reasons: list[str] = []
    if isinstance(engine, Mapping):
        applied_macros = engine.get("applied_macros")
        runtime = engine.get("runtime_distribution")
        if isinstance(applied_macros, Mapping):
            engine_reasons.extend(applied_macros.get("reason_codes", []))
        if isinstance(runtime, Mapping):
            engine_reasons.extend(runtime.get("reason_codes", []))
    engine_reasons = list(dict.fromkeys(str(item) for item in engine_reasons))
    if engine is None:
        engine_reasons = ["input_invalid"]
    shown_candidate = {
        "snapshot_version": APP_SNAPSHOT_VERSION,
        "input_revision": revision,
        "calculated_at": now,
        "effective_date": selected_date,
        "algorithm_version": engine.get("algorithm_version") if isinstance(engine, Mapping) else None,
        "parameter_set_version": engine.get("parameter_set_version") if isinstance(engine, Mapping) else None,
        "evidence_version": engine.get("evidence_version") if isinstance(engine, Mapping) else None,
        "model_document_sha256": engine.get("model_document_sha256") if isinstance(engine, Mapping) else None,
        "solver_context_sha256": engine.get("solver_context_sha256") if isinstance(engine, Mapping) else None,
        "mode": engine.get("mode") if isinstance(engine, Mapping) else None,
        "override_mode": engine.get("override_mode") if isinstance(engine, Mapping) else None,
        "requested_speed": engine.get("requested_speed") if isinstance(engine, Mapping) else None,
        "raw_budget_kcal_day": engine.get("raw_budget_kcal_day") if isinstance(engine, Mapping) else None,
        "guarded_budget_kcal_day": engine.get("guarded_budget_kcal_day") if isinstance(engine, Mapping) else None,
        "applied_budget_kcal_day": engine.get("applied_budget_kcal_day") if isinstance(engine, Mapping) else None,
        "target_speed_applied": engine.get("target_speed_applied") if isinstance(engine, Mapping) else None,
        "reason_codes": engine_reasons,
        "profile_facts": copy.deepcopy(profile),
        "training_facts": copy.deepcopy(training),
        "recommended_day": engine.get("recommended_day") if isinstance(engine, Mapping) else None,
        "applied_day": engine.get("applied_day") if isinstance(engine, Mapping) else None,
        "engine_snapshot": copy.deepcopy(engine),
        "projection": copy.deepcopy(projection),
        "error": error,
    }
    previous = existing if isinstance(existing, Mapping) else {}
    previous_shown = previous.get("shown_target_snapshot")
    if freeze_shown and isinstance(previous_shown, Mapping):
        if isinstance(previous_shown.get("projection"), Mapping):
            shown = copy.deepcopy(previous_shown)
        else:
            # Migrate the Build 90 projection-only snapshot without changing
            # the values the user originally saw.
            shown = {
                "snapshot_version": 1,
                "input_revision": previous.get("input_revision"),
                "calculated_at": previous.get("calculated_at"),
                "effective_date": previous.get("effective_date"),
                "algorithm_version": (
                    previous.get("engine_snapshot", {}).get("algorithm_version")
                    if isinstance(previous.get("engine_snapshot"), Mapping) else None
                ),
                "parameter_set_version": (
                    previous.get("engine_snapshot", {}).get("parameter_set_version")
                    if isinstance(previous.get("engine_snapshot"), Mapping) else None
                ),
                "evidence_version": (
                    previous.get("engine_snapshot", {}).get("evidence_version")
                    if isinstance(previous.get("engine_snapshot"), Mapping) else None
                ),
                "profile_facts": copy.deepcopy(previous.get("profile_facts")),
                "training_facts": copy.deepcopy(previous.get("training_facts")),
                "recommended_day": (
                    previous.get("engine_snapshot", {}).get("recommended_day")
                    if isinstance(previous.get("engine_snapshot"), Mapping) else None
                ),
                "applied_day": previous_shown.get("day_label"),
                "engine_snapshot": copy.deepcopy(previous.get("engine_snapshot")),
                "projection": copy.deepcopy(previous_shown),
                "error": previous.get("error"),
            }
    else:
        shown = shown_candidate
    actual_inputs = {"profile": profile, "training": actual_training, "effective_date": selected_date}
    actual_revision = hashlib.sha256(
        json.dumps(actual_inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    actual_recommended_day = None
    if isinstance(engine, Mapping):
        actual_recommended_day = calculate_daily_target(
            profile, actual_training, effective_date=selected_date
        ).get("recommended_day")
    return {
        "snapshot_version": APP_SNAPSHOT_VERSION,
        "input_revision": revision,
        "calculated_at": now,
        "effective_date": selected_date,
        "profile_facts": profile,
        "phase_created": copy.deepcopy(phase_created),
        "training_facts": training,
        "engine_snapshot": engine,
        "ui_projection": projection,
        "shown_target_snapshot": shown,
        "model_document_sha256": engine.get("model_document_sha256") if isinstance(engine, Mapping) else None,
        "degradation_reason_codes": (
            engine_reasons if engine is None or projection.get("status") == "unavailable" else []
        ),
        "recomputed_actual_ledger": {
            "calculated_at": now,
            "input_revision": actual_revision,
            "training_facts": copy.deepcopy(actual_training),
            "recommended_day": actual_recommended_day,
        },
        "error": error,
    }


def projection_from_snapshot(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    shown = snapshot.get("shown_target_snapshot")
    if isinstance(shown, Mapping) and isinstance(shown.get("projection"), Mapping):
        return shown["projection"]
    if isinstance(shown, Mapping) and "macro_targets" in shown:
        return shown
    return snapshot.get("ui_projection") if isinstance(snapshot.get("ui_projection"), Mapping) else {}


def engine_from_snapshot(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the engine facts that belong to the same immutable shown target."""
    shown = snapshot.get("shown_target_snapshot")
    if isinstance(shown, Mapping) and isinstance(shown.get("engine_snapshot"), Mapping):
        return shown["engine_snapshot"]
    return snapshot.get("engine_snapshot") if isinstance(snapshot.get("engine_snapshot"), Mapping) else {}


def targets_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, float] | None:
    projection = projection_from_snapshot(snapshot)
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
    if any(item in text for item in ("中", "moderate")):
        return "moderate"
    return "unknown"


def _cardio_effective_factor(intensity: str) -> float:
    return {"unknown": 0.5, "low": 0.5, "moderate": 1.0, "high": 1.25}.get(intensity, 0.5)


def _highest_intensity(values: list[str]) -> str:
    order = {"unknown": -1, "low": 0, "moderate": 1, "high": 2}
    return max(values, key=lambda item: order.get(item, -1), default="unknown")


def _iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


__all__ = [
    "APP_SNAPSHOT_VERSION",
    "calculate_app_snapshot",
    "engine_from_snapshot",
    "normalize_profile",
    "normalize_training",
    "projection_from_snapshot",
    "targets_from_snapshot",
]
