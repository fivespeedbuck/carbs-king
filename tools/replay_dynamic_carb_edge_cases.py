"""Replay the non-negotiable dynamic-carb edge cases as a compact gate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dynamic_carb_engine import (  # noqa: E402
    build_manual_switch_prompt,
    calculate_body_energy,
    calculate_daily_target,
    classify_training,
    estimate_long_term_maintenance,
    project_daily_target_for_ui,
    select_calibration_window,
    validate_exercise_parameters,
)


DEFAULT_OUTPUT = ROOT / "release_candidates" / "dynamic-carb-edge-case-replay.json"
BASE_PROFILE = {
    "sex": "男", "age": 31, "height": 175, "weight": 78,
    "bodyfat": 20, "goal": "减脂", "activity_habit": "规律训练",
}


def _case(name: str, check: Callable[[], bool]) -> dict[str, Any]:
    try:
        passed = bool(check())
        return {"case": name, "passed": passed, "error": None if passed else "condition_false"}
    except Exception as error:  # replay report must retain the failing case
        return {"case": name, "passed": False, "error": f"{type(error).__name__}:{error}"}


def _history(days: int, *, weight_every: int = 1, diet_status: str = "complete") -> list[dict[str, Any]]:
    start = date(2025, 1, 1)
    return [{
        "date": (start + timedelta(days=index)).isoformat(),
        "weight_status": "observed" if index % weight_every == 0 else "carried",
        "weight_kg": 80 - index * 0.01 if index % weight_every == 0 else None,
        "diet_day_status": diet_status,
        "energy_intake_kcal": 2300 if diet_status == "complete" else None,
        "goal": "减脂",
    } for index in range(days)]


def run_edge_replay() -> dict[str, Any]:
    start = date(2025, 1, 1)

    cases = [
        _case("unknown_is_not_rest", lambda: not classify_training({"status": "unknown"})["formal"]),
        _case("explicit_rest_is_formal_low", lambda: classify_training({"status": "explicit_rest"})["day_type"] == "低碳日"),
        _case("unknown_zero_load_is_not_bodyweight", lambda: not validate_exercise_parameters({
            "recording_mode": "strength", "parameters_confirmed": True,
            "sets": [{"reps": 12, "weight_kg": 0}],
        })["ready"]),
        _case("explicit_bodyweight_is_ready", lambda: validate_exercise_parameters({
            "recording_mode": "strength", "parameters_confirmed": True, "load_kind": "bodyweight",
            "sets": [{"reps": 12}],
        })["ready"]),
        _case("valid_defaults_can_use_one_click_confirmation", lambda: validate_exercise_parameters({
            "recording_mode": "strength", "parameters_confirmed": False, "load_kind": "external",
            "sets": [{"reps": 10, "weight_kg": 0}],
        }, require_confirmation=False)["ready"]),
        _case("partial_diet_never_calibrates", lambda: not select_calibration_window(
            _history(100, diet_status="partial"), start + timedelta(days=100)
        )["eligible"]),
        _case("sparse_records_fall_back_to_60_days", lambda: select_calibration_window(
            _history(61, weight_every=3), start + timedelta(days=61)
        ).get("window_days") == 60),
        _case("weekly_weight_is_insufficient_for_auto_calibration", lambda: not select_calibration_window(
            _history(120, weight_every=7), start + timedelta(days=120)
        )["eligible"]),
        _case("future_rows_never_unlock_past_window", lambda: not select_calibration_window(
            [*_history(10), *[
                {**item, "date": (start + timedelta(days=100 + index)).isoformat()}
                for index, item in enumerate(_history(100))
            ]], start + timedelta(days=10)
        )["eligible"]),
        _case("stale_bodyfat_is_not_treated_as_observed_ffm", lambda: "janmahasatian" in calculate_body_energy({
            "sex": "女", "age": 39, "height": 160, "weight": 96, "bodyfat": 35,
            "bodyfat_status": "carried", "bodyfat_age_days": 120,
            "goal": "减脂", "activity_habit": "偶尔运动",
        })["protein_method"]),
        _case("second_session_upgrades_medium_resistance", lambda: classify_training({
            "status": "completed", "sessions": 2,
            "resistance": {"work_sets_total": 14, "peak_primary_muscle_sets": 8, "duration_min": 60},
        })["demand_key"] == "mixed_high"),
        _case("added_cardio_combines_without_double_counting", lambda: classify_training({
            "status": "completed", "sessions": 1,
            "resistance": {"work_sets_total": 14, "peak_primary_muscle_sets": 8, "duration_min": 60},
            "cardio": {"duration_min": 60, "intensity": "moderate"},
        })["demand_key"] == "mixed_high"),
        _case("ordinary_resistance_never_exceeds_maintenance", lambda: (
            lambda result: result["recommended_macros"]["energy_kcal"] <= result["body"]["maintenance_kcal"] + 1e-9
        )(calculate_daily_target(BASE_PROFILE, {
            "status": "completed", "resistance": {"work_sets_total": 25, "peak_primary_muscle_sets": 12, "duration_min": 90},
        }))),
        _case("long_endurance_can_use_bounded_performance_energy", lambda: (
            lambda result: result["body"]["maintenance_kcal"] < result["recommended_macros"]["energy_kcal"]
            <= result["body"]["maintenance_kcal"] + 500
        )(calculate_daily_target({
            "sex": "女", "age": 33, "height": 165, "weight": 54, "bodyfat": 20,
            "goal": "减脂", "activity_habit": "高频训练", "performance_extra_kcal": 500,
        }, {"status": "completed", "cardio": {"duration_min": 150, "intensity": "moderate"}}))),
        _case("manual_override_keeps_recommendation_separate", lambda: (
            lambda result: result["recommended_day"] == "低碳日" and result["applied_day"] == "高碳日"
        )(calculate_daily_target(BASE_PROFILE, {"status": "explicit_rest"}, manual_day_type="高碳日"))),
        _case("manual_difference_requires_one_prompt", lambda: build_manual_switch_prompt(
            calculate_daily_target(BASE_PROFILE, {"status": "explicit_rest"}), "高碳日"
        )["requires_confirmation"]),
        _case("ordinary_ui_receives_no_internal_formula", lambda: "reason_codes" not in json.dumps(
            project_daily_target_for_ui(calculate_daily_target(BASE_PROFILE, {"status": "explicit_rest"})),
            ensure_ascii=False,
        )),
        _case("training_only_data_does_not_invent_energy_calibration", lambda: estimate_long_term_maintenance(
            [{**item, "diet_day_status": "unknown", "energy_intake_kcal": None} for item in _history(100)],
            start + timedelta(days=100), 2500,
        )["application_status"] == "not_eligible"),
    ]
    failures = [item for item in cases if not item["passed"]]
    return {
        "schema": "dynamic_carb_edge_case_replay",
        "case_count": len(cases),
        "passed_count": len(cases) - len(failures),
        "failure_count": len(failures),
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run_edge_replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("case_count", "passed_count", "failure_count")}, ensure_ascii=False))
    return 1 if report["failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
