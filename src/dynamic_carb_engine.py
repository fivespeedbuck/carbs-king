"""Deterministic reference engine for the dynamic carb-cycle design.

The module consumes normalized facts.  App JSON/session migration belongs in an
adapter so replay tools and the UI share one calculation path.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import exp, isfinite, sqrt
from statistics import fmean, mean, median, stdev
import hashlib
import json
from typing import Any, Mapping, Sequence


ENGINE_VERSION = "CK-DCE-v3.3-rc2-r3-final-candidate"
PARAMETER_SET_VERSION = "CK-DCE-params-2026-08-03-v3.3-rc2-r3-final"
EVIDENCE_VERSION = "CK-DCE-evidence-2026-08-03-v3.3-rc2-r3-final"
MODEL_DOCUMENT_SHA256 = "790ABE73F2B34F48FD9B2DFAF938F685A1D4242DA161CA6350AB1CE0B4C3D16B"
SCHEMA_VERSION = 3
UI_CONTRACT_VERSION = 2
CALIBRATION_MODEL_VERSION = "hall-linearized-2015-v2"
CALIBRATION_RHO_KCAL_PER_KG = 8840.0
CALIBRATION_EPSILON_KCAL_PER_KG_DAY = 25.8
DISPLAY_FAT_SHARE_ROUNDING_TOLERANCE = 0.002
REFERENCE_DISTRIBUTION_VERSION = "ref-dist-2026-08-03-r1"
SOLVER_VERSION = "ordered-waterline-display-v2"
BOUNDARY_VERSION = "rc2-r3-final-ordered-display-bounds-2026-08-03"
INPUT_CONTRACT_VERSION = "input-contract-2026-08-03-r1"
REFERENCE_COUNTS = {"low": 35, "mid": 45, "high": 20}
TIER_OFFSETS = {"low": -0.06, "mid": 0.0, "high": 0.08}
TIERS = ("low", "mid", "high")
TIER_TO_DAY = {"low": "低碳日", "mid": "中碳日", "high": "高碳日"}
DAY_TO_TIER = {value: key for key, value in TIER_TO_DAY.items()}
MIN_TIER_GAP_KCAL = 1.0
DISPLAY_SAFE_TIER_GAP_KCAL = 20.000001

ACTIVITY_CATEGORIES = {
    "inactive": "inactive",
    "low_active": "low_active",
    "active": "active",
    "very_active": "very_active",
}
LEGACY_ACTIVITY_FACTORS = {
    "久坐少动": 1.25,
    "偶尔运动": 1.35,
    "规律训练": 1.45,
    "高频训练": 1.60,
    "sedentary": 1.25,
    "light": 1.35,
    "regular": 1.45,
    "high": 1.60,
}
GOALS = {
    "减脂": "cut_standard", "保持": "recomp", "增肌": "gain_controlled",
    "cut": "cut_standard", "maintain": "recomp", "gain": "gain_controlled",
    "cut_standard": "cut_standard", "recomp": "recomp", "gain_controlled": "gain_controlled",
}
SEXES = {"男": "male", "女": "female", "male": "male", "female": "female"}

TARGET_CONFIG = {
    "gain_controlled": {"requested_speed": 0.0025, "max_positive_delta": 400.0, "max_negative_delta": -500.0},
    "recomp": {"requested_speed": 0.0, "max_positive_delta": 400.0, "max_negative_delta": -500.0},
    "cut_standard": {"requested_speed": -0.005, "max_positive_delta": 400.0, "max_negative_delta": -500.0},
}

INPUT_LIMITS = {
    "weight_kg": (25.0, 500.0),
    "height_cm": (120.0, 230.0),
    "bodyfat_percent": (1.0, 75.0),
    "maintenance_kcal": (800.0, 8000.0),
    "age_years": (19.0, 90.0),
}

DEMANDS: dict[str, dict[str, float | str]] = {
    "provisional_low": {"rank": 2.0, "day_type": "暂定低碳"},
    "rest": {"rank": 2.0, "day_type": "低碳日"},
    "resistance_low": {"rank": 2.0, "day_type": "低碳日"},
    "resistance_medium": {"rank": 2.5, "day_type": "中碳日"},
    "resistance_high": {"rank": 3.0, "day_type": "高碳日"},
    "cardio_light": {"rank": 2.0, "day_type": "低碳日"},
    "cardio_moderate": {"rank": 3.0, "day_type": "中碳日"},
    "cardio_high": {"rank": 5.0, "day_type": "高碳日"},
    "endurance_long": {"rank": 6.0, "day_type": "高碳日"},
    "endurance_extreme": {"rank": 10.0, "day_type": "高碳日"},
    "mixed_high": {"rank": 4.0, "day_type": "高碳日"},
}

CALIBRATION_WINDOWS = (
    (31, 12, 24, 28),
    (60, 16, 45, 50),
    (90, 20, 68, 75),
)
LOAD_KINDS = {"external", "bodyweight", "added_weight", "assisted", "unknown"}


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if isfinite(result) else default


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def _round_step(value: float, step: float) -> float:
    unit = Decimal(str(step))
    return float((Decimal(str(value)) / unit).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * unit)


def _positive(value: Any, field: str) -> float:
    result = _number(value)
    if result is None or result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _round5(value: float) -> float:
    return float((Decimal(str(value)) / Decimal("5")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal("5"))


def _ceil5(value: float) -> float:
    rounded = _round5(value)
    return rounded if rounded >= value - 1e-9 else rounded + 5.0


def _floor5(value: float) -> float:
    rounded = _round5(value)
    return rounded if rounded <= value + 1e-9 else rounded - 5.0


def _round_tenth(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _normalize_bodyfat_records(records: Sequence[Mapping[str, Any]], as_of_date: date) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    for record in records:
        measured = _parse_date(record.get("date"))
        value = _number(record.get("bodyfat_percent"))
        if measured is None or value is None:
            errors.append("input_invalid_measurement_date")
            continue
        if measured > as_of_date:
            errors.append("input_future_measurement")
            continue
        if not INPUT_LIMITS["bodyfat_percent"][0] <= value <= INPUT_LIMITS["bodyfat_percent"][1]:
            errors.append("input_invalid_bodyfat")
            continue
        stable_id = str(record.get("record_id") or _canonical_sha({
            "date": measured.isoformat(), "bodyfat_percent": value,
        }))
        normalized.append({
            "date": measured, "bodyfat_percent": value, "record_id": stable_id,
            "source": record.get("source", "unknown"),
        })
    normalized.sort(key=lambda row: (
        (as_of_date - row["date"]).days, -row["date"].toordinal(), row["record_id"],
        row["bodyfat_percent"], str(row["source"]),
    ))
    return {"records": normalized, "reason_codes": sorted(set(errors))}


def resolve_phase_protein(
    target: str,
    weight_kg: float,
    height_cm: float,
    sex: str,
    bodyfat_records: Sequence[Mapping[str, Any]],
    as_of_date: date,
    *,
    age_years: int = 30,
) -> dict[str, Any]:
    target_key = GOALS.get(str(target))
    sex_key = SEXES.get(str(sex))
    errors: list[str] = []
    if target_key is None:
        errors.append("input_invalid_target")
    if sex_key is None:
        errors.append("input_invalid_sex")
    if not INPUT_LIMITS["weight_kg"][0] <= weight_kg <= INPUT_LIMITS["weight_kg"][1]:
        errors.append("input_invalid_weight")
    if not INPUT_LIMITS["height_cm"][0] <= height_cm <= INPUT_LIMITS["height_cm"][1]:
        errors.append("input_invalid_height")
    if not INPUT_LIMITS["age_years"][0] <= age_years <= INPUT_LIMITS["age_years"][1]:
        errors.append("input_invalid_age")
    normalized = _normalize_bodyfat_records(bodyfat_records, as_of_date)
    errors.extend(normalized["reason_codes"])
    if errors:
        return {"status": "invalid", "protein_g": None,
                "reason_codes": ["input_invalid", *sorted(set(errors))]}
    records = normalized["records"]
    coefficient_ffm = 2.3 if target_key == "cut_standard" else 2.0
    coefficient_weight = 1.8 if target_key == "cut_standard" else 1.6
    paired = [row for row in records if 0 <= (as_of_date - row["date"]).days <= 7]
    if paired:
        selected = paired[0]
        ffm = weight_kg * (1.0 - selected["bodyfat_percent"] / 100.0)
        return {
            "status": "valid", "protein_g": coefficient_ffm * ffm,
            "route": "fresh_paired_bodyfat_ffm", "ffm_kg": ffm,
            "bodyfat_record_id": selected["record_id"],
            "reason_codes": ["protein_ffm_fresh_paired"],
        }
    if not records:
        bodyfat_reason = "bodyfat_missing"
    elif all((as_of_date - row["date"]).days > 90 for row in records):
        bodyfat_reason = "bodyfat_stale"
    else:
        bodyfat_reason = "bodyfat_unpaired"
    bmi = weight_kg / (height_cm / 100.0) ** 2
    if bmi >= 30.0:
        denominator = (6680.0 + 216.0 * bmi) if sex_key == "male" else (8780.0 + 244.0 * bmi)
        ffm = 9270.0 * weight_kg / denominator
        return {
            "status": "valid", "protein_g": coefficient_ffm * ffm,
            "route": "janmahasatian_ffm", "ffm_kg": ffm, "bmi": bmi,
            "bodyfat_record_id": None,
            "reason_codes": [bodyfat_reason, "janmahasatian_ffm_route"],
        }
    return {
        "status": "valid", "protein_g": float(Decimal(str(coefficient_weight)) * Decimal(str(weight_kg))),
        "route": "bodyweight", "ffm_kg": None, "bmi": bmi, "bodyfat_record_id": None,
        "reason_codes": [bodyfat_reason],
    }


def classify_training(training: Mapping[str, Any] | None) -> dict[str, Any]:
    facts = training if isinstance(training, Mapping) else {}
    status = str(facts.get("status") or "unknown")
    if status == "explicit_rest":
        return _classification("rest", formal=True, sample=True, reasons=["explicit_rest"])
    if status in {"unknown", "planned_pending", "outcome_unknown"}:
        return _classification("provisional_low", formal=False, sample=False, reasons=[status])
    if status not in {"planned_confirmed", "active", "completed"}:
        return _classification("provisional_low", formal=False, sample=False, reasons=["invalid_training_status"])

    resistance = facts.get("resistance") if isinstance(facts.get("resistance"), Mapping) else None
    cardio = facts.get("cardio") if isinstance(facts.get("cardio"), Mapping) else None
    medium_or_higher_sessions = max(0, int(_number(facts.get("medium_or_higher_sessions"), 0) or 0))
    resistance_key = _classify_resistance(resistance) if resistance else None
    cardio_key = _classify_cardio(cardio) if cardio else None
    if not resistance_key and not cardio_key:
        return _classification("provisional_low", formal=False, sample=False, reasons=["confirmed_training_has_no_valid_work"])

    reasons: list[str] = []
    if resistance_key:
        reasons.append(resistance_key)
    if cardio_key:
        reasons.append(cardio_key)
    if resistance_key and cardio_key:
        resistance_medium = resistance_key in {"resistance_medium", "resistance_high"}
        cardio_medium = cardio_key in {"cardio_moderate", "cardio_high", "endurance_long", "endurance_extreme"}
        if resistance_medium and cardio_medium:
            selected = max(
                (resistance_key, cardio_key, "mixed_high"),
                key=lambda key: float(DEMANDS[key]["rank"]),
            )
            if selected == "mixed_high":
                reasons.append("combined_training_upgrade")
        else:
            selected = max((resistance_key, cardio_key), key=lambda key: float(DEMANDS[key]["rank"]))
    else:
        selected = resistance_key or cardio_key or "provisional_low"

    if medium_or_higher_sessions >= 2:
        upgraded = max((selected, "mixed_high"), key=lambda key: float(DEMANDS[key]["rank"]))
        if upgraded != selected:
            reasons.append("multiple_sessions_upgrade")
        selected = upgraded
    if bool(facts.get("close_second_high_glycogen_session")):
        upgraded = max((selected, "mixed_high"), key=lambda key: float(DEMANDS[key]["rank"]))
        if upgraded != selected:
            reasons.append("close_second_session_upgrade")
        selected = upgraded
    return _classification(selected, formal=True, sample=status == "completed", reasons=reasons)


def validate_exercise_parameters(
    exercise: Mapping[str, Any] | None,
    *,
    require_confirmation: bool = True,
) -> dict[str, Any]:
    """Validate whether a raw planned exercise may enter a formal plan.

    `load_kind` carries the semantic distinction between a confirmed bodyweight
    movement and an unknown or default zero load.  Completed legacy facts may be
    migrated separately with reduced quality; this validator deliberately does
    not guess their meaning.
    """

    item = exercise if isinstance(exercise, Mapping) else {}
    reasons: list[str] = []
    if require_confirmation and not bool(item.get("parameters_confirmed")):
        reasons.append("parameters_not_confirmed")
    mode = str(item.get("recording_mode") or "strength")
    if mode == "strength":
        load_kind = str(item.get("load_kind") or "unknown")
        if load_kind not in LOAD_KINDS or load_kind == "unknown":
            reasons.append("load_kind_unknown")
        sets = item.get("sets") if isinstance(item.get("sets"), list) else []
        if not sets:
            reasons.append("sets_missing")
        for index, training_set in enumerate(sets):
            if not isinstance(training_set, Mapping):
                reasons.append(f"set_{index + 1}_invalid")
                continue
            reps = _number(training_set.get("reps"))
            if reps is None or reps <= 0:
                reasons.append(f"set_{index + 1}_reps_missing")
            if load_kind == "external":
                weight = _number(training_set.get("weight_kg"))
                if weight is None or weight < 0:
                    reasons.append(f"set_{index + 1}_external_load_missing")
            elif load_kind == "added_weight":
                weight = _number(training_set.get("weight_kg"))
                if weight is None or weight <= 0:
                    reasons.append(f"set_{index + 1}_added_load_missing")
            elif load_kind == "assisted":
                assistance = _number(training_set.get("assistance_kg", training_set.get("weight_kg")))
                if assistance is None or assistance <= 0:
                    reasons.append(f"set_{index + 1}_assistance_missing")
        return {"ready": not reasons, "recording_mode": mode, "load_kind": load_kind, "reason_codes": reasons}

    if mode in {"timed", "cardio"}:
        duration = _number(item.get("duration_seconds"))
        if duration is None or duration <= 0:
            reasons.append("duration_missing")
        return {"ready": not reasons, "recording_mode": mode, "load_kind": None, "reason_codes": reasons}

    reasons.append("recording_mode_invalid")
    return {"ready": False, "recording_mode": mode, "load_kind": None, "reason_codes": reasons}


def _classification(key: str, *, formal: bool, sample: bool, reasons: Sequence[str]) -> dict[str, Any]:
    demand = DEMANDS[key]
    return {
        "demand_key": key,
        "day_type": demand["day_type"],
        "formal": formal,
        "training_sample": sample,
        "demand_rank": float(demand["rank"]),
        "reason_codes": list(reasons),
    }


def _classify_resistance(facts: Mapping[str, Any]) -> str | None:
    total = max(0, int(_number(facts.get("work_sets_total"), 0) or 0))
    peak = max(0, int(_number(facts.get("peak_body_part_sets"), 0) or 0))
    duration = _number(facts.get("duration_min"))
    if total <= 0:
        return None
    high_signals = sum(
        (
            total >= 20,
            peak > 10,
            duration is not None and duration >= 75,
        )
    )
    if (duration is not None and duration >= 120) or high_signals >= 2:
        return "resistance_high"
    duration_low = duration is None or duration < 45
    if total < 8 and peak < 6 and duration_low:
        return "resistance_low"
    return "resistance_medium"


def _classify_cardio(facts: Mapping[str, Any]) -> str | None:
    duration = _number(facts.get("duration_min"))
    if duration is None or duration <= 0:
        return None
    intensity = str(facts.get("intensity") or "unknown")
    factor = {"unknown": 0.5, "low": 0.5, "moderate": 1.0, "high": 1.25}.get(intensity, 0.5)
    effective = _number(facts.get("effective_minutes"))
    effective = max(0.0, effective) if effective is not None else duration * factor
    if duration >= 240 and effective >= 240:
        return "endurance_extreme"
    if duration >= 120 and effective >= 120:
        return "endurance_long"
    if effective >= 60:
        return "cardio_high"
    if effective >= 45:
        return "cardio_moderate"
    return "cardio_light"


def calculate_body_energy(profile: Mapping[str, Any]) -> dict[str, Any]:
    weight = _positive(profile.get("weight_kg", profile.get("weight")), "weight_kg")
    height = _positive(profile.get("height_cm", profile.get("height")), "height_cm")
    age = _positive(profile.get("age_years", profile.get("age")), "age_years")
    sex = SEXES.get(str(profile.get("sex") or ""))
    goal = GOALS.get(str(profile.get("goal", profile.get("macro_goal", ""))))
    if sex is None or goal is None or not 25 <= weight <= 500 or not 120 <= height <= 230 or not 19 <= age <= 90:
        raise ValueError("profile sex, goal, weight, height or age is outside the supported adult range")

    baseline_weight = _number(profile.get("phase_baseline_weight_kg"), weight) or weight
    if not INPUT_LIMITS["weight_kg"][0] <= baseline_weight <= INPUT_LIMITS["weight_kg"][1]:
        raise ValueError("phase baseline weight is outside the supported adult range")
    bodyfat = _number(profile.get("bodyfat_percent", profile.get("bodyfat")))
    if bodyfat is not None and not INPUT_LIMITS["bodyfat_percent"][0] <= bodyfat <= INPUT_LIMITS["bodyfat_percent"][1]:
        raise ValueError("bodyfat is outside the supported adult range")

    rmr = 10 * weight + 6.25 * height - 5 * age + (5 if sex == "male" else -161)
    maintenance_override = _number(profile.get("phase_maintenance_kcal", profile.get("maintenance_kcal")))
    if maintenance_override is not None and maintenance_override > 0:
        maintenance = maintenance_override
        energy_method = "phase_maintenance_fixed" if profile.get("phase_maintenance_kcal") is not None else "maintenance_override"
        activity_category = None
    else:
        explicit_activity = str(profile.get("activity_category") or "")
        activity_category = ACTIVITY_CATEGORIES.get(explicit_activity)
        if activity_category is not None:
            maintenance = _nasem_adult_eer(sex, activity_category, age, height, weight)
            energy_method = "nasem_2023_adult_eer"
        else:
            legacy_activity_factor = LEGACY_ACTIVITY_FACTORS.get(str(profile.get("activity_habit") or ""))
            if legacy_activity_factor is None:
                raise ValueError("activity category is missing or invalid")
            maintenance = rmr * legacy_activity_factor
            energy_method = "legacy_mifflin_activity_prior"
    if not INPUT_LIMITS["maintenance_kcal"][0] <= maintenance <= INPUT_LIMITS["maintenance_kcal"][1]:
        raise ValueError("maintenance energy is outside the supported range")

    target_spec = TARGET_CONFIG[goal]
    requested_speed = float(target_spec["requested_speed"])
    raw_delta = _hall_energy_change_for_28_days(baseline_weight, requested_speed)
    guarded_delta = min(
        float(target_spec["max_positive_delta"]),
        max(float(target_spec["max_negative_delta"]), raw_delta),
    )
    raw_budget = maintenance + raw_delta
    guarded_budget = maintenance + guarded_delta
    budget_reasons = ["hall_delta_raw"]
    if abs(guarded_delta - raw_delta) > 1e-9:
        budget_reasons.extend(["hall_delta_capped", "target_speed_clamped_energy_guard"])

    protein, protein_method, protein_lean_mass, protein_reasons = _protein_anchor(
        profile, baseline_weight, height, age, goal
    )
    fat_anchor = _number(profile.get("phase_fat_anchor_g"), 0.8 * baseline_weight) or 0.8 * baseline_weight
    display_lean_mass = weight * (1 - bodyfat / 100) if bodyfat is not None else protein_lean_mass
    return {
        "weight_kg": weight,
        "phase_baseline_weight_kg": baseline_weight,
        "height_cm": height,
        "age_years": age,
        "sex": sex,
        "goal": goal,
        "rmr_kcal": rmr,
        "maintenance_kcal": maintenance,
        "requested_speed": requested_speed,
        "raw_delta_kcal_day": raw_delta,
        "guarded_delta_kcal_day": guarded_delta,
        "raw_budget_kcal_day": raw_budget,
        "guarded_budget_kcal_day": guarded_budget,
        "goal_energy_kcal": guarded_budget,
        "target_speed_guarded": guarded_delta / (4.0 * baseline_weight * _hall_k28()),
        "protein_g": protein,
        "fat_anchor_g": fat_anchor,
        "lean_mass_kg": display_lean_mass,
        "activity_category": activity_category,
        "energy_method": energy_method,
        "goal_energy_method": "hall_28d_guarded_budget",
        "protein_method": protein_method,
        "protein_reason_codes": protein_reasons,
        "budget_reason_codes": budget_reasons,
        "phase_id": profile.get("phase_id"),
    }


def create_phase_baseline(profile: Mapping[str, Any], effective_date: str | date) -> dict[str, Any]:
    """Freeze the inputs that must remain stable throughout one goal phase."""

    target_date = effective_date if isinstance(effective_date, date) else _parse_date(effective_date)
    if target_date is None:
        raise ValueError("effective_date must be an ISO date")
    base_profile = dict(profile)
    for key in (
        "phase_id", "phase_baseline_weight_kg", "phase_maintenance_kcal", "phase_protein_g",
        "phase_fat_anchor_g", "phase_ffm_kg",
    ):
        base_profile.pop(key, None)
    base_profile["as_of_date"] = target_date.isoformat()
    body = calculate_body_energy(base_profile)
    identity = {
        "started_at": target_date.isoformat(),
        "goal": body["goal"],
        "baseline_weight_kg": body["weight_kg"],
        "maintenance_kcal": body["maintenance_kcal"],
        "protein_g": body["protein_g"],
        "fat_anchor_g": 0.8 * body["weight_kg"],
    }
    return {
        "phase_id": f"phase-{_canonical_sha(identity)[:16].lower()}",
        "started_at": target_date.isoformat(),
        "effective_from": target_date.isoformat(),
        "goal": body["goal"],
        "baseline_weight_kg": body["weight_kg"],
        "maintenance_kcal": body["maintenance_kcal"],
        "protein_g": body["protein_g"],
        "protein_route": body["protein_method"],
        "protein_reason_codes": list(body.get("protein_reason_codes", [])),
        "ffm_kg": body.get("lean_mass_kg") if body["protein_method"] != "bodyweight" else None,
        "fat_anchor_g": 0.8 * body["weight_kg"],
        "algorithm_version": ENGINE_VERSION,
        "parameter_set_version": PARAMETER_SET_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "model_document_sha256": MODEL_DOCUMENT_SHA256,
    }


def create_refreshed_phase(previous_phase: Mapping[str, Any], refresh: Mapping[str, Any]) -> dict[str, Any]:
    """Create the deterministic next-day phase produced by a verified baseline refresh."""

    if not refresh.get("refresh"):
        raise ValueError("refresh result is not eligible")
    effective_from = str(refresh.get("effective_from") or "")
    if _parse_date(effective_from) is None:
        raise ValueError("refresh effective_from must be an ISO date")
    identity = {
        "previous_phase_id": previous_phase.get("phase_id"),
        "effective_from": effective_from,
        "goal": previous_phase.get("goal"),
        "baseline_weight_kg": refresh.get("new_baseline_weight_kg"),
        "protein_g": refresh.get("new_protein_g"),
        "fat_anchor_g": refresh.get("new_fat_anchor_g"),
    }
    return {
        "phase_id": f"phase-{_canonical_sha(identity)[:16].lower()}",
        "previous_phase_id": previous_phase.get("phase_id"),
        "started_at": effective_from,
        "effective_from": effective_from,
        "goal": previous_phase.get("goal"),
        "baseline_weight_kg": float(refresh["new_baseline_weight_kg"]),
        "maintenance_kcal": float(previous_phase["maintenance_kcal"]),
        "protein_g": float(refresh["new_protein_g"]),
        "protein_route": refresh.get("protein_route"),
        "protein_reason_codes": list(refresh.get("protein_reason_codes", [])),
        "ffm_kg": refresh.get("new_ffm_kg"),
        "fat_anchor_g": float(refresh["new_fat_anchor_g"]),
        "refresh_trigger": refresh.get("trigger"),
        "refresh_window_start": refresh.get("window_start"),
        "refresh_window_end": refresh.get("window_end"),
        "refresh_reason_codes": list(refresh.get("reason_codes", [])),
        "algorithm_version": ENGINE_VERSION,
        "parameter_set_version": PARAMETER_SET_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "model_document_sha256": MODEL_DOCUMENT_SHA256,
    }


def _nasem_adult_eer(sex: str, activity: str, age: float, height: float, weight: float) -> float:
    coefficients = {
        ("male", "inactive"): (753.07, -10.83, 6.50, 14.10),
        ("male", "low_active"): (581.47, -10.83, 8.30, 14.94),
        ("male", "active"): (1004.82, -10.83, 6.52, 15.91),
        ("male", "very_active"): (-517.88, -10.83, 15.61, 19.11),
        ("female", "inactive"): (584.90, -7.01, 5.72, 11.71),
        ("female", "low_active"): (575.77, -7.01, 6.60, 12.14),
        ("female", "active"): (710.25, -7.01, 6.54, 12.34),
        ("female", "very_active"): (511.83, -7.01, 9.07, 12.56),
    }
    intercept, age_factor, height_factor, weight_factor = coefficients[(sex, activity)]
    return intercept + age_factor * age + height_factor * height + weight_factor * weight


def _hall_energy_change_for_28_days(weight: float, weekly_rate: float) -> float:
    return 4.0 * weekly_rate * weight * _hall_k28()


def _hall_k28() -> float:
    response = 1.0 - exp(-CALIBRATION_EPSILON_KCAL_PER_KG_DAY * 28.0 / CALIBRATION_RHO_KCAL_PER_KG)
    return CALIBRATION_EPSILON_KCAL_PER_KG_DAY / response


def _protein_anchor(
    profile: Mapping[str, Any], weight: float, height: float, age: float, goal: str
) -> tuple[float, str, float | None, list[str]]:
    explicit = _number(profile.get("phase_protein_g", profile.get("protein_target_g")))
    if explicit is not None and explicit > 0:
        return explicit, "phase_fixed", _number(profile.get("phase_ffm_kg")), ["phase_protein_fixed"]
    records = profile.get("bodyfat_records")
    as_of = _parse_date(profile.get("as_of_date"))
    if isinstance(records, Sequence) and not isinstance(records, (str, bytes)) and as_of is not None:
        resolution = resolve_phase_protein(
            goal, weight, height, str(profile.get("sex") or ""), records, as_of, age_years=int(age)
        )
        if resolution.get("status") == "valid":
            return (
                float(resolution["protein_g"]), str(resolution["route"]),
                _number(resolution.get("ffm_kg")), list(resolution.get("reason_codes", [])),
            )
    bodyfat = _number(profile.get("bodyfat_percent", profile.get("bodyfat")))
    bodyfat_status = str(profile.get("bodyfat_status") or ("observed" if bodyfat is not None else "unknown"))
    bodyfat_age = _number(profile.get("bodyfat_age_days"), 0) or 0
    coefficient_ffm = 2.3 if goal == "cut_standard" else 2.0
    coefficient_weight = 1.8 if goal == "cut_standard" else 1.6
    if bodyfat is not None and 1 <= bodyfat <= 75 and bodyfat_status in {"observed", "carried"} and 0 <= bodyfat_age <= 7:
        lean_mass = weight * (1 - bodyfat / 100)
        protein = lean_mass * coefficient_ffm
        return protein, "fresh_paired_bodyfat_ffm", lean_mass, ["protein_ffm_fresh_paired"]

    if bodyfat is None:
        bodyfat_reason = "bodyfat_missing"
    elif bodyfat_age > 90:
        bodyfat_reason = "bodyfat_stale"
    else:
        bodyfat_reason = "bodyfat_unpaired"

    bmi = weight / (height / 100) ** 2
    if bmi >= 30:
        if SEXES.get(str(profile.get("sex") or "")) == "male":
            lean_mass = 9270 * weight / (6680 + 216 * bmi)
        else:
            lean_mass = 9270 * weight / (8780 + 244 * bmi)
        protein = lean_mass * coefficient_ffm
        return protein, "janmahasatian_ffm", lean_mass, [bodyfat_reason, "janmahasatian_ffm_route"]
    protein = float(Decimal(str(coefficient_weight)) * Decimal(str(weight)))
    return protein, "bodyweight", None, [bodyfat_reason]


def _tier_bounds(target: str, maintenance: float) -> dict[str, tuple[float, float]]:
    if target == "gain_controlled":
        return {
            "low": (0.95 * maintenance, 1.10 * maintenance),
            "mid": (1.00 * maintenance, 1.16 * maintenance),
            "high": (1.05 * maintenance, min(1.25 * maintenance, maintenance + 500.0)),
        }
    if target == "recomp":
        return {
            "low": (0.85 * maintenance, 0.98 * maintenance),
            "mid": (0.95 * maintenance, 1.05 * maintenance),
            "high": (1.02 * maintenance, 1.12 * maintenance),
        }
    return {
        "low": (max(0.65 * maintenance, maintenance - 750.0), max(0.85 * maintenance, maintenance - 500.0)),
        "mid": (max(0.75 * maintenance, maintenance - 600.0), 0.95 * maintenance),
        "high": (0.90 * maintenance, 1.00 * maintenance),
    }


def _v33_macros(energy: float, protein: float, fat_anchor: float) -> dict[str, Any]:
    fat = max(0.20 * energy / 9.0, min(fat_anchor, 0.30 * energy / 9.0))
    carb = (energy - 4.0 * protein - 9.0 * fat) / 4.0
    if carb < -1e-9:
        return {
            "status": "infeasible",
            "energy_internal_kcal": energy,
            "protein_internal_g": protein,
            "fat_internal_g": fat,
            "carb_conflict_magnitude_g": abs(carb),
            "conflict_direction": "below_zero",
            "reason_codes": ["protein_energy_conflict"],
            "user_prompt": "固定蛋白与当前能量边界无法形成非负宏量，请提高计划能量或改用手动目标。",
        }
    carb = max(0.0, carb)
    reasons = ["fat_anchor_applied"]
    if fat_anchor < 0.20 * energy / 9.0:
        reasons = ["fat_anchor_raised_to_20pct"]
    elif fat_anchor > 0.30 * energy / 9.0:
        reasons = ["fat_anchor_lowered_to_30pct"]
    if carb < 130.0:
        reasons.append("carb_below_rda_soft_target")
    protein_display = _round_step(protein, 5.0)
    carb_display = _round_step(carb, 5.0)
    fat_display = _round_step(fat, 0.1)
    display_energy_exact = 4.0 * protein_display + 4.0 * carb_display + 9.0 * fat_display
    return {
        "status": "feasible",
        "energy_internal_kcal": energy,
        "protein_internal_g": protein,
        "carb_internal_g": carb,
        "fat_internal_g": fat,
        "protein_display_g": protein_display,
        "carb_display_g": carb_display,
        "fat_display_g": fat_display,
        "energy_from_display_macros_exact": display_energy_exact,
        "energy_display_kcal": _round_step(display_energy_exact, 1.0),
        "display_macro_energy_error_vs_internal": display_energy_exact - energy,
        "reason_codes": reasons,
    }


def _macro_min_energy(protein: float, fat_anchor: float) -> float:
    low, high = 0.0, max(1000.0, 10.0 * protein)
    for _ in range(100):
        middle = (low + high) / 2.0
        if _v33_macros(middle, protein, fat_anchor)["status"] == "feasible":
            high = middle
        else:
            low = middle
    return high


def _effective_tier_bounds(
    target: str, maintenance: float, protein: float, fat_anchor: float, tier_gap: float
) -> dict[str, Any]:
    raw = _tier_bounds(target, maintenance)
    macro_floor = _macro_min_energy(protein, fat_anchor)
    low = {tier: max(raw[tier][0], macro_floor) for tier in TIERS}
    high = {tier: raw[tier][1] for tier in TIERS}
    if any(low[tier] > high[tier] for tier in TIERS):
        return {"feasible": False, "reason_codes": ["phase_budget_infeasible", "protein_energy_conflict"]}
    for _ in range(4):
        low["mid"] = max(low["mid"], low["low"] + tier_gap)
        low["high"] = max(low["high"], low["mid"] + tier_gap)
        high["mid"] = min(high["mid"], high["high"] - tier_gap)
        high["low"] = min(high["low"], high["mid"] - tier_gap)
    if any(low[tier] > high[tier] for tier in TIERS):
        return {"feasible": False, "reason_codes": ["phase_budget_infeasible", "tier_order_infeasible"]}
    return {"feasible": True, "lo": low, "hi": high, "macro_min_energy_kcal_day": macro_floor}


def _solve_distribution_once(
    target: str,
    counts: Mapping[str, int],
    budget: float,
    *,
    maintenance: float,
    baseline_weight: float,
    protein: float,
    fat_anchor: float,
    mode: str,
    tier_gap: float,
) -> dict[str, Any]:
    normalized_counts = {tier: max(0, int(counts.get(tier, 0))) for tier in TIERS}
    total_days = sum(normalized_counts.values())
    if total_days == 0:
        return {"mode": mode, "counts": normalized_counts, "feasible": False,
                "reason_codes": ["no_formal_days", "phase_budget_infeasible"]}
    prepared = _effective_tier_bounds(target, maintenance, protein, fat_anchor, tier_gap)
    if not prepared["feasible"]:
        return {"mode": mode, "counts": normalized_counts, **prepared}
    low, high = prepared["lo"], prepared["hi"]
    weights = {tier: normalized_counts[tier] / total_days for tier in TIERS}

    def values(waterline: float) -> dict[str, float]:
        low_value = max(low["low"], min(high["low"], waterline + TIER_OFFSETS["low"] * maintenance))
        mid_value = max(low["mid"], min(high["mid"], max(waterline, low_value + tier_gap)))
        high_value = max(
            low["high"],
            min(high["high"], max(waterline + TIER_OFFSETS["high"] * maintenance, mid_value + tier_gap)),
        )
        return {"low": low_value, "mid": mid_value, "high": high_value}

    def average(waterline: float) -> float:
        row = values(waterline)
        return sum(weights[tier] * row[tier] for tier in TIERS)

    minimum_budget = sum(weights[tier] * low[tier] for tier in TIERS)
    maximum_budget = sum(weights[tier] * high[tier] for tier in TIERS)
    feasible = minimum_budget - 1e-8 <= budget <= maximum_budget + 1e-8
    boundary_budget = min(maximum_budget, max(minimum_budget, budget))
    span = max(1.0, max(high.values()) - min(low.values()), abs(maintenance))
    waterline_low = min(low[tier] - TIER_OFFSETS[tier] * maintenance for tier in TIERS) - span
    waterline_high = max(high[tier] - TIER_OFFSETS[tier] * maintenance for tier in TIERS) + span
    expansions = 0
    while average(waterline_low) > boundary_budget + 1e-8:
        span *= 2.0
        waterline_low -= span
        expansions += 1
    while average(waterline_high) < boundary_budget - 1e-8:
        span *= 2.0
        waterline_high += span
        expansions += 1
    bracket = {
        "x_low": waterline_low, "x_high": waterline_high, "expansions": expansions,
        "average_low": average(waterline_low), "average_high": average(waterline_high),
    }
    for _ in range(120):
        middle = (waterline_low + waterline_high) / 2.0
        if average(middle) < boundary_budget:
            waterline_low = middle
        else:
            waterline_high = middle
    waterline = (waterline_low + waterline_high) / 2.0
    energies = values(waterline)
    result = {
        "mode": mode,
        "counts": normalized_counts,
        "feasible": feasible,
        "guarded_budget_kcal_day": budget,
        "feasible_average_min_kcal_day": minimum_budget,
        "feasible_average_max_kcal_day": maximum_budget,
        "feasible_speed_min": (minimum_budget - maintenance) / (4.0 * baseline_weight * _hall_k28()),
        "feasible_speed_max": (maximum_budget - maintenance) / (4.0 * baseline_weight * _hall_k28()),
        "macro_min_energy_kcal_day": prepared["macro_min_energy_kcal_day"],
        "internal_tier_gap_kcal": tier_gap,
        "waterline_bracket": bracket,
        "effective_bounds": {tier: [low[tier], high[tier]] for tier in TIERS},
        "boundary_preview": {"boundary_budget_kcal_day": boundary_budget, "waterline_x": waterline,
                             "daily_energy_by_tier_kcal": energies},
        "reason_codes": ["period_budget_rebalanced"] if feasible else ["phase_budget_infeasible"],
    }
    result["fastest_feasible_speed"] = (
        result["feasible_speed_min"] if target == "cut_standard" else result["feasible_speed_max"]
    )
    result["slowest_feasible_speed"] = (
        result["feasible_speed_max"] if target == "cut_standard" else result["feasible_speed_min"]
    )
    if any(energies[tier] <= low[tier] + 1e-7 for tier in TIERS if normalized_counts[tier]):
        result["reason_codes"].append("day_bound_clamped_low")
    if any(energies[tier] >= high[tier] - 1e-7 for tier in TIERS if normalized_counts[tier]):
        result["reason_codes"].append("day_bound_clamped_high")
    if not feasible:
        result["user_prompt"] = "当前目标与计划边界不兼容，请调整速度或训练分布。"
        return result
    daily_macros = {tier: _v33_macros(energies[tier], protein, fat_anchor) for tier in TIERS}
    if any(row["status"] != "feasible" for row in daily_macros.values()):
        return {
            **result,
            "feasible": False,
            "reason_codes": ["phase_budget_infeasible", "protein_energy_conflict"],
            "user_prompt": "固定蛋白与正式日边界无法形成全周期非负宏量。",
        }
    result.update({
        "applied_budget_kcal_day": budget,
        "target_speed_applied": (budget - maintenance) / (4.0 * baseline_weight * _hall_k28()),
        "daily_energy_by_tier_kcal": energies,
        "daily_macros_by_tier": daily_macros,
        "remaining_budget_kcal": budget * total_days - average(waterline) * total_days,
        "period_closure_error_kcal": average(waterline) - budget,
        "clamped_days": [
            {"tier": tier, "count": normalized_counts[tier]}
            for tier in TIERS
            if abs(energies[tier] - low[tier]) < 1e-7 or abs(energies[tier] - high[tier]) < 1e-7
        ],
    })
    if mode == "period_preview_constrained":
        result["applied_budget_kcal_total"] = budget * total_days
        result["period_total_closure_error_kcal"] = (average(waterline) - budget) * total_days
    return result


def _display_tier_contract(macros_by_tier: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    energies = [float(macros_by_tier[tier]["energy_display_kcal"]) for tier in TIERS]
    signatures = [
        (macros_by_tier[tier]["protein_display_g"], macros_by_tier[tier]["carb_display_g"],
         macros_by_tier[tier]["fat_display_g"])
        for tier in TIERS
    ]
    return {
        "ordered": energies[0] < energies[1] < energies[2],
        "distinct_macro_signatures": len(set(signatures)) == len(TIERS),
        "display_energy_by_tier_kcal": dict(zip(TIERS, energies)),
    }


def solve_distribution(
    target: str,
    counts: Mapping[str, int],
    budget: float,
    *,
    maintenance: float,
    baseline_weight: float,
    protein: float,
    fat_anchor: float,
    mode: str = "period_preview_constrained",
) -> dict[str, Any]:
    first = _solve_distribution_once(
        target, counts, budget, maintenance=maintenance, baseline_weight=baseline_weight,
        protein=protein, fat_anchor=fat_anchor, mode=mode, tier_gap=MIN_TIER_GAP_KCAL,
    )
    if not first["feasible"]:
        if mode == "runtime_fixed_day" and "runtime_reference_infeasible" not in first["reason_codes"]:
            first["reason_codes"].append("runtime_reference_infeasible")
        return first
    contract = _display_tier_contract(first["daily_macros_by_tier"])
    if contract["ordered"] and contract["distinct_macro_signatures"]:
        first["display_tier_contract"] = contract
        return first
    retry = _solve_distribution_once(
        target, counts, budget, maintenance=maintenance, baseline_weight=baseline_weight,
        protein=protein, fat_anchor=fat_anchor, mode=mode, tier_gap=DISPLAY_SAFE_TIER_GAP_KCAL,
    )
    if retry["feasible"]:
        retry_contract = _display_tier_contract(retry["daily_macros_by_tier"])
        if retry_contract["ordered"] and retry_contract["distinct_macro_signatures"]:
            retry["display_tier_contract"] = retry_contract
            retry["reason_codes"].append("display_tier_gap_expanded")
            retry["initial_display_tier_contract"] = contract
            return retry
    failure = {
        "mode": mode, "counts": dict(counts), "guarded_budget_kcal_day": budget, "feasible": False,
        "reason_codes": ["phase_budget_infeasible", "tier_order_infeasible", "display_tier_collapse"],
        "user_prompt": "当前边界无法生成清晰不同的低、中、高显示目标，请调整速度或计划分布。",
    }
    if mode == "runtime_fixed_day":
        failure["reason_codes"].append("runtime_reference_infeasible")
    return failure


def _macro_compat(row: Mapping[str, Any], extra_reasons: Sequence[str] = ()) -> dict[str, Any]:
    if row.get("status") != "feasible":
        return {
            "status": "macro_infeasible",
            "energy_kcal": row.get("energy_internal_kcal"),
            "protein_g": row.get("protein_internal_g"),
            "carb_g": None,
            "fat_g": None,
            "reason_codes": list(dict.fromkeys([*extra_reasons, *row.get("reason_codes", [])])),
        }
    protein = float(row["protein_internal_g"])
    carb = float(row["carb_internal_g"])
    fat = float(row["fat_internal_g"])
    energy = float(row["energy_internal_kcal"])
    display_protein = float(row["protein_display_g"])
    display_carb = float(row["carb_display_g"])
    display_fat = float(row["fat_display_g"])
    return {
        **dict(row),
        "status": "ok",
        "energy_kcal": energy,
        "protein_g": protein,
        "carb_g": carb,
        "fat_g": fat,
        "display": {
            "protein_g": display_protein, "protein_range_g": [display_protein, display_protein],
            "carb_g": display_carb, "carb_range_g": [display_carb, display_carb],
            "fat_g": display_fat, "fat_range_g": [display_fat, display_fat],
        },
        "fat_energy_share": fat * 9.0 / energy,
        "energy_closure_error": protein * 4.0 + carb * 4.0 + fat * 9.0 - energy,
        "reason_codes": list(dict.fromkeys([*extra_reasons, *row.get("reason_codes", [])])),
    }


def solve_macros(body: Mapping[str, Any], classification: Mapping[str, Any]) -> dict[str, Any]:
    runtime = solve_distribution(
        str(body["goal"]), REFERENCE_COUNTS, float(body["guarded_budget_kcal_day"]),
        maintenance=float(body["maintenance_kcal"]),
        baseline_weight=float(body["phase_baseline_weight_kg"]),
        protein=float(body["protein_g"]), fat_anchor=float(body["fat_anchor_g"]),
        mode="runtime_fixed_day",
    )
    if not runtime.get("feasible"):
        return {
            "status": "macro_infeasible", "energy_kcal": None, "protein_g": body.get("protein_g"),
            "carb_g": None, "fat_g": None,
            "reason_codes": list(dict.fromkeys([
                *classification.get("reason_codes", []), *body.get("budget_reason_codes", []),
                *body.get("protein_reason_codes", []), *runtime.get("reason_codes", []),
            ])),
        }
    tier = DAY_TO_TIER.get(str(classification.get("day_type")), "low")
    return _macro_compat(
        runtime["daily_macros_by_tier"][tier],
        [*classification.get("reason_codes", []), *body.get("budget_reason_codes", []),
         *body.get("protein_reason_codes", []), *runtime.get("reason_codes", [])],
    )


def _infeasible(code: str, energy: float, protein: float, reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "status": "macro_infeasible",
        "energy_kcal": energy,
        "protein_g": protein,
        "carb_g": None,
        "fat_g": None,
        "reason_codes": list(dict.fromkeys([*reasons, code])),
    }


def calculate_daily_target(
    profile: Mapping[str, Any],
    training: Mapping[str, Any] | None,
    *,
    effective_date: str | None = None,
    manual_day_type: str | None = None,
) -> dict[str, Any]:
    body = calculate_body_energy(profile)
    classification = classify_training(training)
    runtime = solve_distribution(
        str(body["goal"]), REFERENCE_COUNTS, float(body["guarded_budget_kcal_day"]),
        maintenance=float(body["maintenance_kcal"]),
        baseline_weight=float(body["phase_baseline_weight_kg"]),
        protein=float(body["protein_g"]), fat_anchor=float(body["fat_anchor_g"]),
        mode="runtime_fixed_day",
    )
    recommended_tier = DAY_TO_TIER.get(str(classification.get("day_type")), "low")
    recommended_day = str(classification.get("day_type") or "暂定低碳")
    applied_tier = recommended_tier
    applied_day = recommended_day
    mode = "auto"
    if manual_day_type in {"低碳日", "中碳日", "高碳日"}:
        mode = "manual"
        applied_tier = DAY_TO_TIER[manual_day_type]
        applied_day = manual_day_type
    if runtime.get("feasible"):
        common_reasons = [
            *classification.get("reason_codes", []), *body.get("budget_reason_codes", []),
            *body.get("protein_reason_codes", []), *runtime.get("reason_codes", []),
        ]
        recommended = _macro_compat(runtime["daily_macros_by_tier"][recommended_tier], common_reasons)
        applied_reasons = [*common_reasons]
        if mode == "manual":
            applied_reasons.append("manual_day_override")
        applied = _macro_compat(runtime["daily_macros_by_tier"][applied_tier], applied_reasons)
    else:
        reasons = [
            *classification.get("reason_codes", []), *body.get("budget_reason_codes", []),
            *body.get("protein_reason_codes", []), *runtime.get("reason_codes", []),
        ]
        recommended = {"status": "macro_infeasible", "reason_codes": list(dict.fromkeys(reasons))}
        applied = recommended
    solver_context = {
        "algorithm_version": ENGINE_VERSION,
        "parameter_set_version": PARAMETER_SET_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "model_document_sha256": MODEL_DOCUMENT_SHA256,
        "solver_version": SOLVER_VERSION,
        "boundary_version": BOUNDARY_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "reference_distribution_version": REFERENCE_DISTRIBUTION_VERSION,
        "reference_counts": REFERENCE_COUNTS,
        "offsets": TIER_OFFSETS,
        "target": body["goal"],
        "phase_id": body.get("phase_id"),
        "phase_baseline_weight_kg": body["phase_baseline_weight_kg"],
        "maintenance_kcal": body["maintenance_kcal"],
        "protein_g": body["protein_g"],
        "fat_anchor_g": body["fat_anchor_g"],
    }
    return {
        "algorithm_version": ENGINE_VERSION,
        "parameter_set_version": PARAMETER_SET_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "model_document_sha256": MODEL_DOCUMENT_SHA256,
        "schema_version": SCHEMA_VERSION,
        "effective_date": effective_date,
        "mode": "runtime_fixed_day",
        "override_mode": mode,
        "solver_context": solver_context,
        "solver_context_sha256": _canonical_sha(solver_context),
        "body": body,
        "requested_speed": body["requested_speed"],
        "raw_budget_kcal_day": body["raw_budget_kcal_day"],
        "guarded_budget_kcal_day": body["guarded_budget_kcal_day"],
        "applied_budget_kcal_day": runtime.get("applied_budget_kcal_day"),
        "target_speed_applied": runtime.get("target_speed_applied"),
        "recommended_day": recommended_day,
        "recommended_demand": classification,
        "recommended_macros": recommended,
        "applied_day": applied_day,
        "applied_macros": applied,
        "runtime_distribution": runtime,
        "manual_override": mode == "manual",
    }


def solve_period_preview(profile: Mapping[str, Any], counts: Mapping[str, int]) -> dict[str, Any]:
    """Solve a complete submitted period without mutating any shown snapshot."""

    body = calculate_body_energy(profile)
    result = solve_distribution(
        str(body["goal"]), counts, float(body["guarded_budget_kcal_day"]),
        maintenance=float(body["maintenance_kcal"]),
        baseline_weight=float(body["phase_baseline_weight_kg"]),
        protein=float(body["protein_g"]), fat_anchor=float(body["fat_anchor_g"]),
        mode="period_preview_constrained",
    )
    result.update({
        "algorithm_version": ENGINE_VERSION,
        "parameter_set_version": PARAMETER_SET_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "model_document_sha256": MODEL_DOCUMENT_SHA256,
        "requested_speed": body["requested_speed"],
        "raw_budget_kcal_day": body["raw_budget_kcal_day"],
        "guarded_budget_kcal_day": body["guarded_budget_kcal_day"],
        "target": body["goal"],
    })
    return result


def project_daily_target_for_ui(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the only macro payload that ordinary UI surfaces should consume."""

    macro = snapshot.get("applied_macros") if isinstance(snapshot.get("applied_macros"), Mapping) else {}
    display = macro.get("display") if isinstance(macro.get("display"), Mapping) else {}
    demand = snapshot.get("recommended_demand") if isinstance(snapshot.get("recommended_demand"), Mapping) else {}
    if macro.get("status") != "ok":
        return {
            "ui_contract_version": UI_CONTRACT_VERSION,
            "effective_date": snapshot.get("effective_date"),
            "status": "unavailable",
            "day_label": snapshot.get("applied_day"),
            "macro_targets": None,
        }
    override_mode = str(snapshot.get("override_mode") or "auto")
    status = "manual" if override_mode == "manual" else "auto" if demand.get("formal") else "provisional"
    recommended = str(snapshot.get("recommended_day") or "")
    applied = str(snapshot.get("applied_day") or recommended)
    difference = recommended if override_mode == "manual" and recommended != applied else None
    display_energy = float(macro.get("energy_display_kcal", macro.get("energy_kcal", 0)) or 0)
    return {
        "ui_contract_version": UI_CONTRACT_VERSION,
        "effective_date": snapshot.get("effective_date"),
        "status": status,
        "day_label": applied,
        "energy_kcal": display_energy,
        "macro_targets": {
            "carb": _ui_macro(display.get("carb_g"), display.get("carb_range_g")),
            "protein": _ui_macro(display.get("protein_g"), display.get("protein_range_g")),
            "fat": _ui_macro(display.get("fat_g"), display.get("fat_range_g")),
        },
        "recommended_difference": difference,
    }


def build_manual_switch_prompt(snapshot: Mapping[str, Any], requested_day: str) -> dict[str, Any]:
    if requested_day not in {"低碳日", "中碳日", "高碳日"}:
        raise ValueError("requested_day must be a supported carb day")
    recommended = str(snapshot.get("recommended_day") or "暂定低碳")
    same_as_provisional = recommended == "暂定低碳" and requested_day == "低碳日"
    requires_confirmation = requested_day != recommended and not same_as_provisional
    if requires_confirmation and recommended == "暂定低碳":
        message = f"当前训练计划尚未确认，系统暂定低碳，是否切换为{requested_day}？"
    elif requires_confirmation:
        message = f"根据当前训练计划建议{recommended}，是否切换为{requested_day}？"
    else:
        message = None
    return {
        "requested_day": requested_day,
        "recommended_day": recommended,
        "requires_confirmation": requires_confirmation,
        "message": message,
    }


def _ui_macro(center: Any, value_range: Any) -> dict[str, float]:
    bounds = value_range if isinstance(value_range, Sequence) and not isinstance(value_range, (str, bytes)) else []
    low = _number(bounds[0]) if len(bounds) > 0 else _number(center, 0)
    high = _number(bounds[1]) if len(bounds) > 1 else _number(center, 0)
    return {
        "center_g": float(_number(center, 0) or 0),
        "min_g": float(low or 0),
        "max_g": float(high or 0),
    }


def normalize_weight_records(weights: Sequence[Mapping[str, Any]], as_of_date: date) -> dict[str, Any]:
    grouped: dict[date, list[float]] = {}
    excluded: list[dict[str, Any]] = []
    errors: list[str] = []
    for record in weights:
        measured = _parse_date(record.get("date"))
        value = _number(record.get("weight", record.get("weight_kg")))
        if measured is None or value is None:
            errors.append("input_invalid_measurement_date")
            continue
        if measured > as_of_date:
            errors.append("input_future_measurement")
            continue
        if not INPUT_LIMITS["weight_kg"][0] <= value <= INPUT_LIMITS["weight_kg"][1]:
            excluded.append({"date": measured.isoformat(), "weight": value, "reason": "input_invalid_weight"})
            continue
        grouped.setdefault(measured, []).append(value)
    duplicate_dates = sorted(day.isoformat() for day, values in grouped.items() if len(values) > 1)
    points = sorted((day, median(values)) for day, values in grouped.items())
    return {
        "points": points, "excluded_points": excluded,
        "merged_duplicate_weight_dates": duplicate_dates, "reason_codes": sorted(set(errors)),
    }


def filter_weight_outliers(points: Sequence[tuple[date, float]]) -> tuple[list[tuple[date, float]], list[dict[str, Any]]]:
    rows = list(points)
    if len(rows) < 3:
        return rows, []
    values = [value for _, value in rows]
    global_median = median(values)
    mad = median(abs(value - global_median) for value in values)
    smooth_monotonic = (
        (all(a <= b for a, b in zip(values, values[1:])) or all(a >= b for a, b in zip(values, values[1:])))
        and max(abs(a - b) for a, b in zip(values, values[1:])) <= 0.02 * global_median
    )
    threshold = max(0.05 * global_median, 6.0 * 1.4826 * mad)
    rough = set() if smooth_monotonic else {
        day for day, value in rows if abs(value - global_median) > threshold
    }
    remaining = [(day, value) for day, value in rows if day not in rough]
    excluded = [
        {"date": day.isoformat(), "weight": value, "reason": "global_median_mad"}
        for day, value in rows if day in rough
    ]
    while len(remaining) >= 3:
        flagged: set[date] = set()
        for day, value in remaining:
            nearby = sorted(
                ((abs((other_day - day).days), other_day, other_value)
                 for other_day, other_value in remaining
                 if other_day != day and abs((other_day - day).days) <= 6),
                key=lambda item: (item[0], item[1]),
            )
            neighbors = [neighbor for _, _, neighbor in nearby[:3]]
            if neighbors and abs(value / median(neighbors) - 1.0) > 0.05:
                flagged.add(day)
        if not flagged:
            break
        excluded.extend(
            {"date": day.isoformat(), "weight": value, "reason": "local_leave_one_out"}
            for day, value in remaining if day in flagged
        )
        remaining = [(day, value) for day, value in remaining if day not in flagged]
    excluded.sort(key=lambda row: (row["date"], row["weight"], row["reason"]))
    return remaining, excluded


def evaluate_baseline_refresh(
    weights: Sequence[Mapping[str, Any]],
    bodyfat_records: Sequence[Mapping[str, Any]],
    baseline_weight_kg: float,
    target: str,
    *,
    sex: str,
    height_cm: float,
    age_years: int,
    as_of_date: date,
) -> dict[str, Any]:
    normalized = normalize_weight_records(weights, as_of_date)
    if normalized["reason_codes"]:
        return {"refresh": False, "reason_codes": ["input_invalid", *normalized["reason_codes"]]}
    valid, outlier_excluded = filter_weight_outliers(normalized["points"])
    excluded = [*normalized["excluded_points"], *outlier_excluded]
    normalization_codes = ["duplicate_weight_date_merged"] if normalized["merged_duplicate_weight_dates"] else []
    seven_days = [(day, value) for day, value in valid if day >= as_of_date - timedelta(days=6)]
    twenty_eight_days = [(day, value) for day, value in valid if day >= as_of_date - timedelta(days=27)]
    early = len(seven_days) >= 4 and abs(mean(value for _, value in seven_days) / baseline_weight_kg - 1.0) >= 0.03
    regular = (
        len(twenty_eight_days) >= 12
        and (twenty_eight_days[-1][0] - twenty_eight_days[0][0]).days >= 21
    )
    if not early and not regular:
        return {
            "refresh": False, "valid_points": len(twenty_eight_days), "excluded_points": excluded,
            "merged_duplicate_weight_dates": normalized["merged_duplicate_weight_dates"],
            "reason_codes": ["baseline_refresh_deferred_insufficient_points", *normalization_codes],
        }
    chosen = seven_days if early else twenty_eight_days
    trigger = "baseline_refresh_3pct" if early else "baseline_refresh_28d"
    new_weight = mean(value for _, value in chosen)
    resolution = resolve_phase_protein(
        target, new_weight, height_cm, sex, bodyfat_records, as_of_date, age_years=age_years
    )
    if resolution.get("status") != "valid":
        return {"refresh": False, "reason_codes": list(resolution.get("reason_codes", []))}
    return {
        "refresh": True,
        "trigger": trigger,
        "window_start": chosen[0][0].isoformat(),
        "window_end": as_of_date.isoformat(),
        "valid_points": [{"date": day.isoformat(), "weight": value} for day, value in chosen],
        "excluded_points": excluded,
        "merged_duplicate_weight_dates": normalized["merged_duplicate_weight_dates"],
        "normalized_weight_points": [
            {"date": day.isoformat(), "weight": value} for day, value in normalized["points"]
        ],
        "new_baseline_weight_kg": new_weight,
        "new_protein_g": resolution["protein_g"],
        "new_ffm_kg": resolution.get("ffm_kg"),
        "new_fat_anchor_g": 0.8 * new_weight,
        "protein_route": resolution["route"],
        "protein_reason_codes": list(resolution.get("reason_codes", [])),
        "bodyfat_record_id": resolution.get("bodyfat_record_id"),
        "reuse_bodyfat": resolution["route"] == "fresh_paired_bodyfat_ffm",
        "effective_from": (as_of_date + timedelta(days=1)).isoformat(),
        "affects_past": False,
        "reason_codes": [trigger, *resolution.get("reason_codes", []), *normalization_codes],
    }


def select_calibration_window(history: Sequence[Mapping[str, Any]], as_of_date: str | date) -> dict[str, Any]:
    target = as_of_date if isinstance(as_of_date, date) else _parse_date(as_of_date)
    if target is None:
        raise ValueError("as_of_date must be an ISO date")
    prior = [(day, item) for item in history if (day := _parse_date(item.get("date"))) is not None and day < target]
    failures: list[str] = []
    for days, weight_needed, diet_needed, span_needed in CALIBRATION_WINDOWS:
        start = target - timedelta(days=days)
        rows = [(day, item) for day, item in prior if day >= start]
        observed_weights = [day for day, item in rows if item.get("weight_status") == "observed" and _number(item.get("weight_kg")) is not None]
        complete_diet = [day for day, item in rows if item.get("diet_day_status") == "complete"]
        available_span = (max((day for day, _ in rows), default=target) - min((day for day, _ in rows), default=target)).days
        goals = {str(item.get("goal")) for _, item in rows if item.get("goal")}
        phases = {str(item.get("calibration_phase_id")) for _, item in rows if item.get("calibration_phase_id")}
        latest_weight_age = (target - max(observed_weights)).days if observed_weights else days + 1
        latest_complete_diet_age = (target - max(complete_diet)).days if complete_diet else days + 1
        if (
            len(observed_weights) >= weight_needed
            and len(complete_diet) >= diet_needed
            and available_span >= span_needed
            and len(goals) <= 1
            and len(phases) <= 1
            and latest_weight_age <= 7
            and latest_complete_diet_age <= 3
        ):
            return {
                "eligible": True,
                "window_days": days,
                "observed_weight_count": len(observed_weights),
                "complete_diet_count": len(complete_diet),
                "available_span_days": available_span,
                "latest_weight_age_days": latest_weight_age,
                "latest_complete_diet_age_days": latest_complete_diet_age,
                "mode": "shadow",
            }
        failures.append(
            f"{days}d:w{len(observed_weights)}/{weight_needed},d{len(complete_diet)}/{diet_needed},"
            f"s{available_span}/{span_needed},g{len(goals)},p{len(phases)},"
            f"wf{latest_weight_age}/7,df{latest_complete_diet_age}/3"
        )
    return {"eligible": False, "window_days": None, "mode": "disabled", "reason_codes": failures}


def estimate_long_term_maintenance(
    history: Sequence[Mapping[str, Any]],
    as_of_date: str | date,
    prior_maintenance_kcal: float,
) -> dict[str, Any]:
    """Estimate current maintenance energy without changing the active target.

    The linearized energy-balance relation is used only after a window passes
    the record-completeness gate.  The returned adjustment is a bounded shadow
    candidate; applying it belongs to the snapshot/state layer so cadence and
    user-visible history remain auditable.
    """

    prior = _positive(prior_maintenance_kcal, "prior_maintenance_kcal")
    target = as_of_date if isinstance(as_of_date, date) else _parse_date(as_of_date)
    if target is None:
        raise ValueError("as_of_date must be an ISO date")
    selection = select_calibration_window(history, target)
    if not selection["eligible"]:
        return {
            **selection,
            "calibration_model_version": CALIBRATION_MODEL_VERSION,
            "application_status": "not_eligible",
        }

    window_days = int(selection["window_days"])
    start = target - timedelta(days=window_days)
    rows = [
        (day, item)
        for item in history
        if (day := _parse_date(item.get("date"))) is not None and start <= day < target
    ]
    weight_points = [
        ((day - start).days, float(weight))
        for day, item in rows
        if item.get("weight_status") == "observed"
        and (weight := _number(item.get("weight_kg"))) is not None
        and 25 <= weight <= 350
    ]
    diet_points = [
        ((day - start).days, float(energy))
        for day, item in rows
        if item.get("diet_day_status") == "complete"
        and (energy := _number(item.get("energy_intake_kcal", item.get("total_kcal")))) is not None
        and 500 <= energy <= 10000
    ]
    if len(weight_points) < 3 or not diet_points:
        return {
            **selection,
            "eligible": False,
            "calibration_model_version": CALIBRATION_MODEL_VERSION,
            "application_status": "missing_numeric_inputs",
            "reason_codes": ["complete_days_require_numeric_energy_and_observed_weight"],
        }

    regression = _linear_weight_regression(weight_points)
    if regression is None:
        return {
            **selection,
            "eligible": False,
            "calibration_model_version": CALIBRATION_MODEL_VERSION,
            "application_status": "weight_regression_failed",
            "reason_codes": ["weight_dates_have_no_usable_span"],
        }

    slope = regression["slope_kg_day"]
    intercept = regression["intercept_kg"]
    mean_intake = fmean(energy for _, energy in diet_points)
    mean_diet_day = fmean(day_index for day_index, _ in diet_points)
    fitted_mean_weight = intercept + slope * mean_diet_day
    fitted_current_weight = intercept + slope * (window_days - 1)
    observed_maintenance = (
        mean_intake
        - CALIBRATION_RHO_KCAL_PER_KG * slope
        + CALIBRATION_EPSILON_KCAL_PER_KG_DAY * (fitted_current_weight - fitted_mean_weight)
    )

    intake_sd = stdev(energy for _, energy in diet_points) if len(diet_points) > 1 else 0.0
    analytical_ci = 1.96 * sqrt(
        (CALIBRATION_RHO_KCAL_PER_KG * regression["slope_standard_error"]) ** 2
        + (intake_sd / sqrt(len(diet_points))) ** 2
        + (CALIBRATION_EPSILON_KCAL_PER_KG_DAY * regression["residual_sd_kg"]) ** 2
    )
    span_days = max(day for day, _ in weight_points) - min(day for day, _ in weight_points)
    free_living_ci_floor = 350.0 * sqrt(28.0 / len(weight_points)) * sqrt(28.0 / max(28.0, span_days))
    uncertainty_95_kcal = max(analytical_ci, free_living_ci_floor)

    _, weight_needed, diet_needed, span_needed = next(item for item in CALIBRATION_WINDOWS if item[0] == window_days)
    weight_score = min(1.0, len(weight_points) / (2.0 * weight_needed))
    diet_score = min(1.0, len(diet_points) / window_days)
    span_score = min(1.0, span_days / span_needed)
    uncertainty_score = min(1.0, max(0.0, (650.0 - uncertainty_95_kcal) / 400.0))
    quality = weight_score * diet_score * span_score * uncertainty_score
    alpha = min(0.25, quality**2)
    plausible = 800 <= observed_maintenance <= 6000 and 0.60 * prior <= observed_maintenance <= 1.60 * prior
    precise_enough = uncertainty_95_kcal <= 650 and quality >= 0.10
    if plausible and precise_enough:
        raw_change = alpha * (observed_maintenance - prior)
        change_limit = min(100.0, prior * 0.05)
        bounded_change = min(change_limit, max(-change_limit, raw_change))
        suggested = prior + bounded_change
        application_status = "shadow_candidate"
        reasons: list[str] = []
    else:
        bounded_change = 0.0
        suggested = prior
        application_status = "shadow_observe_only"
        reasons = []
        if not plausible:
            reasons.append("observed_maintenance_outside_guardrail")
        if not precise_enough:
            reasons.append("uncertainty_too_high")

    return {
        **selection,
        "calibration_model_version": CALIBRATION_MODEL_VERSION,
        "application_status": application_status,
        "prior_maintenance_kcal": prior,
        "observed_maintenance_kcal": observed_maintenance,
        "suggested_maintenance_kcal": suggested,
        "bounded_change_kcal": bounded_change,
        "alpha": alpha,
        "quality": quality,
        "uncertainty_95_kcal": uncertainty_95_kcal,
        "weight_slope_kg_day": slope,
        "fitted_current_weight_kg": fitted_current_weight,
        "mean_complete_intake_kcal": mean_intake,
        "numeric_weight_count": len(weight_points),
        "numeric_complete_diet_count": len(diet_points),
        "reason_codes": reasons,
        "mode": "shadow",
    }


def calibration_update_is_due(
    as_of_date: str | date,
    last_update_date: str | date | None,
    *,
    minimum_interval_days: int = 14,
) -> bool:
    """Return whether a previously approved calibration may update again."""

    target = as_of_date if isinstance(as_of_date, date) else _parse_date(as_of_date)
    if target is None:
        raise ValueError("as_of_date must be an ISO date")
    if last_update_date is None:
        return True
    previous = last_update_date if isinstance(last_update_date, date) else _parse_date(last_update_date)
    if previous is None:
        raise ValueError("last_update_date must be an ISO date")
    return (target - previous).days >= minimum_interval_days


def _linear_weight_regression(points: Sequence[tuple[int, float]]) -> dict[str, float] | None:
    x_mean = fmean(x for x, _ in points)
    y_mean = fmean(y for _, y in points)
    sxx = sum((x - x_mean) ** 2 for x, _ in points)
    if sxx <= 0:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / sxx
    intercept = y_mean - slope * x_mean
    residuals = [y - (intercept + slope * x) for x, y in points]
    residual_variance = sum(value**2 for value in residuals) / max(1, len(points) - 2)
    residual_sd = sqrt(residual_variance)
    return {
        "slope_kg_day": slope,
        "intercept_kg": intercept,
        "residual_sd_kg": residual_sd,
        "slope_standard_error": residual_sd / sqrt(sxx),
    }


__all__ = [
    "ACTIVITY_CATEGORIES",
    "LEGACY_ACTIVITY_FACTORS",
    "CALIBRATION_WINDOWS",
    "CALIBRATION_MODEL_VERSION",
    "DEMANDS",
    "DISPLAY_FAT_SHARE_ROUNDING_TOLERANCE",
    "ENGINE_VERSION",
    "EVIDENCE_VERSION",
    "MODEL_DOCUMENT_SHA256",
    "PARAMETER_SET_VERSION",
    "UI_CONTRACT_VERSION",
    "build_manual_switch_prompt",
    "calculate_body_energy",
    "calculate_daily_target",
    "calibration_update_is_due",
    "classify_training",
    "create_phase_baseline",
    "create_refreshed_phase",
    "evaluate_baseline_refresh",
    "estimate_long_term_maintenance",
    "project_daily_target_for_ui",
    "normalize_weight_records",
    "filter_weight_outliers",
    "resolve_phase_protein",
    "select_calibration_window",
    "solve_macros",
    "solve_distribution",
    "solve_period_preview",
    "validate_exercise_parameters",
]
