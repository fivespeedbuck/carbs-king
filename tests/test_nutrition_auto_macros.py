import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_defaults import DAY_TYPES, DEFAULT_MACRO_MULTIPLIERS  # noqa: E402
from app_state import AppState  # noqa: E402
from nutrition_service import create_nutrition_service  # noqa: E402


MEALS = ("早餐", "午餐", "晚餐", "练前", "练后", "偷吃")
GOALS = ("减脂", "保持", "增肌")


class AutomaticMacroFormulaTests(unittest.TestCase):
    def setUp(self):
        self.state = AppState.default(MEALS)
        self.state.update({
            "weight": "61.5",
            "bodyfat": "12.9",
            "height": "175",
            "age": "30",
            "sex": "男",
            "activity_habit": "高频训练",
            "macro_mode": "auto",
        })
        self.service = create_nutrition_service(self.state)

    def test_automatic_targets_come_from_the_dynamic_engine(self):
        target = self.service.targets()
        self.assertTrue(target["dynamic_carb"])
        self.assertEqual(target["dynamic_status"], "provisional")
        self.assertEqual(target["day_label"], "暂定低碳")

    def test_all_goal_and_manual_day_projections_close_energy_and_keep_protein_fixed(self):
        self.state["training"]["carb_mode"] = "manual"
        for goal in GOALS:
            self.state["macro_goal"] = goal
            day_carbs = []
            day_proteins = []
            for day_type in DAY_TYPES:
                with self.subTest(goal=goal, day_type=day_type):
                    self.state["day_type"] = day_type
                    target = self.service.targets()
                    macro_kcal = target["carb"] * 4 + target["protein"] * 4 + target["fat"] * 9
                    self.assertAlmostEqual(macro_kcal, target["calorie_target"], delta=30)
                    self.assertTrue(str(target["protein_basis"]))
                    day_carbs.append(target["carb"])
                    day_proteins.append(target["protein"])
            self.assertGreaterEqual(day_carbs[0], day_carbs[1])
            self.assertGreaterEqual(day_carbs[1], day_carbs[2])
            self.assertEqual(len(set(day_proteins)), 1)

    def test_same_day_targets_increase_from_cut_to_maintenance_to_gain(self):
        for day_type in DAY_TYPES:
            self.state["day_type"] = day_type
            values = []
            for goal in GOALS:
                self.state["macro_goal"] = goal
                values.append(self.service.targets())
            self.assertLess(values[0]["calorie_target"], values[1]["calorie_target"])
            self.assertLess(values[1]["calorie_target"], values[2]["calorie_target"])

    def test_phase_inputs_stay_fixed_until_a_new_goal_phase(self):
        self.state["macro_goal"] = "减脂"
        self.state["day_type"] = "高碳日"

        def snapshot():
            target = self.service.targets()
            return (
                target["bmr"],
                target["tdee"],
                target["calorie_target"],
                target["carb"],
                target["protein"],
                target["fat"],
            )

        baseline_profile = {
            key: self.state[key]
            for key in ("weight", "bodyfat", "height", "age", "sex", "activity_habit")
        }
        baseline = snapshot()
        changes = {
            "weight": "70",
            "height": "180",
            "age": "40",
            "sex": "女",
            "activity_habit": "规律训练",
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                self.state.update(baseline_profile)
                self.state[field] = value
                if field == "activity_habit":
                    self.assertEqual(snapshot(), baseline)
                else:
                    self.assertNotEqual(snapshot(), baseline)

        self.state.update(baseline_profile)
        self.state["macro_goal"] = "保持"
        self.assertNotEqual(snapshot(), baseline)

    def test_gain_goal_uses_one_energy_budget_and_respects_macro_feasibility(self):
        self.state["macro_goal"] = "增肌"
        self.state["training"]["carb_mode"] = "manual"
        carbs_per_kg = []
        calorie_targets = []
        for day_type in DAY_TYPES:
            self.state["day_type"] = day_type
            target = self.service.targets()
            carbs_per_kg.append(round(target["carb"] / 61.5, 2))
            calorie_targets.append(target["calorie_target"])

        self.assertEqual(len(set(calorie_targets)), 3)
        self.assertGreater(calorie_targets[0], calorie_targets[1])
        self.assertGreater(calorie_targets[1], calorie_targets[2])
        self.assertGreaterEqual(carbs_per_kg[0], carbs_per_kg[1])
        self.assertGreaterEqual(carbs_per_kg[1], carbs_per_kg[2])

    def test_custom_mode_is_not_overwritten_and_uses_its_macro_energy(self):
        custom = copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS)
        custom["高碳日"] = {"carb": 4.5, "protein": 2.1, "fat": 1.0}
        self.state["macro_mode"] = "custom"
        self.state["macro_multipliers"] = copy.deepcopy(custom)
        self.state["day_type"] = "高碳日"
        self.state["training"]["planned_exercises"] = [{
            "name": "深蹲", "sets": 12, "reps": 8, "weight": 100,
            "load_kind": "external", "parameters_confirmed": True,
        }]

        before = copy.deepcopy(self.state["macro_multipliers"])
        cut_target = self.service.targets()
        self.state["macro_goal"] = "增肌"
        gain_target = self.service.targets()

        self.assertEqual(self.state["macro_multipliers"], before)
        self.assertEqual(self.state["training"]["carb_snapshot"], {})
        self.assertNotIn("dynamic_carb", cut_target)
        self.assertEqual(cut_target["calorie_target"], gain_target["calorie_target"])
        self.assertAlmostEqual(
            cut_target["carb"] * 4 + cut_target["protein"] * 4 + cut_target["fat"] * 9,
            cut_target["calorie_target"],
            delta=1.5,
        )

    def test_empty_profile_stays_unready_and_legacy_goal_defaults_to_cut(self):
        state = AppState.default(MEALS)
        service = create_nutrition_service(state)

        self.assertEqual(state["macro_goal"], "减脂")
        self.assertFalse(service.targets()["is_ready"])
        self.assertEqual(service.multipliers("auto"), {})

    def test_goal_preview_reports_all_tiers_without_mutating_real_goal_or_phase(self):
        self.state["macro_goal"] = "保持"
        self.service.targets()
        original_phase = copy.deepcopy(self.state["carb_phase"])
        original_snapshot = copy.deepcopy(self.state["training"]["carb_snapshot"])

        preview = self.service.multipliers("auto", "增肌")

        self.assertEqual(self.state["macro_goal"], "保持")
        self.assertEqual(self.state["carb_phase"], original_phase)
        self.assertEqual(self.state["training"]["carb_snapshot"], original_snapshot)
        self.assertEqual(set(preview), set(DAY_TYPES))
        for values in preview.values():
            self.assertGreater(values["kcal"], 0)
            self.assertGreater(values["carb_g"], 0)
            self.assertGreater(values["protein_g"], 0)
            self.assertGreater(values["fat_g"], 0)

    def test_automatic_profile_readiness_uses_adult_weight_and_age_scope(self):
        self.state["weight"] = "24"
        self.state["age"] = "18"
        comp = self.service.body_composition()

        self.assertFalse(comp["is_ready"])
        self.assertIn("体重", comp["missing_fields"])
        self.assertIn("年龄", comp["missing_fields"])

    def test_historical_recompute_keeps_shown_label_macros_and_state_together(self):
        self.state["date"] = "2020-01-01"
        self.state["training"]["targets"] = [{"target": "休息"}]
        original = self.service.targets()
        self.assertEqual(original["day_label"], "低碳日")

        self.state["bodyfat"] = "30"
        self.state["sex"] = "女"
        self.state["activity_habit"] = "久坐少动"
        self.state["macro_goal"] = "增肌"
        self.state["training"]["targets"] = []
        self.state["training"]["session"] = {
            "status": "planned",
            "exercises": [{
                "name": "卧推", "body_part": "胸", "recording_mode": "strength",
                "load_kind": "external", "parameters_confirmed": True,
                "sets": [{"weight_kg": 40, "reps": 10, "completed": False} for _ in range(10)],
            }],
        }
        frozen = self.service.targets()

        self.assertEqual(frozen["day_label"], "低碳日")
        self.assertEqual(frozen["dynamic_status"], original["dynamic_status"])
        self.assertEqual(frozen["carb"], original["carb"])
        self.assertEqual(frozen["bodyfat"], original["bodyfat"])
        self.assertEqual(frozen["sex"], original["sex"])
        self.assertEqual(frozen["activity_habit"], original["activity_habit"])
        self.assertEqual(frozen["macro_goal"], original["macro_goal"])
        self.assertEqual(self.state["day_type"], "低碳日")
        self.assertEqual(self.state["training"]["carb_snapshot"]["engine_snapshot"]["recommended_day"], "中碳日")


if __name__ == "__main__":
    unittest.main()
