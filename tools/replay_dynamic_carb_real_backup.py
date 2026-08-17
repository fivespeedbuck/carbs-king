"""Replay an exported real backup with auditable input provenance.

The report intentionally distinguishes stored historical labels from the new
engine's recomputation. Missing historical fields are never silently treated
as observed facts; every fallback is named in each record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dynamic_carb_adapter import normalize_profile, normalize_training  # noqa: E402
from dynamic_carb_engine import calculate_daily_target, create_phase_baseline  # noqa: E402
from training_models import TrainingSession  # noqa: E402
from training_service import raw_training_sessions  # noqa: E402


DEFAULT_OUTPUT = ROOT / "release_candidates" / "dynamic-carb-real-backup-reference-replay.json"


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _raw_completed_resistance_audit(training: Mapping[str, Any]) -> dict[str, int]:
    total = 0
    body_parts: Counter[str] = Counter()
    for raw_session in raw_training_sessions(training):
        session = TrainingSession.from_dict(raw_session)
        if session.status != "completed":
            continue
        for exercise in session.exercises:
            if exercise.recording_mode != "strength":
                continue
            count = sum(1 for item in exercise.sets if item.completed and not item.warmup)
            total += count
            if count:
                body_parts[exercise.body_part or exercise.name or "未分类"] += count
    return {
        "completed_non_warmup_sets": total,
        "peak_body_part_sets": max(body_parts.values(), default=0),
    }


def _profile_state(
    record_profile: Mapping[str, Any],
    fallback_profile: Mapping[str, Any],
    latest_bodyfat: tuple[Any, str] | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    mapping = {
        "weight": "weight_kg",
        "bodyfat": "bodyfat_percent",
        "height": "height_cm",
        "age": "age",
        "sex": "sex",
        "activity_habit": "activity_habit",
        "macro_goal": "macro_goal",
    }
    state: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for state_key, record_key in mapping.items():
        value = record_profile.get(record_key)
        if value not in (None, ""):
            state[state_key] = value
            sources[state_key] = "daily_record_profile"
            continue
        fallback_value = fallback_profile.get(state_key)
        if fallback_value not in (None, ""):
            state[state_key] = fallback_value
            sources[state_key] = "backup_user_profile_current_missing_daily_field"
        else:
            sources[state_key] = "missing"
    measurement = record_profile.get("measurement")
    if isinstance(measurement, Mapping):
        state["measurement"] = dict(measurement)
    measured_bodyfat = measurement.get("bodyfat_percent") if isinstance(measurement, Mapping) else None
    if measured_bodyfat not in (None, ""):
        state["bodyfat"] = measured_bodyfat
        state["bodyfat_measured_at"] = measurement.get("measured_at")
        sources["bodyfat"] = "daily_record_bodyfat_measurement"
        sources["bodyfat_measured_at"] = "daily_record_bodyfat_measurement"
    elif latest_bodyfat is not None:
        state["bodyfat"], state["bodyfat_measured_at"] = latest_bodyfat
        sources["bodyfat"] = "latest_prior_bodyfat_measurement"
        sources["bodyfat_measured_at"] = "latest_prior_bodyfat_measurement"
    return state, sources


def replay_real_backup(path: Path) -> dict[str, Any]:
    raw_bytes = path.read_bytes()
    payload = json.loads(raw_bytes.decode("utf-8-sig"))
    records = payload.get("daily_records") if isinstance(payload.get("daily_records"), Mapping) else {}
    fallback_profile = payload.get("user_profile") if isinstance(payload.get("user_profile"), Mapping) else {}
    stored_days: Counter[str] = Counter()
    recommended_days: Counter[str] = Counter()
    demands: Counter[str] = Counter()
    training_statuses: Counter[str] = Counter()
    replayed: list[dict[str, Any]] = []
    versions: dict[str, Any] = {}
    latest_bodyfat: tuple[Any, str] | None = None
    violations: list[str] = []
    phases: dict[str, dict[str, Any]] = {}

    for date_key in sorted(records):
        record = records[date_key]
        if not isinstance(record, Mapping):
            continue
        record_profile = record.get("profile") if isinstance(record.get("profile"), Mapping) else {}
        measurement = record_profile.get("measurement") if isinstance(record_profile.get("measurement"), Mapping) else {}
        measured_bodyfat = measurement.get("bodyfat_percent")
        measured_at = str(measurement.get("measured_at") or date_key)
        if measured_bodyfat not in (None, ""):
            latest_bodyfat = (measured_bodyfat, measured_at)
        profile_state, profile_sources = _profile_state(record_profile, fallback_profile, latest_bodyfat)
        profile_facts = normalize_profile(profile_state, date_key)
        goal = str(profile_facts.get("goal") or "减脂")
        if goal not in phases:
            phases[goal] = create_phase_baseline(profile_facts, date_key)
        phase = phases[goal]
        profile_facts.update({
            "phase_id": phase["phase_id"],
            "phase_baseline_weight_kg": phase["baseline_weight_kg"],
            "phase_maintenance_kcal": phase["maintenance_kcal"],
            "phase_protein_g": phase["protein_g"],
            "phase_fat_anchor_g": phase["fat_anchor_g"],
        })
        raw_training = record.get("training") if isinstance(record.get("training"), Mapping) else {}
        raw_training_audit = _raw_completed_resistance_audit(raw_training)
        training_facts = normalize_training(raw_training)
        result = calculate_daily_target(profile_facts, training_facts, effective_date=date_key)
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
        versions = {
            "algorithm_version": result["algorithm_version"],
            "parameter_set_version": result["parameter_set_version"],
            "evidence_version": result["evidence_version"],
            "model_document_sha256": result["model_document_sha256"],
            "schema_version": result["schema_version"],
        }
        stored_day = str(record_profile.get("day_type") or "missing")
        recommended_day = str(result["recommended_day"])
        demand_key = str(result["recommended_demand"]["demand_key"])
        stored_days[stored_day] += 1
        recommended_days[recommended_day] += 1
        demands[demand_key] += 1
        training_statuses[str(training_facts["status"])] += 1
        normalized_input = {
            "effective_date": date_key,
            "profile": profile_facts,
            "training": training_facts,
        }
        normalized_hash = _sha256_bytes(
            json.dumps(normalized_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        replayed.append({
            "date": date_key,
            "normalized_input_sha256": normalized_hash,
            "profile_sources": profile_sources,
            "profile_facts": profile_facts,
            "training_facts": training_facts,
            "raw_training_audit": raw_training_audit,
            "stored_day_type": stored_day,
            "legacy_engine_recomputed_day_type": None,
            "legacy_recompute_status": "unavailable_no_versioned_legacy_engine_snapshot",
            "recommended_day_type": recommended_day,
            "recommended_demand_key": demand_key,
            "recommended_macros": result["recommended_macros"],
        })

    return {
        "schema": "dynamic_carb_real_backup_replay_v2",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "file_name": path.name,
            "byte_size": len(raw_bytes),
            "sha256": _sha256_bytes(raw_bytes),
            "backup_version": payload.get("backup_version"),
            "app_version": payload.get("app_version"),
            "exported_at": payload.get("exported_at"),
        },
        "engine": versions,
        "code_sha256": _sha256_bytes(
            (SRC / "dynamic_carb_engine.py").read_bytes()
            + (SRC / "dynamic_carb_adapter.py").read_bytes()
        ),
        "record_days": len(replayed),
        "summary": {
            "stored_day_types": dict(stored_days),
            "recommended_day_types": dict(recommended_days),
            "demand_types": dict(demands),
            "training_statuses": dict(training_statuses),
        },
        "violations": violations,
        "interpretation_limits": [
            "stored_day_type_is_not_a_ground_truth_label",
            "legacy_engine_output_cannot_be_recomputed_without_its_versioned_snapshot",
            "current_user_profile_fallbacks_are_named_and_macro_amounts_using_them_are_not_historical_validation",
            "training_classification_is_an_engineering_replay_not_physiological_outcome_validation",
        ],
        "records": replayed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = replay_real_backup(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"record_days": report["record_days"], **report["summary"]}, ensure_ascii=False))
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
