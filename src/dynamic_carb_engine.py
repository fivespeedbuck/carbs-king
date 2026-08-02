"""Deterministic reference engine for the dynamic carb-cycle design.

The module consumes normalized facts.  App JSON/session migration belongs in an
adapter so replay tools and the UI share one calculation path.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite, sqrt
from statistics import fmean, stdev
from typing import Any, Mapping, Sequence


ENGINE_VERSION = "CK-DCE-v1-reference"
PARAMETER_SET_VERSION = "CK-DCE-params-2026-08-02-c"
EVIDENCE_VERSION = "2026-08-02"
SCHEMA_VERSION = 1
UI_CONTRACT_VERSION = 1
CALIBRATION_MODEL_VERSION = "hall-linearized-2011-v1"
CALIBRATION_RHO_KCAL_PER_KG = 9100.0
CALIBRATION_EPSILON_KCAL_PER_KG_DAY = 22.0

ACTIVITY_FACTORS = {
    "久坐少动": 1.25,
    "偶尔运动": 1.35,
    "规律训练": 1.45,
    "高频训练": 1.60,
    "sedentary": 1.25,
    "light": 1.35,
    "regular": 1.45,
    "high": 1.60,
}
GOALS = {"减脂": "cut", "保持": "maintain", "增肌": "gain", "cut": "cut", "maintain": "maintain", "gain": "gain"}
SEXES = {"男": "male", "女": "female", "male": "male", "female": "female"}

DEMANDS: dict[str, dict[str, float | str]] = {
    "provisional_low": {"low": 2.0, "center": 2.5, "high": 3.0, "day_type": "暂定低碳"},
    "rest": {"low": 2.0, "center": 2.5, "high": 3.0, "day_type": "低碳日"},
    "resistance_low": {"low": 2.0, "center": 2.5, "high": 3.0, "day_type": "低碳日"},
    "resistance_medium": {"low": 3.0, "center": 3.5, "high": 4.0, "day_type": "中碳日"},
    "resistance_high": {"low": 4.0, "center": 4.5, "high": 5.0, "day_type": "高碳日"},
    "cardio_light": {"low": 2.0, "center": 2.5, "high": 3.0, "day_type": "低碳日"},
    "cardio_moderate": {"low": 3.0, "center": 4.0, "high": 5.0, "day_type": "中碳日"},
    "cardio_high": {"low": 5.0, "center": 6.0, "high": 7.0, "day_type": "高碳日"},
    "endurance_long": {"low": 6.0, "center": 8.0, "high": 10.0, "day_type": "高碳日"},
    "endurance_extreme": {"low": 8.0, "center": 10.0, "high": 12.0, "day_type": "高碳日"},
    "mixed_high": {"low": 4.0, "center": 5.0, "high": 6.0, "day_type": "高碳日"},
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


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


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
    sessions = max(1, int(_number(facts.get("sessions"), 1) or 1))
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
        if (resistance_medium and cardio_medium) or sessions >= 2:
            selected = "mixed_high"
            reasons.append("combined_training_upgrade")
        else:
            selected = max((resistance_key, cardio_key), key=lambda key: float(DEMANDS[key]["center"]))
    else:
        selected = resistance_key or cardio_key or "provisional_low"

    if sessions >= 2 and selected in {"resistance_medium", "resistance_high", "cardio_moderate", "cardio_high"}:
        selected = "mixed_high"
        reasons.append("multiple_sessions_upgrade")
    if bool(facts.get("close_second_high_glycogen_session")):
        selected = "mixed_high"
        reasons.append("close_second_session_upgrade")
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
        "gkg_low": float(demand["low"]),
        "gkg_center": float(demand["center"]),
        "gkg_high": float(demand["high"]),
        "reason_codes": list(reasons),
    }


def _classify_resistance(facts: Mapping[str, Any]) -> str | None:
    total = max(0, int(_number(facts.get("work_sets_total"), 0) or 0))
    peak = max(0, int(_number(facts.get("peak_primary_muscle_sets"), 0) or 0))
    duration = _number(facts.get("duration_min"))
    if total <= 0:
        return None
    if total >= 20 or peak >= 10 or (duration is not None and duration >= 75):
        return "resistance_high"
    duration_low = duration is None or duration < 45
    if total < 10 and peak < 6 and duration_low:
        return "resistance_low"
    return "resistance_medium"


def _classify_cardio(facts: Mapping[str, Any]) -> str | None:
    duration = _number(facts.get("duration_min"))
    if duration is None or duration <= 0:
        return None
    intensity = str(facts.get("intensity") or "moderate")
    factor = {"low": 0.65, "moderate": 1.0, "high": 1.25}.get(intensity, 1.0)
    effective = duration * factor
    if duration >= 240 and intensity in {"moderate", "high"}:
        return "endurance_extreme"
    if duration >= 120 and effective >= 120:
        return "endurance_long"
    if effective >= 90:
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
    if sex is None or goal is None or not 120 <= height <= 230 or not 18 <= age <= 90:
        raise ValueError("profile sex, goal, height or age is outside the supported adult range")

    rmr = 10 * weight + 6.25 * height - 5 * age + (5 if sex == "male" else -161)
    maintenance_override = _number(profile.get("maintenance_kcal"))
    if maintenance_override is not None and maintenance_override > 0:
        maintenance = maintenance_override
        energy_method = "maintenance_override"
    else:
        activity_factor = _number(profile.get("activity_factor"))
        if activity_factor is None:
            activity_factor = ACTIVITY_FACTORS.get(str(profile.get("activity_habit") or ""))
        if activity_factor is None or not 1.1 <= activity_factor <= 2.2:
            raise ValueError("activity factor is missing or invalid")
        maintenance = rmr * activity_factor
        energy_method = "mifflin_pal_total"

    explicit_goal_energy = _number(profile.get("goal_energy_kcal"))
    if explicit_goal_energy is not None and explicit_goal_energy > 0:
        goal_energy = explicit_goal_energy
        goal_energy_method = "explicit"
    elif goal == "cut":
        deficit_fraction = _number(profile.get("deficit_fraction"), 0.15) or 0.15
        deficit = min(500.0, maintenance * min(0.25, max(0.05, deficit_fraction)))
        goal_energy = maintenance - deficit
        goal_energy_method = "default_cut"
    elif goal == "gain":
        surplus_fraction = _number(profile.get("surplus_fraction"), 0.075) or 0.075
        goal_energy = maintenance * (1 + min(0.15, max(0.025, surplus_fraction)))
        goal_energy_method = "default_gain"
    else:
        goal_energy = maintenance
        goal_energy_method = "maintenance"

    protein, protein_method, lean_mass = _protein_anchor(profile, weight, height, age, goal)
    return {
        "weight_kg": weight,
        "height_cm": height,
        "age_years": age,
        "sex": sex,
        "goal": goal,
        "rmr_kcal": rmr,
        "maintenance_kcal": maintenance,
        "goal_energy_kcal": goal_energy,
        "protein_g": protein,
        "lean_mass_kg": lean_mass,
        "energy_method": energy_method,
        "goal_energy_method": goal_energy_method,
        "protein_method": protein_method,
        "performance_extra_kcal": max(0.0, _number(profile.get("performance_extra_kcal"), 0) or 0),
    }


def _protein_anchor(
    profile: Mapping[str, Any], weight: float, height: float, age: float, goal: str
) -> tuple[float, str, float | None]:
    explicit = _number(profile.get("protein_target_g"))
    if explicit is not None and explicit > 0:
        return explicit, "explicit", None
    bodyfat = _number(profile.get("bodyfat_percent", profile.get("bodyfat")))
    bodyfat_status = str(profile.get("bodyfat_status") or ("observed" if bodyfat is not None else "unknown"))
    bodyfat_age = _number(profile.get("bodyfat_age_days"), 0) or 0
    if bodyfat is not None and 3 <= bodyfat <= 60 and bodyfat_status in {"observed", "carried"} and bodyfat_age <= 90:
        lean_mass = weight * (1 - bodyfat / 100)
        factor = 2.3 if goal == "cut" else 2.0
        protein = lean_mass * factor
        if age >= 65:
            protein = max(protein, weight * 1.4)
        return protein, f"ffm_{factor:g}gkg", lean_mass

    bmi = weight / (height / 100) ** 2
    if bmi >= 30:
        if SEXES.get(str(profile.get("sex") or "")) == "male":
            lean_mass = 9270 * weight / (6680 + 216 * bmi)
        else:
            lean_mass = 9270 * weight / (8780 + 244 * bmi)
        factor = 2.3 if goal == "cut" else 2.0
        return lean_mass * factor, f"janmahasatian_ffm_estimate_{factor:g}gkg", lean_mass
    factor = 1.8 if goal == "cut" else 1.6
    protein = weight * factor
    if age >= 65:
        protein = max(protein, weight * 1.4)
    return protein, f"actual_weight_{factor:g}gkg", None


def solve_macros(body: Mapping[str, Any], classification: Mapping[str, Any]) -> dict[str, Any]:
    weight = float(body["weight_kg"])
    protein = float(body["protein_g"])
    maintenance = float(body["maintenance_kcal"])
    energy = float(body["goal_energy_kcal"])
    demand_low = weight * float(classification["gkg_low"])
    demand_center = weight * float(classification["gkg_center"])
    demand_high = weight * float(classification["gkg_high"])
    reasons = list(classification.get("reason_codes", []))

    feasible = _carb_energy_range(energy, protein)
    if feasible is None:
        return _infeasible("protein_energy_conflict", energy, protein, reasons)
    energy_min_carb, energy_max_carb = feasible
    training_demand = classification["demand_key"] not in {"rest", "provisional_low", "resistance_low"}
    if training_demand and demand_low > energy_max_carb and energy < maintenance:
        needed = (4 * protein + 4 * demand_low) / 0.80
        raised = min(maintenance, max(energy, needed))
        if raised > energy + 0.5:
            energy = raised
            reasons.append("training_day_deficit_reduced")
            feasible = _carb_energy_range(energy, protein)
            if feasible is None:
                return _infeasible("protein_energy_conflict", energy, protein, reasons)
            energy_min_carb, energy_max_carb = feasible

    if classification["demand_key"] in {"endurance_long", "endurance_extreme"} and demand_low > energy_max_carb:
        extra_cap = max(0.0, _number(body.get("performance_extra_kcal"), 0) or 0)
        needed = (4 * protein + 4 * demand_low) / 0.80
        raised = min(max(energy, needed), maintenance + extra_cap)
        if raised > energy + 0.5:
            energy = raised
            reasons.append("performance_energy_exception")
            feasible = _carb_energy_range(energy, protein)
            if feasible is None:
                return _infeasible("protein_energy_conflict", energy, protein, reasons)
            energy_min_carb, energy_max_carb = feasible

    carb = min(energy_max_carb, max(energy_min_carb, demand_center))
    if carb > demand_center + 0.1:
        reasons.append("carb_raised_to_energy_floor")
    if carb < demand_center - 0.1:
        reasons.append("carb_clamped_to_energy_ceiling")
    fat = (energy - 4 * protein - 4 * carb) / 9
    if min(carb, fat, protein) < 0:
        return _infeasible("negative_macro", energy, protein, reasons)

    intersection_low = max(demand_low, energy_min_carb)
    intersection_high = min(demand_high, energy_max_carb)
    span = max(10.0, carb * 0.05)
    if intersection_low <= intersection_high:
        range_low = max(intersection_low, carb - span)
        range_high = min(intersection_high, carb + span)
    else:
        range_low = range_high = carb
        reasons.append("demand_energy_intervals_do_not_overlap")
    display_center = min(_floor5(energy_max_carb), max(_ceil5(energy_min_carb), _round5(carb)))
    display_low = _ceil5(range_low)
    display_high = _floor5(range_high)
    if display_low > display_high:
        display_low = display_high = display_center
    display_center = min(display_high, max(display_low, display_center))
    fat_at_low_carb = (energy - 4 * protein - 4 * range_low) / 9
    fat_at_high_carb = (energy - 4 * protein - 4 * range_high) / 9
    protein_span = max(5.0, protein * 0.05)
    display_fat_low = _ceil5(fat_at_high_carb)
    display_fat_high = _floor5(fat_at_low_carb)
    if display_fat_low > display_fat_high:
        display_fat_low = display_fat_high = _round5(fat)

    return {
        "status": "ok",
        "energy_kcal": energy,
        "protein_g": protein,
        "carb_g": carb,
        "fat_g": fat,
        "carb_range_g": [range_low, range_high],
        "fat_range_g": [fat_at_high_carb, fat_at_low_carb],
        "display": {
            "protein_g": _round5(protein),
            "protein_range_g": [_ceil5(max(0.0, protein - protein_span)), _floor5(protein + protein_span)],
            "carb_g": display_center,
            "carb_range_g": [display_low, display_high],
            "fat_g": _round5(fat),
            "fat_range_g": [display_fat_low, display_fat_high],
        },
        "fat_energy_share": fat * 9 / energy,
        "energy_closure_error": protein * 4 + carb * 4 + fat * 9 - energy,
        "demand_interval_g": [demand_low, demand_high],
        "energy_carb_interval_g": [energy_min_carb, energy_max_carb],
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def _carb_energy_range(energy: float, protein: float) -> tuple[float, float] | None:
    if energy <= 0 or protein <= 0:
        return None
    low = (energy - 4 * protein - 0.35 * energy) / 4
    high = (energy - 4 * protein - 0.20 * energy) / 4
    if high < 0 or low > high:
        return None
    return max(0.0, low), high


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
    recommended = solve_macros(body, classification)
    applied_classification = classification
    mode = "auto"
    if manual_day_type in {"低碳日", "中碳日", "高碳日"}:
        key = {"低碳日": "rest", "中碳日": "resistance_medium", "高碳日": "resistance_high"}[manual_day_type]
        applied_classification = _classification(key, formal=True, sample=False, reasons=["manual_day_override"])
        mode = "manual"
    applied = recommended if mode == "auto" else solve_macros(body, applied_classification)
    return {
        "algorithm_version": ENGINE_VERSION,
        "parameter_set_version": PARAMETER_SET_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "effective_date": effective_date,
        "body": body,
        "recommended_day": classification["day_type"],
        "recommended_demand": classification,
        "recommended_macros": recommended,
        "applied_day": applied_classification["day_type"],
        "applied_macros": applied,
        "mode": mode,
    }


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
    mode = str(snapshot.get("mode") or "auto")
    status = "manual" if mode == "manual" else "auto" if demand.get("formal") else "provisional"
    recommended = str(snapshot.get("recommended_day") or "")
    applied = str(snapshot.get("applied_day") or recommended)
    difference = recommended if mode == "manual" and recommended != applied else None
    return {
        "ui_contract_version": UI_CONTRACT_VERSION,
        "effective_date": snapshot.get("effective_date"),
        "status": status,
        "day_label": applied,
        "energy_kcal": round(float(macro["energy_kcal"])),
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
    "ACTIVITY_FACTORS",
    "CALIBRATION_WINDOWS",
    "CALIBRATION_MODEL_VERSION",
    "DEMANDS",
    "ENGINE_VERSION",
    "PARAMETER_SET_VERSION",
    "UI_CONTRACT_VERSION",
    "build_manual_switch_prompt",
    "calculate_body_energy",
    "calculate_daily_target",
    "calibration_update_is_due",
    "classify_training",
    "estimate_long_term_maintenance",
    "project_daily_target_for_ui",
    "select_calibration_window",
    "solve_macros",
    "validate_exercise_parameters",
]
