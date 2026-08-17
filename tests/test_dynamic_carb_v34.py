import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynamic_carb_adapter import calculate_app_snapshot  # noqa: E402
from dynamic_carb_engine import (  # noqa: E402
    ENGINE_VERSION,
    calculate_daily_target,
    classify_training,
    solve_period_preview,
)


GOAL_CASES = {
    ("男", "减脂"): {"carb": (3.5, 3.0, 8 / 3), "protein": 1.7, "fat": 1.0},
    ("男", "保持"): {"carb": (3.75, 3.25, 35 / 12), "protein": 1.75, "fat": 1.0},
    ("男", "增肌"): {"carb": (4.0, 3.5, 19 / 6), "protein": 1.8, "fat": 1.0},
    ("女", "减脂"): {"carb": (3.0, 2.5, 13 / 6), "protein": 1.7, "fat": 1.1},
    ("女", "保持"): {"carb": (3.25, 2.75, 29 / 12), "protein": 1.75, "fat": 1.15},
    ("女", "增肌"): {"carb": (3.5, 3.0, 8 / 3), "protein": 1.8, "fat": 1.2},
}


def profile(sex="男", goal="减脂", bodyfat=14.2):
    result = {
        "weight_kg": 62.35,
        "height_cm": 174,
        "age_years": 31,
        "sex": sex,
        "goal": goal,
        "activity_habit": "规律训练",
    }
    if bodyfat is not None:
        result.update({"bodyfat_percent": bodyfat, "bodyfat_status": "observed", "bodyfat_age_days": 0})
    return result


def training(body_part, sets=4):
    return {
        "status": "planned_confirmed",
        "body_parts": [body_part],
        "resistance": {"work_sets_total": sets, "peak_body_part_sets": sets, "duration_min": 60},
    }


class DynamicCarbV34Tests(unittest.TestCase):
    def test_all_goal_sex_tiers_close_their_weekly_wiki_baseline(self):
        for (sex, goal), expected in GOAL_CASES.items():
            with self.subTest(sex=sex, goal=goal):
                snapshots = [
                    calculate_daily_target(profile(sex, goal), training(part))
                    for part in ("背", "胸", "二头")
                ]
                carbs = [item["applied_macros"]["carb_internal_g"] / 62.35 for item in snapshots]
                proteins = [item["applied_macros"]["protein_internal_g"] / 62.35 for item in snapshots]
                fats = [item["applied_macros"]["fat_internal_g"] / 62.35 for item in snapshots]
                expected_high, expected_mid, expected_low = expected["carb"]
                for actual, wanted in zip(carbs, (expected_high, expected_mid, expected_low)):
                    self.assertAlmostEqual(actual, wanted, places=7)
                self.assertAlmostEqual((2 * carbs[0] + 2 * carbs[1] + 3 * carbs[2]) / 7, expected_mid, places=7)
                self.assertTrue(all(abs(item - expected["protein"]) < 1e-9 for item in proteins))
                self.assertTrue(all(abs(item - expected["fat"]) < 1e-9 for item in fats))
                self.assertIn("v3.4", snapshots[0]["algorithm_version"])

    def test_bodyfat_does_not_change_v34_macros(self):
        observed = calculate_daily_target(profile(bodyfat=14.2), training("背"))["applied_macros"]
        missing = calculate_daily_target(profile(bodyfat=None), training("背"))["applied_macros"]
        for key in ("carb_internal_g", "protein_internal_g", "fat_internal_g", "energy_internal_kcal"):
            self.assertAlmostEqual(observed[key], missing[key], places=9)

    def test_body_part_not_set_count_controls_resistance_tier(self):
        self.assertEqual(classify_training(training("背", sets=4))["day_type"], "高碳日")
        self.assertEqual(classify_training(training("背", sets=24))["day_type"], "高碳日")
        self.assertEqual(classify_training(training("胸", sets=4))["day_type"], "中碳日")
        self.assertEqual(classify_training(training("胸", sets=24))["day_type"], "中碳日")
        self.assertEqual(classify_training(training("二头", sets=24))["day_type"], "低碳日")
        self.assertEqual(classify_training({"status": "explicit_rest"})["day_type"], "低碳日")

    def test_reference_period_preview_uses_two_high_two_mid_three_low(self):
        result = solve_period_preview(profile("男", "保持"), {"high": 2, "mid": 2, "low": 3})
        self.assertTrue(result["feasible"])
        self.assertAlmostEqual(result["period_closure_error_kcal"], 0, places=7)
        self.assertAlmostEqual(result["applied_budget_kcal_day"] / 62.35, 29.0, places=7)

    def test_current_day_replaces_a_v33_phase_without_rewriting_old_snapshot_values(self):
        current = {
            "date": date.today().isoformat(),
            "weight": "62.35",
            "bodyfat": "14.2",
            "height": "174",
            "age": "31",
            "sex": "男",
            "activity_habit": "规律训练",
            "macro_goal": "减脂",
            "day_type": "低碳日",
            "training": {"targets": [{"target": "休息"}], "carb_mode": "auto"},
            "carb_phase": {
                "phase_id": "phase-v33",
                "started_at": "2026-08-07",
                "effective_from": "2026-08-07",
                "goal": "cut_standard",
                "baseline_weight_kg": 62.35,
                "maintenance_kcal": 2278,
                "protein_g": 123,
                "fat_anchor_g": 49.9,
                "algorithm_version": "CK-DCE-v3.3-rc2-r3-final-candidate",
            },
        }
        snapshot = calculate_app_snapshot(current)
        self.assertEqual(current["carb_phase"]["algorithm_version"], ENGINE_VERSION)
        self.assertNotEqual(current["carb_phase"]["phase_id"], "phase-v33")
        self.assertEqual(snapshot["engine_snapshot"]["algorithm_version"], ENGINE_VERSION)


if __name__ == "__main__":
    unittest.main()
