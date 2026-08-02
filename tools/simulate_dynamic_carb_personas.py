"""Run deterministic long-horizon persona replays against the reference engine."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dynamic_carb_engine import (  # noqa: E402
    calculate_body_energy,
    calculate_daily_target,
    calibration_update_is_due,
    estimate_long_term_maintenance,
    select_calibration_window,
)


START_DATE = date(2025, 1, 1)
DAYS = 365
SEED = 20260802
DEFAULT_OUTPUT = ROOT / "release_candidates" / "dynamic-carb-persona-replay-365d.json"


@dataclass(frozen=True)
class Persona:
    key: str
    label: str
    profile: dict[str, Any]
    schedule: tuple[str, ...]
    record_pattern: str
    annual_weight_change_kg: float
    manual_weekday: int | None = None
    true_maintenance_bias_kcal: float = 0.0
    reporting_bias_fraction: float = 0.0


PERSONAS = (
    Persona("male_cut_regular", "31岁男性·常规减脂抗阻", {"sex": "男", "age": 31, "height": 175, "weight": 78, "bodyfat": 20, "goal": "减脂", "activity_habit": "规律训练"}, ("res_mid", "rest", "res_mid", "rest", "res_high", "cardio_light", "rest"), "complete", -4.0, true_maintenance_bias_kcal=180),
    Persona("female_maintain_mixed", "28岁女性·维持混合训练", {"sex": "女", "age": 28, "height": 162, "weight": 58, "bodyfat": 26, "goal": "保持", "activity_habit": "规律训练"}, ("res_mid", "rest", "cardio_mid", "rest", "res_mid", "cardio_light", "rest"), "complete", 0.0, true_maintenance_bias_kcal=-120),
    Persona("male_obesity_beginner", "45岁男性·肥胖初学减脂", {"sex": "男", "age": 45, "height": 175, "weight": 112, "bodyfat": 36, "goal": "减脂", "activity_habit": "偶尔运动"}, ("res_low", "rest", "walk", "rest", "res_low", "walk", "rest"), "sparse", -8.0, true_maintenance_bias_kcal=260, reporting_bias_fraction=0.10),
    Persona("female_obesity_missing_bf", "39岁女性·肥胖且体脂缺失", {"sex": "女", "age": 39, "height": 160, "weight": 96, "goal": "减脂", "activity_habit": "偶尔运动"}, ("walk", "rest", "res_low", "rest", "walk", "rest", "rest"), "sparse", -7.0, true_maintenance_bias_kcal=150, reporting_bias_fraction=0.15),
    Persona("male_lean_gain", "22岁男性·精瘦高频增肌", {"sex": "男", "age": 22, "height": 180, "weight": 70, "bodyfat": 10, "goal": "增肌", "activity_habit": "高频训练"}, ("res_high", "res_mid", "rest", "res_high", "res_mid", "res_high", "rest"), "complete", 2.0, true_maintenance_bias_kcal=300),
    Persona("female_older_active", "55岁女性·规律力量与步行", {"sex": "女", "age": 55, "height": 158, "weight": 62, "bodyfat": 31, "goal": "保持", "activity_habit": "规律训练"}, ("res_mid", "rest", "walk", "rest", "res_mid", "walk", "rest"), "weekly_weight", 0.0, true_maintenance_bias_kcal=-100),
    Persona("male_senior", "67岁男性·老年维持训练", {"sex": "男", "age": 67, "height": 170, "weight": 74, "bodyfat": 23, "goal": "保持", "activity_habit": "规律训练"}, ("res_low", "rest", "walk", "rest", "res_low", "rest", "rest"), "weekly_weight", -0.5, true_maintenance_bias_kcal=-180),
    Persona("female_runner", "33岁女性·耐力跑者", {"sex": "女", "age": 33, "height": 165, "weight": 54, "bodyfat": 20, "goal": "保持", "activity_habit": "高频训练"}, ("cardio_high", "cardio_light", "rest", "cardio_mid", "rest", "endurance_long", "rest"), "complete", 0.0, true_maintenance_bias_kcal=250),
    Persona("male_mixed_double", "36岁男性·混合与同日双练", {"sex": "男", "age": 36, "height": 178, "weight": 86, "bodyfat": 17, "goal": "保持", "activity_habit": "高频训练"}, ("mixed", "rest", "res_high", "rest", "double", "cardio_light", "rest"), "complete", 0.0, true_maintenance_bias_kcal=220),
    Persona("male_bodyweight_only", "30岁男性·纯自重训练", {"sex": "男", "age": 30, "height": 172, "weight": 68, "bodyfat": 16, "goal": "保持", "activity_habit": "规律训练"}, ("bodyweight", "rest", "bodyweight", "rest", "bodyweight_high", "rest", "rest"), "training_only", 0.0),
    Persona("female_diet_only", "41岁女性·主要记录饮食", {"sex": "女", "age": 41, "height": 164, "weight": 72, "bodyfat": 34, "goal": "减脂", "activity_habit": "久坐少动"}, ("unknown",) * 7, "diet_only", -4.5, true_maintenance_bias_kcal=-200, reporting_bias_fraction=0.08),
    Persona("male_manual_override", "29岁男性·经常手动切碳档", {"sex": "男", "age": 29, "height": 177, "weight": 81, "bodyfat": 19, "goal": "减脂", "activity_habit": "规律训练"}, ("res_mid", "rest", "res_mid", "rest", "res_high", "rest", "rest"), "chaotic", -3.0, manual_weekday=4, true_maintenance_bias_kcal=100, reporting_bias_fraction=0.05),
)


def training_facts(kind: str) -> dict[str, Any]:
    if kind == "rest":
        return {"status": "explicit_rest"}
    if kind == "unknown":
        return {"status": "unknown"}
    templates = {
        "res_low": {"status": "completed", "resistance": {"work_sets_total": 8, "peak_primary_muscle_sets": 5, "duration_min": 40}},
        "res_mid": {"status": "completed", "resistance": {"work_sets_total": 14, "peak_primary_muscle_sets": 8, "duration_min": 60}},
        "res_high": {"status": "completed", "resistance": {"work_sets_total": 22, "peak_primary_muscle_sets": 11, "duration_min": 85}},
        "bodyweight": {"status": "completed", "resistance": {"work_sets_total": 12, "peak_primary_muscle_sets": 7, "duration_min": 50, "load_kind": "bodyweight"}},
        "bodyweight_high": {"status": "completed", "resistance": {"work_sets_total": 20, "peak_primary_muscle_sets": 10, "duration_min": 75, "load_kind": "bodyweight"}},
        "walk": {"status": "completed", "cardio": {"duration_min": 40, "intensity": "low"}},
        "cardio_light": {"status": "completed", "cardio": {"duration_min": 35, "intensity": "moderate"}},
        "cardio_mid": {"status": "completed", "cardio": {"duration_min": 60, "intensity": "moderate"}},
        "cardio_high": {"status": "completed", "cardio": {"duration_min": 90, "intensity": "high"}},
        "endurance_long": {"status": "completed", "cardio": {"duration_min": 150, "intensity": "moderate"}},
        "mixed": {"status": "completed", "resistance": {"work_sets_total": 14, "peak_primary_muscle_sets": 8, "duration_min": 60}, "cardio": {"duration_min": 50, "intensity": "moderate"}, "sessions": 1},
        "double": {"status": "completed", "resistance": {"work_sets_total": 14, "peak_primary_muscle_sets": 8, "duration_min": 60}, "cardio": {"duration_min": 60, "intensity": "moderate"}, "sessions": 2},
    }
    return json.loads(json.dumps(templates[kind]))


def _record_flags(pattern: str, index: int) -> tuple[str, str]:
    if pattern == "complete":
        return "observed", "complete"
    if pattern == "sparse":
        return ("observed" if index % 3 == 0 else "carried", "complete" if index % 5 else "partial")
    if pattern == "weekly_weight":
        return ("observed" if index % 7 == 0 else "carried", "complete" if index % 4 else "partial")
    if pattern == "training_only":
        return ("observed" if index % 3 == 0 else "carried", "unknown")
    if pattern == "diet_only":
        return ("observed" if index % 3 == 0 else "carried", "complete")
    return ("observed" if index % 4 == 0 else "carried", "complete" if index % 3 else "unknown")


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def simulate_persona(persona: Persona, days: int = DAYS, replicate: int = 0) -> dict[str, Any]:
    rng = random.Random(f"{SEED}:{persona.key}:{replicate}")
    history: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    start_weight = float(persona.profile["weight"])
    formula_prior = float(calculate_body_energy(persona.profile)["maintenance_kcal"])
    true_maintenance_at_start = formula_prior + persona.true_maintenance_bias_kcal
    truth_rho = rng.uniform(7200.0, 9400.0)
    truth_epsilon = rng.uniform(18.0, 30.0)
    target_daily_balance = persona.annual_weight_change_kg * truth_rho / max(1, days - 1)
    tissue_weight = start_weight
    water_weight = 0.0
    simulated_applied_maintenance = formula_prior
    last_simulated_update: date | None = None
    day_types: Counter[str] = Counter()
    demand_types: Counter[str] = Counter()
    reason_codes: Counter[str] = Counter()
    calibration_windows: Counter[str] = Counter()
    calibration_statuses: Counter[str] = Counter()
    raw_calibration_errors: list[float] = []
    suggested_calibration_errors: list[float] = []
    first_candidate_day: int | None = None
    simulated_updates = 0
    violations: list[str] = []

    last_observed_weight = start_weight
    last_bodyfat = persona.profile.get("bodyfat")
    bodyfat_observed_index = 0
    for index in range(days):
        current = START_DATE + timedelta(days=index)
        activity_drift = 45.0 * math.sin(index * 2 * math.pi / 120.0)
        true_maintenance = (
            true_maintenance_at_start
            + truth_epsilon * (tissue_weight - start_weight)
            + activity_drift
        )
        actual_intake = true_maintenance + target_daily_balance + rng.gauss(0.0, 230.0)
        daily_energy_density = truth_rho * (1.0 + 0.06 * math.sin(index * 2 * math.pi / 73.0))
        tissue_weight += (actual_intake - true_maintenance) / daily_energy_density
        water_weight = 0.78 * water_weight + rng.gauss(0.0, 0.16) + 0.00025 * (actual_intake - true_maintenance)
        true_weight = tissue_weight + water_weight
        weight_status, diet_status = _record_flags(persona.record_pattern, index)
        if persona.record_pattern == "chaotic" and actual_intake > true_maintenance + 180 and rng.random() < 0.55:
            diet_status = "unknown"
        if weight_status == "observed":
            last_observed_weight = true_weight
        if last_bodyfat is not None and index % 30 == 0:
            bodyfat_observed_index = index

        profile = dict(persona.profile)
        profile["weight"] = round(last_observed_weight, 2)
        if last_bodyfat is not None:
            profile["bodyfat_status"] = "observed" if index == bodyfat_observed_index else "carried"
            profile["bodyfat_age_days"] = index - bodyfat_observed_index
        kind = persona.schedule[current.weekday()]
        training = training_facts(kind)
        manual = "高碳日" if persona.manual_weekday == current.weekday() else None
        result = calculate_daily_target(profile, training, effective_date=current.isoformat(), manual_day_type=manual)
        outputs.append(result)
        day_types[str(result["recommended_day"])] += 1
        demand_types[str(result["recommended_demand"]["demand_key"])] += 1
        macro = result["recommended_macros"]
        reason_codes.update(macro.get("reason_codes", []))
        if macro["status"] != "ok":
            violations.append(f"{current}:macro_infeasible")
        else:
            if not 0.20 - 1e-9 <= macro["fat_energy_share"] <= 0.35 + 1e-9:
                violations.append(f"{current}:fat_share")
            if abs(macro["energy_closure_error"]) > 1e-6:
                violations.append(f"{current}:energy_closure")
            if min(macro["protein_g"], macro["carb_g"], macro["fat_g"]) < 0:
                violations.append(f"{current}:negative_macro")

        reported_intake = None
        if diet_status == "complete":
            reported_intake = actual_intake * (1.0 - persona.reporting_bias_fraction) + rng.gauss(0.0, 45.0)
        history.append({
            "date": current.isoformat(),
            "weight_status": weight_status,
            "weight_kg": round(true_weight, 2) if weight_status == "observed" else None,
            "diet_day_status": diet_status,
            "energy_intake_kcal": round(reported_intake) if reported_intake is not None else None,
            "goal": persona.profile["goal"],
        })
        next_day = current + timedelta(days=1)
        eligibility = select_calibration_window(history, next_day)
        calibration_windows[str(eligibility.get("window_days") or "disabled")] += 1
        calibration = estimate_long_term_maintenance(history, next_day, simulated_applied_maintenance)
        status = str(calibration["application_status"])
        calibration_statuses[status] += 1
        if status == "shadow_candidate":
            if first_candidate_day is None:
                first_candidate_day = index + 1
            raw_calibration_errors.append(abs(float(calibration["observed_maintenance_kcal"]) - true_maintenance))
            suggested_calibration_errors.append(abs(float(calibration["suggested_maintenance_kcal"]) - true_maintenance))
            if calibration_update_is_due(next_day, last_simulated_update):
                simulated_applied_maintenance = float(calibration["suggested_maintenance_kcal"])
                last_simulated_update = next_day
                simulated_updates += 1

    carbs = [item["recommended_macros"]["carb_g"] for item in outputs if item["recommended_macros"]["status"] == "ok"]
    calories = [item["recommended_macros"]["energy_kcal"] for item in outputs if item["recommended_macros"]["status"] == "ok"]
    return {
        "persona": persona.key if replicate == 0 else f"{persona.key}#{replicate + 1}",
        "base_persona": persona.key,
        "replicate": replicate,
        "label": persona.label,
        "days": days,
        "day_types": dict(day_types),
        "demand_types": dict(demand_types),
        "calibration_windows": dict(calibration_windows),
        "calibration": {
            "statuses": dict(calibration_statuses),
            "first_candidate_day": first_candidate_day,
            "simulated_updates": simulated_updates,
            "formula_prior_kcal": round(formula_prior),
            "true_maintenance_at_start_kcal": round(true_maintenance_at_start),
            "final_simulated_maintenance_kcal": round(simulated_applied_maintenance),
            "initial_prior_error_kcal": round(abs(formula_prior - true_maintenance_at_start)),
            "final_simulated_error_kcal": round(abs(simulated_applied_maintenance - true_maintenance)),
            "raw_candidate_median_error_kcal": round(_percentile(raw_calibration_errors, 0.50) or 0),
            "raw_candidate_p90_error_kcal": round(_percentile(raw_calibration_errors, 0.90) or 0),
            "suggested_median_error_kcal": round(_percentile(suggested_calibration_errors, 0.50) or 0),
            "reporting_bias_fraction": persona.reporting_bias_fraction,
            "truth_model": {
                "rho_kcal_per_kg": round(truth_rho),
                "epsilon_kcal_per_kg_day": round(truth_epsilon, 1),
                "water_noise": True,
                "activity_drift": True,
            },
        },
        "reason_codes": dict(reason_codes),
        "carb_g_range": [round(min(carbs), 1), round(max(carbs), 1)] if carbs else None,
        "energy_kcal_range": [round(min(calories)), round(max(calories))] if calories else None,
        "violations": violations,
    }


def run_replay(days: int = DAYS, replicates: int = 1) -> dict[str, Any]:
    if replicates < 1:
        raise ValueError("replicates must be positive")
    personas = [simulate_persona(persona, days, replicate) for replicate in range(replicates) for persona in PERSONAS]
    violations = sum(len(item["violations"]) for item in personas)
    eligible = [item for item in personas if item["calibration"]["simulated_updates"] > 0]
    reliable = [item for item in eligible if item["calibration"]["reporting_bias_fraction"] == 0]
    biased = [item for item in eligible if item["calibration"]["reporting_bias_fraction"] > 0]
    return {
        "schema": "dynamic_carb_persona_replay_summary",
        "generated_with_seed": SEED,
        "start_date": START_DATE.isoformat(),
        "days_per_persona": days,
        "replicates_per_persona": replicates,
        "persona_count": len(personas),
        "total_person_days": days * len(personas),
        "total_violations": violations,
        "calibration_summary": {
            "eligible_personas": len(eligible),
            "disabled_personas": len(personas) - len(eligible),
            "reliable_logging_personas": len(reliable),
            "reliable_logging_improved": sum(
                item["calibration"]["final_simulated_error_kcal"] < item["calibration"]["initial_prior_error_kcal"]
                for item in reliable
            ),
            "biased_logging_personas": len(biased),
            "biased_logging_worsened": sum(
                item["calibration"]["final_simulated_error_kcal"] > item["calibration"]["initial_prior_error_kcal"]
                for item in biased
            ),
            "product_mode": "shadow_only",
            "auto_apply_gate": "blocked_until_real_backup_replay",
        },
        "personas": personas,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=DAYS)
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run_replay(args.days, args.replicates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("persona_count", "days_per_persona", "total_person_days", "total_violations")}, ensure_ascii=False))
    return 1 if report["total_violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
