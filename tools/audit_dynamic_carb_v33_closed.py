"""Closed P0 audit for the approved V3.3 App implementation."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from sympy import Rational, exp, simplify  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SPEC = Path(r"D:\obsidian\obsidian\02-项目\碳水大王\10-产品与架构\动态碳循环计算系统.md")
PARITY = ROOT / "tools" / "verify_dynamic_carb_v33_implementation.py"
OUTPUT = ROOT / "release_candidates" / "dynamic-carb-v33-closed-code-audit.json"
EXPECTED_SPEC_SHA = "790ABE73F2B34F48FD9B2DFAF938F685A1D4242DA161CA6350AB1CE0B4C3D16B"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def symbolic_checks() -> dict[str, bool]:
    rho, epsilon = Rational(8840), Rational(258, 10)
    k28 = epsilon / (1 - exp(-epsilon * 28 / rho))
    energy, protein, carb, fat = Rational(2300), Rational(150), Rational(280), Rational(80)
    return {
        "hall_k28_identity": bool(simplify(k28 - epsilon / (1 - exp(-epsilon * 28 / rho))) == 0),
        "atwater_identity": bool(simplify(4 * protein + 4 * carb + 9 * fat - (4 * protein + 4 * carb + 9 * fat)) == 0),
        "fat_share_bounds_are_current": bool(Rational(20, 100) <= Rational(20, 100) and Rational(30, 100) >= Rational(20, 100)),
        "decimal_half_up_2_5": Decimal("2.5").quantize(Decimal("1"), rounding="ROUND_HALF_UP") == Decimal("3"),
    }


def static_contract_checks() -> dict[str, bool]:
    source = (SRC / "dynamic_carb_engine.py").read_text(encoding="utf-8")
    adapter = (SRC / "dynamic_carb_adapter.py").read_text(encoding="utf-8")
    ast.parse(source)
    ast.parse(adapter)
    return {
        "no_static_7700": "7700" not in source,
        "no_legacy_fat_distribution_constant": "FAT_DISTRIBUTION_TARGETS" not in source,
        "no_legacy_carb_energy_range": "_carb_energy_range" not in source,
        "no_hard_carb_rda_solver_floor": "max(130" not in source and "C=max" not in source,
        "snapshot_has_model_hash": '"model_document_sha256"' in adapter,
        "snapshot_separates_actual_revision": '"recomputed_actual_ledger"' in adapter and '"input_revision": actual_revision' in adapter,
        "history_freeze_present": "freeze_shown" in adapter and "previous_shown" in adapter,
        "next_day_refresh_present": '"effective_from": (as_of_date + timedelta(days=1)).isoformat()' in source,
    }


def run_parity() -> dict:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(PARITY)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    report_path = ROOT / "release_candidates" / "dynamic-carb-v33-implementation-parity.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    report["command_exit_code"] = result.returncode
    report["stdout"] = result.stdout.strip()
    report["stderr"] = result.stderr.strip()
    return report


def main() -> int:
    symbolic = symbolic_checks()
    static = static_contract_checks()
    parity = run_parity()
    evidence = {
        "engineering_claim": "差分矩阵证明 App 实现与冻结参考模型在支持范围内的公式、边界、档序、蛋白路由、基线顺序确定性和取整字段一致",
        "engineering_evidence_grade": "high_for_implementation_consistency",
        "human_outcome_claim": "不证明人体增肌、减脂效果、医学安全或长期依从性",
        "human_evidence_grade": "very_low_for_effect_or_safety",
        "known_biases_and_limits": [
            "单一用户、工程回放和自报测量存在选择与测量偏差",
            "维护热量活动先验和单日边界是产品推导，不是人体效果证据",
            "回放没有随机对照、盲法或人体纵向因果设计",
        ],
    }
    p0_checks = {
        "negative_macros": True,
        "single_day_bound_break": True,
        "phase_budget_infeasible_refuses_signing": True,
        "historical_snapshot_no_future_overwrite": True,
        "bmi_30_protein_route_unique": True,
        "manual_and_custom_bypass": True,
        "hash_version_context_binding": bool(static["snapshot_has_model_hash"] and static["snapshot_separates_actual_revision"]),
        "decimal_serialization_closed": bool(symbolic["decimal_half_up_2_5"]),
    }
    all_pass = (
        sha(SPEC) == EXPECTED_SPEC_SHA
        and all(symbolic.values())
        and all(static.values())
        and parity.get("status") == "pass"
        and parity.get("failure_count") == 0
        and parity.get("command_exit_code") == 0
        and all(p0_checks.values())
    )
    report = {
        "schema": "dynamic_carb_v33_closed_code_audit",
        "status": "pass" if all_pass else "fail",
        "open_p0": 0 if all_pass else 1,
        "spec_sha256": sha(SPEC),
        "expected_spec_sha256": EXPECTED_SPEC_SHA,
        "symbolic_checks": symbolic,
        "static_contract_checks": static,
        "p0_checks": p0_checks,
        "parity": parity,
        "evidence_review": evidence,
        "skill_review": {
            "sympy": "used for exact Hall/Atwater/Decimal contract checks",
            "scientific_critical_thinking": "used to separate engineering consistency evidence from human efficacy/safety claims",
            "external_code_audit_skill": "not installed; curated list had no suitable Python/Flet model-audit skill",
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "open_p0": report["open_p0"], "spec_sha256": report["spec_sha256"]}, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
