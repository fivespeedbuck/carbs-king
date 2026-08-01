import copy
import sys
import unittest
from datetime import date
from pathlib import Path

import flet as ft


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_defaults import CIRCUMFERENCE_FIELDS, DEFAULT_MACRO_MULTIPLIERS  # noqa: E402
from app_state import AppState  # noqa: E402
from nutrition_service import create_nutrition_service  # noqa: E402
from profile_details_views import build_profile_details, build_profile_metrics  # noqa: E402
from storage_service import normalize_profile_age  # noqa: E402


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

    def test_profile_body_edits_also_create_today_measurement_records(self):
        controller = (ROOT / "src" / "profile_controller.py").read_text(encoding="utf-8-sig")
        details = (ROOT / "src" / "profile_details_views.py").read_text(encoding="utf-8-sig")
        data_controller = (ROOT / "src" / "data_record_controller.py").read_text(encoding="utf-8-sig")
        macro = (ROOT / "src" / "profile_macro_views.py").read_text(encoding="utf-8-sig")

        self.assertNotIn("def record_current_measurement", controller)
        self.assertNotIn('def save_profile_fields', controller)
        self.assertIn("from analytics_service import merge_body_measurement", controller)
        self.assertIn("def record_current_body_measurement", controller)
        self.assertIn("weight_changed=(field is weight_field", controller)
        self.assertIn("bodyfat_changed=(field is bodyfat_field", controller)
        self.assertIn("record_current_body_measurement(weight_changed=True, bodyfat_changed=True)", controller)
        self.assertIn('"查看身体围度"', details)
        self.assertIn('"收起身体围度"', details)
        self.assertNotIn('"记录本次测量"', details)
        self.assertIn("update_circumferences(", data_controller)
        self.assertIn("一次填写所有已测量围度", data_controller)
        self.assertNotIn("围度请在“数据 → 记录围度”中一次填写", details)
        self.assertNotIn("记录维度", details)
        self.assertNotIn("请先完善个人资料，再计算自动宏量目标。", controller)
        self.assertIn("small_text(profile_message) if not profile_ready", macro)
        self.assertNotIn('make_button("保存", on_click=on_save', details)
        self.assertIn("BMR（基础代谢率）", details)
        self.assertIn("TDEE（每日总能量消耗）", details)
        self.assertIn("if not auto_selected", macro)
        self.assertIn("蛋白按去脂体重", macro)
        self.assertIn("碳水补足剩余热量", macro)

    def test_profile_fields_use_shared_compact_aligned_grids(self):
        controller = (ROOT / "src" / "profile_controller.py").read_text(encoding="utf-8-sig")
        details = (ROOT / "src" / "profile_details_views.py").read_text(encoding="utf-8-sig")

        self.assertIn("two_field_grid(weight_box, bodyfat_box", controller)
        self.assertIn("two_field_grid(height_box, age_box", controller)
        self.assertIn("three_field_grid(carb_box, protein_box, fat_box", controller)
        self.assertIn("two_field_grid(weight_box, bodyfat_box", details)
        self.assertIn("two_field_grid(height_box, age_box", details)

    def test_body_profile_fields_auto_save_when_editing_finishes(self):
        controller = (ROOT / "src" / "profile_controller.py").read_text(encoding="utf-8-sig")

        for field in ("weight_field", "bodyfat_field", "height_field", "age_field"):
            self.assertIn(f"{field}.on_blur = persist_body_profile", controller)
        self.assertIn('state["age_reference_year"] = datetime.date.today().year', controller)
        for message in ("体重已保存", "体脂已保存", "身高已保存", "年龄已保存"):
            self.assertIn(message, controller)

    def test_age_advances_once_each_new_year(self):
        profile = {"age": "30", "age_reference_year": 2025}

        self.assertTrue(normalize_profile_age(profile, today=date(2026, 1, 1)))
        self.assertEqual(profile, {"age": "31", "age_reference_year": 2026})
        self.assertFalse(normalize_profile_age(profile, today=date(2026, 12, 31)))
        self.assertEqual(profile["age"], "31")
        self.assertTrue(normalize_profile_age(profile, today=date(2028, 1, 1)))
        self.assertEqual(profile, {"age": "33", "age_reference_year": 2028})

    def test_legacy_age_starts_new_year_tracking_without_guessing(self):
        profile = {"age": "30"}

        self.assertTrue(normalize_profile_age(profile, today=date(2026, 7, 29)))
        self.assertEqual(profile, {"age": "30", "age_reference_year": 2026})

    def test_profile_gender_options_keep_male_and_female_labels(self):
        details = (ROOT / "src" / "profile_details_views.py").read_text(encoding="utf-8-sig")

        self.assertIn('option_button("男", sex, on_sex_change)', details)
        self.assertIn('option_button("女", sex, on_sex_change)', details)
        self.assertNotIn('option_button("?", sex, on_sex_change)', details)

    def test_challenge_recommendations_default_to_all_lanes_and_filter_on_select(self):
        controller = (ROOT / "src" / "profile_controller.py").read_text(encoding="utf-8")

        self.assertIn('ft.dropdown.Option("all", "全部赛道")', controller)
        self.assertIn('mobile_dropdown("选择赛道", "all"', controller)
        self.assertIn("recommended_lane_box.on_change = change_recommendation_lane", controller)
        self.assertIn("filter_recommendations_by_lane(recommendation_templates, selected_lane)", controller)
        self.assertNotIn('mobile_dropdown("创建到赛道"', controller)

    def test_all_challenge_creation_entries_show_the_three_item_limit(self):
        controller = (ROOT / "src" / "profile_controller.py").read_text(encoding="utf-8")

        self.assertIn('if len(load_challenges().get("active", [])) >= 3:', controller)
        self.assertGreaterEqual(controller.count('snack("最多只能同时进行 3 个挑战")'), 1)
        self.assertIn('"最多三项" in str(exc)', controller)

    def test_custom_challenge_page_uses_grouped_catalog_and_metric_fields(self):
        definitions = (ROOT / "src" / "goal_challenge_definitions.py").read_text(encoding="utf-8")
        controller = (ROOT / "src" / "profile_controller.py").read_text(encoding="utf-8")

        for heading in ("基础累积", "强度突破", "密度效率", "游戏化"):
            self.assertIn(f'"group": "{heading}"', definitions)
        for title in (
            "训练总容量 (kg/lbs)", "动作总容量 (kg/lbs)", "训练总组数 (组)",
            "大重量组数 (组)", "有效连续打卡 (天)", "有氧耐力 (次)",
            "定点训练 (次)", "特殊日训练 (次)",
        ):
            self.assertIn(title, definitions)
        self.assertIn("CUSTOM_CHALLENGE_CATALOG", controller)
        self.assertIn("def open_custom_spec(spec, *, preserve_values=False):", controller)
        self.assertIn("min_weight_field.value", controller)
        self.assertIn("duration_field.value", controller)
        self.assertIn("special_dates_field.value", controller)
        self.assertIn("def open_action_picker(e=None):", controller)
        self.assertIn("catalog = exercise_catalog()", controller)
        self.assertIn("build_category_sidebar(categories", controller)
        self.assertIn("build_exercise_card(", controller)
        self.assertIn("build_sort_row(choose_sort", controller)
        self.assertIn('f"选择动作 · {len(catalog)} 个"', controller)
        self.assertIn("[search, browser_panel]", controller)
        self.assertIn('selected_action["id"] = str(exercise.get("id")', controller)
        self.assertIn('small_text("已选动作")', controller)
        self.assertNotIn("动作名称/ID", controller)
        self.assertNotIn("action_field", controller)
        self.assertIn('allowed_units = ("kg", "lbs") if default_unit == "kg" else (default_unit,)', controller)
        self.assertIn("unit_box.field.disabled = len(allowed_units) == 1", controller)
        self.assertIn("unit_box.field.height = 46", controller)
        self.assertIn("two_field_grid(target_box, unit_box, viewport_width=dialog_width)", controller)
        self.assertIn("], spacing=8, tight=True)", controller)

    def test_profile_details_removes_obsolete_circumference_tip_below_backup(self):
        details = (ROOT / "src" / "profile_details_views.py").read_text(encoding="utf-8")

        self.assertNotIn("围度请在“数据 → 记录围度”中一次填写", details)


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
