import copy
import sys
import unittest
from pathlib import Path

import flet as ft


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_defaults import CIRCUMFERENCE_FIELDS, DEFAULT_MACRO_MULTIPLIERS  # noqa: E402
from app_state import AppState  # noqa: E402
from nutrition_service import create_nutrition_service  # noqa: E402
from profile_details_views import build_profile_details, build_profile_metrics  # noqa: E402


MEALS = ("早餐", "午餐", "晚餐", "练前", "练后", "偷吃")


class MacroModeTests(unittest.TestCase):
    def setUp(self):
        self.state = AppState.default(MEALS)
        self.state.update({
            "weight": "62.5", "bodyfat": "13", "height": "170", "age": "30",
            "sex": "男", "activity_habit": "规律训练",
        })
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

    def test_empty_profile_does_not_create_nutrition_targets(self):
        state = AppState.default(MEALS)
        service = create_nutrition_service(state)

        composition = service.body_composition()
        targets = service.targets()
        evaluation = service.evaluate()

        self.assertFalse(composition["is_ready"])
        self.assertIn("体重", composition["missing_fields"])
        self.assertFalse(targets["is_ready"])
        self.assertIsNone(targets["bmr"])
        self.assertEqual(service.multipliers("auto"), {})
        self.assertEqual(evaluation["status"], "待完善资料")


class ProfileMeasurementContractTests(unittest.TestCase):
    @staticmethod
    def _all_text_values(control):
        values = []
        if isinstance(control, ft.Text):
            values.append(control.value)
        content = getattr(control, "content", None)
        if content is not None and content is not control:
            values.extend(ProfileMeasurementContractTests._all_text_values(content))
        for child in getattr(control, "controls", []) or []:
            values.extend(ProfileMeasurementContractTests._all_text_values(child))
        return values

    @staticmethod
    def _profile_details(*, circumference_values, circumference_expanded):
        return build_profile_details(
            [ft.Container(), ft.Container(), ft.Container(), ft.Container()],
            sex="男",
            activity_habit="规律训练",
            circumference_values=circumference_values,
            circumference_expanded=circumference_expanded,
            on_toggle_circumference=lambda event=None: None,
            on_sex_change=lambda value: None,
            on_activity_change=lambda value: None,
            metrics=ft.Container(),
            macro_panel=ft.Container(),
            backup_panel=ft.Container(),
            viewport_width=360,
        )

    def test_profile_circumference_expansion_state_supports_first_open_and_close(self):
        state = AppState.default(MEALS)

        self.assertFalse(state["profile_circumference_expanded"])

    def test_new_profile_defaults_are_blank(self):
        state = AppState.default(MEALS)

        self.assertEqual(
            {key: state[key] for key in ("weight", "bodyfat", "height", "age", "sex", "activity_habit")},
            {"weight": "", "bodyfat": "", "height": "", "age": "", "sex": "", "activity_habit": ""},
        )
        state["profile_circumference_expanded"] = True
        self.assertTrue(state["profile_circumference_expanded"])
        state["profile_circumference_expanded"] = False
        self.assertFalse(state["profile_circumference_expanded"])

    def test_expanded_profile_circumference_handles_empty_and_historical_data(self):
        empty_text = self._all_text_values(
            self._profile_details(circumference_values={}, circumference_expanded=True)
        )
        historical_text = self._all_text_values(
            self._profile_details(
                circumference_values={"waist_cm": 80.5, "chest_cm": 101},
                circumference_expanded=True,
            )
        )

        self.assertEqual(empty_text.count("未记录"), 6)
        self.assertIn("80.5 cm", historical_text)
        self.assertIn("101 cm", historical_text)

    def test_incomplete_profile_hides_metrics_prompt_so_macro_panel_is_single_notice(self):
        metrics = build_profile_metrics({
            "is_ready": False,
            "profile_message": "请完善个人资料：体重、体脂",
        })

        self.assertEqual(self._all_text_values(metrics), [])

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

    def test_profile_ui_moves_measurement_recording_to_data_page(self):
        controller = (ROOT / "src" / "profile_controller.py").read_text(encoding="utf-8-sig")
        details = (ROOT / "src" / "profile_details_views.py").read_text(encoding="utf-8-sig")
        data_controller = (ROOT / "src" / "data_record_controller.py").read_text(encoding="utf-8-sig")
        macro = (ROOT / "src" / "profile_macro_views.py").read_text(encoding="utf-8-sig")

        self.assertNotIn("def record_current_measurement", controller)
        self.assertNotIn('def save_profile_fields', controller)
        self.assertIn('"查看身体围度"', details)
        self.assertIn('"收起身体围度"', details)
        self.assertNotIn('"记录本次测量"', details)
        self.assertIn("update_circumferences(", data_controller)
        self.assertIn("一次填写所有已测量围度", data_controller)
        self.assertIn("记录围度", details)
        self.assertNotIn("记录维度", details)
        self.assertNotIn("请先完善个人资料，再计算自动宏量目标。", controller)
        self.assertIn("small_text(profile_message) if not profile_ready", macro)
        self.assertNotIn('make_button("保存", on_click=on_save', details)
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


    def test_macro_goal_controls_are_wired_in_both_profile_entries(self):
        controller = (ROOT / "src" / "profile_controller.py").read_text(encoding="utf-8-sig")

        self.assertIn("def set_macro_goal(goal):", controller)
        self.assertIn('state.get("macro_mode", "auto") != "auto"', controller)
        self.assertIn('current_goal=state.get("macro_goal", "减脂")', controller)
        self.assertIn("on_goal_change=set_macro_goal", controller)
        self.assertIn("goal_holder.content = build_carb_cycle_goal_section(", controller)
        self.assertLess(
            controller.index('small_text("运动习惯")'),
            controller.index("            goal_holder,"),
        )

if __name__ == "__main__":
    unittest.main()
