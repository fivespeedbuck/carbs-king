"""Replay the canonical 100-day backup through the dynamic-carb reference engine."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dynamic_carb_engine import (  # noqa: E402
    calculate_body_energy,
    calculate_daily_target,
    estimate_long_term_maintenance,
)


DEFAULT_INPUT = ROOT / "release_candidates" / "carbs-king-virtual-100-days-20260415-20260723.json"
DEFAULT_OUTPUT = ROOT / "release_candidates" / "dynamic-carb-100-day-reference-replay.json"


def normalize_training(record: Mapping[str, Any]) -> dict[str, Any]:
    training = record.get("training") if isinstance(record.get("training"), Mapping) else {}
    sessions = [item for item in training.get("sessions", []) if isinstance(item, Mapping)]
    completed = [item for item in sessions if item.get("status") == "completed"]
    if not completed:
        return {"status": "explicit_rest"}

    muscle_sets: Counter[str] = Counter()
    cardio_duration = 0.0
    total_duration = 0.0
    for session in completed:
        total_duration += float(session.get("total_duration_min") or 0)
        for exercise in session.get("exercises", []):
            if not isinstance(exercise, Mapping) or not exercise.get("completed", True):
                continue
            if exercise.get("recording_mode") == "strength":
                body_part = str(exercise.get("body_part") or "未分类")
                muscle_sets[body_part] += sum(
                    bool(training_set.get("completed")) and not bool(training_set.get("warmup"))
                    for training_set in exercise.get("sets", [])
                    if isinstance(training_set, Mapping)
                )
            elif exercise.get("recording_mode") == "cardio":
                cardio_duration += float(exercise.get("duration_seconds") or 0) / 60.0

    facts: dict[str, Any] = {"status": "completed", "sessions": len(completed)}
    if muscle_sets:
        facts["resistance"] = {
            "work_sets_total": sum(muscle_sets.values()),
            "peak_primary_muscle_sets": max(muscle_sets.values()),
            "duration_min": total_duration,
        }
    if cardio_duration > 0:
        facts["cardio"] = {"duration_min": cardio_duration, "intensity": "moderate"}
    return facts


def replay_fixture(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("daily_records") if isinstance(payload.get("daily_records"), Mapping) else {}
    old_days: Counter[str] = Counter()
    new_days: Counter[str] = Counter()
    demands: Counter[str] = Counter()
    transitions: Counter[str] = Counter()
    violations: list[str] = []
    history: list[dict[str, Any]] = []
    final_calibration: dict[str, Any] | None = None

    for date_key in sorted(records):
        record = records[date_key]
        profile_data = record.get("profile") if isinstance(record.get("profile"), Mapping) else {}
        profile = {
            "sex": profile_data.get("sex"),
            "age": profile_data.get("age"),
            "height": profile_data.get("height_cm"),
            "weight": profile_data.get("weight_kg"),
            "bodyfat": profile_data.get("bodyfat_percent"),
            "bodyfat_status": "observed",
            "bodyfat_age_days": 0,
            "goal": "减脂",
            "activity_habit": profile_data.get("activity_habit"),
        }
        normalized_training = normalize_training(record)
        result = calculate_daily_target(profile, normalized_training, effective_date=date_key)
        old_day = str(profile_data.get("day_type") or "")
        new_day = str(result["recommended_day"])
        old_days[old_day] += 1
        new_days[new_day] += 1
        demands[str(result["recommended_demand"]["demand_key"])] += 1
        transitions[f"{old_day}->{new_day}"] += 1
        macro = result["recommended_macros"]
        if macro["status"] != "ok" or abs(float(macro.get("energy_closure_error") or 0)) > 1e-6:
            violations.append(f"{date_key}:macro")

        daily_total = record.get("daily_total") if isinstance(record.get("daily_total"), Mapping) else {}
        history.append({
            "date": date_key,
            "weight_status": "observed",
            "weight_kg": profile_data.get("weight_kg"),
            "diet_day_status": "complete",
            "energy_intake_kcal": daily_total.get("kcal"),
            "goal": "减脂",
        })
        current = date.fromisoformat(date_key)
        prior = float(calculate_body_energy(profile)["maintenance_kcal"])
        final_calibration = estimate_long_term_maintenance(history, current + timedelta(days=1), prior)

    return {
        "schema": "dynamic_carb_100_day_reference_replay",
        "input": path.name,
        "record_days": len(records),
        "old_day_types": dict(old_days),
        "new_day_types": dict(new_days),
        "demand_types": dict(demands),
        "transitions": dict(transitions),
        "violations": violations,
        "calibration": final_calibration,
        "calibration_interpretation": "engineering_fixture_only_not_physiological_validation",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = replay_fixture(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("record_days", "old_day_types", "new_day_types", "violations")}, ensure_ascii=False))
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
