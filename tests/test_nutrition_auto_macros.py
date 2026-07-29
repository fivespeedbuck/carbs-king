import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_defaults import DAY_TYPES, DEFAULT_MACRO_MULTIPLIERS  # noqa: E402
from app_state import AppState  # noqa: E402
from nutrition_service import (  # noqa: E402
    FAT_CALORIE_SHARE,
    GOAL_CONFIG,
    create_nutrition_service,
)


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

    def test_goal_and_day_calorie_factors_are_explicit(self):
        self.assertEqual(
            {goal: GOAL_CONFIG[goal]["calorie_factor"] for goal in GOALS},
            {
                "减脂": {"高碳日": 0.90, "中碳日": 0.80, "低碳日": 0.70},
                "保持": {"高碳日": 1.10, "中碳日": 1.00, "低碳日": 0.90},
                "增肌": {"高碳日": 1.15, "中碳日": 1.05, "低碳日": 0.95},
            },
        )
        self.assertEqual(FAT_CALORIE_SHARE, {"高碳日": 0.25, "中碳日": 0.30, "低碳日": 0.35})

    def test_all_nine_auto_targets_close_energy_and_use_declared_bases(self):
        composition = self.service.body_composition()
        for goal in GOALS:
            self.state["macro_goal"] = goal
            day_carbs = []
            for day_type in DAY_TYPES:
                with self.subTest(goal=goal, day_type=day_type):
                    self.state["day_type"] = day_type
                    target = self.service.targets()
                    multipliers = self.service.multipliers("auto")[day_type]
                    macro_kcal = target["carb"] * 4 + target["protein"] * 4 + target["fat"] * 9

                    self.assertAlmostEqual(macro_kcal, target["calorie_target"], delta=1.5)
                    self.assertEqual(target["protein_basis"], "lean_mass")
                    self.assertAlmostEqual(
                        target["protein"] / composition["lean_mass"],
                        GOAL_CONFIG[goal]["protein_lbm_gkg"],
                        delta=0.01,
                    )
                    self.assertAlmostEqual(
                        target["fat"] * 9 / target["calorie_target"],
                        FAT_CALORIE_SHARE[day_type],
                        delta=0.001,
                    )
                    self.assertEqual(
                        target["calorie_target"],
                        round(composition["tdee"] * GOAL_CONFIG[goal]["calorie_factor"][day_type], 0),
                    )
                    self.assertAlmostEqual(multipliers["carb"], target["carb"] / composition["weight"], delta=0.01)
                    self.assertAlmostEqual(multipliers["protein"], target["protein"] / composition["lean_mass"], delta=0.01)
                    self.assertAlmostEqual(multipliers["fat"], target["fat"] / composition["weight"], delta=0.01)
                    day_carbs.append(target["carb"])
            self.assertGreater(day_carbs[0], day_carbs[1])
            self.assertGreater(day_carbs[1], day_carbs[2])

    def test_same_day_targets_increase_from_cut_to_maintenance_to_gain(self):
        for day_type in DAY_TYPES:
            self.state["day_type"] = day_type
            values = []
            for goal in GOALS:
                self.state["macro_goal"] = goal
                values.append(self.service.targets())
            self.assertLess(values[0]["calorie_target"], values[1]["calorie_target"])
            self.assertLess(values[1]["calorie_target"], values[2]["calorie_target"])
            self.assertLess(values[0]["carb"], values[1]["carb"])
            self.assertLess(values[1]["carb"], values[2]["carb"])

    def test_every_profile_input_and_cycle_goal_affects_the_calculation(self):
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
            "bodyfat": "20",
            "height": "180",
            "age": "40",
            "sex": "女",
            "activity_habit": "规律训练",
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                self.state.update(baseline_profile)
                self.state[field] = value
                self.assertNotEqual(snapshot(), baseline)

        self.state.update(baseline_profile)
        self.state["macro_goal"] = "保持"
        self.assertNotEqual(snapshot(), baseline)

    def test_screenshot_profile_has_a_real_gain_cycle(self):
        self.state["macro_goal"] = "增肌"
        carbs_per_kg = []
        calorie_targets = []
        for day_type in DAY_TYPES:
            self.state["day_type"] = day_type
            target = self.service.targets()
            carbs_per_kg.append(round(target["carb"] / 61.5, 2))
            calorie_targets.append(target["calorie_target"])

        self.assertEqual(calorie_targets, [2877.0, 2627.0, 2377.0])
        self.assertAlmostEqual(carbs_per_kg[0], 7.03, delta=0.02)
        self.assertAlmostEqual(carbs_per_kg[1], 5.74, delta=0.02)
        self.assertAlmostEqual(carbs_per_kg[2], 4.54, delta=0.02)

    def test_custom_mode_is_not_overwritten_and_uses_its_macro_energy(self):
        custom = copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS)
        custom["高碳日"] = {"carb": 4.5, "protein": 2.1, "fat": 1.0}
        self.state["macro_mode"] = "custom"
        self.state["macro_multipliers"] = copy.deepcopy(custom)
        self.state["day_type"] = "高碳日"

        before = copy.deepcopy(self.state["macro_multipliers"])
        cut_target = self.service.targets()
        self.state["macro_goal"] = "增肌"
        gain_target = self.service.targets()

        self.assertEqual(self.state["macro_multipliers"], before)
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


if __name__ == "__main__":
    unittest.main()
