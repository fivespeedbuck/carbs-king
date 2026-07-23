import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_defaults import CIRCUMFERENCE_FIELDS, DEFAULT_MACRO_MULTIPLIERS  # noqa: E402
from app_state import AppState  # noqa: E402
from nutrition_service import create_nutrition_service  # noqa: E402


MEALS = ("早餐", "午餐", "晚餐", "练前", "练后", "偷吃")


class MacroModeTests(unittest.TestCase):
    def setUp(self):
        self.state = AppState.default(MEALS)
        self.state["day_type"] = "高碳日"
        self.state["macro_multipliers"] = copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS)
        self.service = create_nutrition_service(self.state)

    def test_auto_and_custom_values_are_independent(self):
        custom = copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS)
        custom["高碳日"]["carb"] = 4.5
        self.state["macro_multipliers"] = custom

        auto_values = self.service.multipliers("auto")
        custom_values = self.service.multipliers("custom")

        self.assertNotEqual(auto_values["高碳日"]["carb"], 4.5)
        self.assertEqual(custom_values["高碳日"]["carb"], 4.5)

    def test_switching_mode_changes_active_target_without_overwriting_custom(self):
        custom = copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS)
        custom["高碳日"]["carb"] = 4.5
        self.state["macro_multipliers"] = copy.deepcopy(custom)
        self.state["macro_mode"] = "custom"
        custom_target = self.service.targets()["carb"]

        self.state["macro_mode"] = "auto"
        auto_target = self.service.targets()["carb"]

        self.assertNotEqual(custom_target, auto_target)
        self.assertEqual(self.state["macro_multipliers"], custom)

    def test_auto_recalculates_when_profile_changes_but_custom_stays_fixed(self):
        custom_before = self.service.multipliers("custom")
        auto_before = self.service.multipliers("auto")

        self.state["bodyfat"] = "25"
        self.state["age"] = "50"
        auto_after = self.service.multipliers("auto")
        custom_after = self.service.multipliers("custom")

        self.assertNotEqual(auto_before["高碳日"]["carb"], auto_after["高碳日"]["carb"])
        self.assertEqual(custom_before, custom_after)


class ProfileMeasurementContractTests(unittest.TestCase):
    def test_only_normal_circumferences_are_configured(self):
        self.assertEqual(
            CIRCUMFERENCE_FIELDS,
            (
                ("chest_cm", "胸围"),
                ("waist_cm", "腰围"),
                ("hip_cm", "臀围"),
                ("arm_cm", "上臂围"),
                ("thigh_cm", "大腿围"),
                ("calf_cm", "小腿围"),
            ),
        )
        keys = {key for key, _ in CIRCUMFERENCE_FIELDS}
        self.assertNotIn("neck_cm", keys)
        self.assertNotIn("shoulder_cm", keys)

    def test_profile_ui_has_explicit_measurement_action_and_full_terms(self):
        controller = (ROOT / "src" / "profile_controller.py").read_text(encoding="utf-8-sig")
        details = (ROOT / "src" / "profile_details_views.py").read_text(encoding="utf-8-sig")
        macro = (ROOT / "src" / "profile_macro_views.py").read_text(encoding="utf-8-sig")

        self.assertIn("def record_current_measurement", controller)
        self.assertIn('snack("资料已保存，未新增围度记录")', controller)
        self.assertIn('"记录本次测量"', details)
        self.assertIn("BMR（基础代谢率）", details)
        self.assertIn("TDEE（每日总能量消耗）", details)
        self.assertIn("if not auto_selected", macro)
        self.assertIn("当前显示自动计算倍率，仅供查看", macro)

    def test_profile_fields_use_shared_compact_aligned_grids(self):
        controller = (ROOT / "src" / "profile_controller.py").read_text(encoding="utf-8-sig")
        details = (ROOT / "src" / "profile_details_views.py").read_text(encoding="utf-8-sig")

        self.assertIn("two_field_grid(weight_box, bodyfat_box", controller)
        self.assertIn("two_field_grid(height_box, age_box", controller)
        self.assertIn("three_field_grid(carb_box, protein_box, fat_box", controller)
        self.assertIn("two_field_grid(weight_box, bodyfat_box", details)
        self.assertIn("two_field_grid(height_box, age_box", details)


if __name__ == "__main__":
    unittest.main()
