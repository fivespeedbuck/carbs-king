"""Replay the canonical 100-day backup through the dynamic-carb reference engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dynamic_carb_engine import (  # noqa: E402
    calculate_body_energy,
    calculate_daily_target,
    create_phase_baseline,
    estimate_long_term_maintenance,
)
from dynamic_carb_adapter import normalize_training  # noqa: E402


DEFAULT_INPUT = ROOT / "release_candidates" / "carbs-king-virtual-100-days-20260415-20260723.json"
DEFAULT_OUTPUT = ROOT / "release_candidates" / "dynamic-carb-100-day-reference-replay.json"


def replay_fixture(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    raw_bytes = path.read_bytes()
    payload = json.loads(raw_bytes.decode("utf-8-sig"))
    records = payload.get("daily_records") if isinstance(payload.get("daily_records"), Mapping) else {}
    old_days: Counter[str] = Counter()
    new_days: Counter[str] = Counter()
    demands: Counter[str] = Counter()
    recommendation_states: Counter[str] = Counter()
    training_statuses: Counter[str] = Counter()
    transitions: Counter[str] = Counter()
    violations: list[str] = []
    history: list[dict[str, Any]] = []
    final_calibration: dict[str, Any] | None = None
    versions: dict[str, Any] = {}
    phase: dict[str, Any] | None = None

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
        if phase is None:
            phase = create_phase_baseline(profile, date_key)
        profile.update({
            "phase_id": phase["phase_id"],
            "phase_baseline_weight_kg": phase["baseline_weight_kg"],
            "phase_maintenance_kcal": phase["maintenance_kcal"],
            "phase_protein_g": phase["protein_g"],
            "phase_fat_anchor_g": phase["fat_anchor_g"],
        })
        raw_training = record.get("training") if isinstance(record.get("training"), Mapping) else {}
        normalized_training = normalize_training(raw_training)
        result = calculate_daily_target(profile, normalized_training, effective_date=date_key)
        versions = {
            "algorithm_version": result["algorithm_version"],
            "parameter_set_version": result["parameter_set_version"],
            "evidence_version": result["evidence_version"],
            "model_document_sha256": result["model_document_sha256"],
            "schema_version": result["schema_version"],
        }
        old_day = str(profile_data.get("day_type") or "")
        new_day = str(result["recommended_day"])
        old_days[old_day] += 1
        new_days[new_day] += 1
        demand = result["recommended_demand"]
        demand_key = str(demand["demand_key"])
        demands[demand_key] += 1
        training_statuses[str(normalized_training["status"])] += 1
        if demand_key == "provisional_low":
            recommendation_states["provisional_low"] += 1
        elif new_day == "低碳日":
            recommendation_states["formal_low"] += 1
        elif new_day == "中碳日":
            recommendation_states["formal_medium"] += 1
        else:
            recommendation_states["formal_high"] += 1
        transitions[f"{old_day}->{new_day}"] += 1
        macro = result["recommended_macros"]
        if macro["status"] != "ok" or abs(float(macro.get("energy_closure_error") or 0)) > 1e-6:
            violations.append(f"{date_key}:macro")
        else:
            displayed = macro["display"]
            displayed_kcal = 4 * displayed["carb_g"] + 4 * displayed["protein_g"] + 9 * displayed["fat_g"]
            if abs(displayed_kcal - float(macro["energy_from_display_macros_exact"])) > 1e-9:
                violations.append(f"{date_key}:display_macro_recompute")
            rounded = float(Decimal(str(displayed_kcal)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if rounded != float(macro["energy_display_kcal"]):
                violations.append(f"{date_key}:display_energy_rounding")

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
        prior = float(phase["maintenance_kcal"])
        final_calibration = estimate_long_term_maintenance(history, current + timedelta(days=1), prior)

    return {
        "schema": "dynamic_carb_100_day_reference_replay",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "file_name": path.name,
            "byte_size": len(raw_bytes),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        },
        "engine": versions,
        "code_sha256": hashlib.sha256(
            (SRC / "dynamic_carb_engine.py").read_bytes()
            + (SRC / "dynamic_carb_adapter.py").read_bytes()
        ).hexdigest(),
        "record_days": len(records),
        "old_day_types": dict(old_days),
        "new_day_types": dict(new_days),
        "demand_types": dict(demands),
        "recommendation_states": dict(recommendation_states),
        "training_statuses": dict(training_statuses),
        "transitions": dict(transitions),
        "violations": violations,
        "calibration": final_calibration,
        "calibration_interpretation": "engineering_fixture_only_not_physiological_validation",
        "data_semantics": "missing_training_is_unknown_and_missing_cardio_intensity_is_not_imputed",
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
