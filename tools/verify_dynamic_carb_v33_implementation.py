"""Differentially verify the App V3.3 engine against the frozen reviewed model."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import dynamic_carb_engine as app  # noqa: E402


DEFAULT_REFERENCE = Path.home() / ".codex" / "worktrees" / "b783" / "carbs-king" / "docs" / "model-review" / "v3.3-rc2" / "10-v3.3-rc2-model-replay.py"
DEFAULT_SPEC = Path(r"D:\obsidian\obsidian\02-项目\碳水大王\10-产品与架构\动态碳循环计算系统.md")
DEFAULT_OUTPUT = ROOT / "release_candidates" / "dynamic-carb-v33-implementation-parity.json"
TIERS = ("low", "mid", "high")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load_reference(path: Path):
    spec = importlib.util.spec_from_file_location("v33_frozen_reference", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load reference: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(reference_path: Path, spec_path: Path) -> dict[str, Any]:
    reference = _load_reference(reference_path)
    failures: list[dict[str, Any]] = []
    counters = {"hall": 0, "protein": 0, "distribution": 0, "baseline": 0}

    def fail(kind: str, context: Any, expected: Any, actual: Any) -> None:
        if len(failures) < 100:
            failures.append({"kind": kind, "context": context, "expected": expected, "actual": actual})

    targets = ("gain_controlled", "recomp", "cut_standard")
    maintenances = (800.0, 1000.0, 1500.0, 2100.0, 2500.0, 4000.0, 8000.0)
    weights = (25.0, 40.0, 60.0, 78.0, 120.0, 250.0, 500.0)
    distributions = [
        dict(zip(TIERS, values))
        for values in itertools.product(range(8), repeat=3)
        if sum(values) == 7
    ]

    for target, maintenance, weight in itertools.product(targets, maintenances, weights):
        expected_budget = reference.hall_budget(target, maintenance=maintenance, weight=weight)
        profile = {
            "sex": "male", "age": 30, "height": 175, "weight": weight,
            "goal": target, "maintenance_kcal": maintenance,
        }
        actual_budget = app.calculate_body_energy(profile)
        counters["hall"] += 1
        for key in ("raw_delta_kcal_day", "guarded_delta_kcal_day", "raw_budget_kcal_day", "guarded_budget_kcal_day"):
            if abs(float(expected_budget[key]) - float(actual_budget[key])) > 1e-8:
                fail("hall", {"target": target, "maintenance": maintenance, "weight": weight, "field": key}, expected_budget[key], actual_budget[key])

        expected_protein = reference.resolve_protein(target, weight, 175.0, "male", [], reference.DEFAULT_AS_OF_DATE)
        actual_protein = app.resolve_phase_protein(target, weight, 175.0, "male", [], reference.DEFAULT_AS_OF_DATE)
        counters["protein"] += 1
        if expected_protein.get("route") != actual_protein.get("route") or abs(float(expected_protein["protein_g"]) - float(actual_protein["protein_g"])) > 1e-8:
            fail("protein", {"target": target, "weight": weight}, expected_protein, actual_protein)

        protein = float(expected_protein["protein_g"])
        for counts in distributions:
            expected = reference.solve_distribution(
                target, counts, expected_budget["guarded_budget_kcal_day"],
                maintenance=maintenance, weight=weight, protein=protein, fat_anchor=0.8 * weight,
            )
            actual = app.solve_distribution(
                target, counts, expected_budget["guarded_budget_kcal_day"],
                maintenance=maintenance, baseline_weight=weight, protein=protein, fat_anchor=0.8 * weight,
            )
            counters["distribution"] += 1
            if expected["feasible"] != actual["feasible"]:
                fail("distribution_feasible", {"target": target, "maintenance": maintenance, "weight": weight, "counts": counts}, expected["feasible"], actual["feasible"])
                continue
            for key in ("feasible_average_min_kcal_day", "feasible_average_max_kcal_day", "feasible_speed_min", "feasible_speed_max"):
                if key in expected and abs(float(expected[key]) - float(actual[key])) > 1e-7:
                    fail("distribution_boundary", {"target": target, "maintenance": maintenance, "weight": weight, "counts": counts, "field": key}, expected[key], actual[key])
            if not expected["feasible"]:
                continue
            for tier in TIERS:
                if abs(expected["daily_energy_by_tier_kcal"][tier] - actual["daily_energy_by_tier_kcal"][tier]) > 1e-7:
                    fail("tier_energy", {"target": target, "maintenance": maintenance, "weight": weight, "counts": counts, "tier": tier}, expected["daily_energy_by_tier_kcal"][tier], actual["daily_energy_by_tier_kcal"][tier])
                for key in ("protein_internal_g", "carb_internal_g", "fat_internal_g", "protein_display_g", "carb_display_g", "fat_display_g", "energy_from_display_macros_exact", "energy_display_kcal"):
                    expected_value = expected["daily_macros_by_tier"][tier][key]
                    actual_value = actual["daily_macros_by_tier"][tier][key]
                    if abs(float(expected_value) - float(actual_value)) > 1e-7:
                        fail("tier_macro", {"target": target, "maintenance": maintenance, "weight": weight, "counts": counts, "tier": tier, "field": key}, expected_value, actual_value)

    as_of = date(2026, 8, 3)
    baseline_weights = [
        {"record_id": f"w-{index:02d}", "date": (as_of - timedelta(days=22 - index * 2)).isoformat(), "weight": 78.0 - index * 0.05}
        for index in range(12)
    ]
    bodyfat = [{"record_id": "bf-1", "date": as_of.isoformat(), "bodyfat_percent": 20.0}]
    rng = random.Random(20260803)
    for _ in range(100):
        shuffled = list(baseline_weights)
        rng.shuffle(shuffled)
        expected = reference.evaluate_baseline_refresh(shuffled, bodyfat, 78.0, "cut_standard", sex="male", height_cm=175.0, age_years=31, as_of_date=as_of)
        actual = app.evaluate_baseline_refresh(shuffled, bodyfat, 78.0, "cut_standard", sex="male", height_cm=175.0, age_years=31, as_of_date=as_of)
        counters["baseline"] += 1
        for key in ("refresh", "trigger", "window_start", "window_end", "effective_from", "affects_past", "protein_route"):
            if expected.get(key) != actual.get(key):
                fail("baseline", {"field": key}, expected.get(key), actual.get(key))
        for key in ("new_baseline_weight_kg", "new_protein_g", "new_fat_anchor_g"):
            if abs(float(expected[key]) - float(actual[key])) > 1e-8:
                fail("baseline_numeric", {"field": key}, expected[key], actual[key])

    return {
        "schema": "dynamic_carb_v33_implementation_parity",
        "status": "pass" if not failures else "fail",
        "algorithm_version": app.ENGINE_VERSION,
        "parameter_set_version": app.PARAMETER_SET_VERSION,
        "evidence_version": app.EVIDENCE_VERSION,
        "model_document_sha256_expected": app.MODEL_DOCUMENT_SHA256,
        "model_document_sha256_actual": _sha(spec_path),
        "reference_sha256": _sha(reference_path),
        "implementation_sha256": _sha(SRC / "dynamic_carb_engine.py"),
        "case_counts": counters,
        "failure_count": len(failures),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = verify(args.reference, args.spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "case_counts", "failure_count", "model_document_sha256_actual")}, ensure_ascii=False))
    return 1 if report["failure_count"] or report["model_document_sha256_actual"] != report["model_document_sha256_expected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
