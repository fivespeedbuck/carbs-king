import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from app_version import BUILD_NUMBER, VERSION_NAME  # noqa: E402
from update_service import (  # noqa: E402
    fetch_latest_release,
    parse_build_number,
    parse_release,
    update_available,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class Build76RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.training = (SRC / "training_controller.py").read_text(encoding="utf-8-sig")
        cls.training_views = (SRC / "training_views.py").read_text(encoding="utf-8-sig")
        cls.profile = (SRC / "profile_controller.py").read_text(encoding="utf-8-sig")
        cls.details = (SRC / "profile_details_views.py").read_text(encoding="utf-8-sig")
        cls.theme = (SRC / "profile_theme_views.py").read_text(encoding="utf-8-sig")
        cls.challenge = (SRC / "profile_views.py").read_text(encoding="utf-8-sig")
        cls.analytics = (SRC / "analytics_page.py").read_text(encoding="utf-8-sig")
        cls.diet = (SRC / "diet_controller.py").read_text(encoding="utf-8-sig")
        cls.today = (SRC / "today_views.py").read_text(encoding="utf-8-sig")
        cls.plan = (SRC / "training_plan_views.py").read_text(encoding="utf-8-sig")
        cls.summary = (SRC / "training_summary_views.py").read_text(encoding="utf-8-sig")

    def test_exercise_search_keeps_all_selected_filters_and_sort(self):
        self.assertIn('search_exercises(query, selected["category"], catalog)', self.training)
        self.assertIn('if selected["subgroup"] != "全部":', self.training)
        self.assertIn('if selected["equipment"] != "全部":', self.training)
        self.assertNotIn('None if query else selected["category"]', self.training)
        self.assertIn('sort_exercises(results, usage_stats, selected["sort"])', self.training)

    def test_equipment_filters_pack_visible_rows_and_keep_more_reachable(self):
        self.assertIn("child_aspect_ratio=2.5", self.training)
        self.assertIn("def pack_equipment_controls(items, ordered_count):", self.training)
        self.assertIn("for row_index, used in enumerate(used_widths):", self.training)
        self.assertIn('compact_row = ft.Row(', self.training)
        self.assertIn('"更多器械"', self.training)
        self.assertIn('scroll=_SCROLL_HIDDEN', self.training)
        self.assertIn('content=category_rows, width=52', self.training)
        self.assertNotIn('sort_row, selection_status', self.training)
        self.assertIn('"更多器械",', self.training)
        self.assertIn('selected["equipment"] != "全部" and selected["equipment"] not in equipment', self.training)

    def test_training_entry_icons_have_visible_white_backplates(self):
        self.assertIn('size=36, color=PRIMARY), width=60, height=60, bgcolor=CARD', self.today)
        self.assertIn('size=42, color=PRIMARY)', self.plan)
        self.assertIn('width=72,', self.plan)
        self.assertIn('bgcolor=CARD,', self.plan)

    def test_completed_training_summary_uses_selected_theme_primary(self):
        self.assertIn("bgcolor=PRIMARY, border_radius=12, padding=22", self.summary)
        self.assertNotIn('bgcolor="#173E35"', self.summary)

    def test_set_details_use_separate_lines_without_squeezing_action_total(self):
        summary = (SRC / "training_summary_views.py").read_text(encoding="utf-8-sig")
        self.assertIn("Keep the label and actual value on separate lines", summary)
        self.assertIn("ft.Column([", summary)
        self.assertIn('ft.Text(value, size=12, color=TEXT, weight="bold")', summary)

    def test_action_manager_persists_reordered_exercise_list_and_cursor(self):
        self.assertIn('session["exercises"] = exercises', self.training)
        self.assertIn('current_exercise_id()', self.training)
        self.assertIn('state["training_exercise_index"] = max(0, current_index)', self.training)

    def test_active_action_manager_exposes_safe_weight_and_set_editor(self):
        self.assertIn('def open_edit_active_exercise(exercise_id):', self.training)
        self.assertIn('build_action_arrangement_list(', self.training)
        self.assertIn('组数不能截断第', self.training)
        self.assertIn('if index < locked_set_count:', self.training)
        self.assertIn('summary_controls = build_action_summary_controls(item)', self.training)
        self.assertIn('summary_controls[0]', self.training)
        self.assertIn('*summary_controls[1:]', self.training)
        self.assertNotIn('section_title("动作摘要")', self.training)

        summary_start = self.training.index("    def build_action_summary_controls(exercise):")
        summary_end = self.training.index("    def open_edit_planned_exercise", summary_start)
        summary_section = self.training[summary_start:summary_end]
        self.assertIn('bgcolor="#FFFFFF"', summary_section)
        self.assertNotIn("bgcolor=SURFACE", summary_section)

    def test_inner_and_outer_action_cards_share_native_animated_reordering(self):
        self.assertIn('def build_action_arrangement_card(', self.plan)
        self.assertIn('ft.ReorderableListView(', self.plan)
        self.assertIn('show_default_drag_handles=False', self.plan)
        self.assertIn('ft.ReorderableDragHandle', self.plan)
        self.assertNotIn('data="action-arrangement-group-member-wheel-guard"', self.plan)
        self.assertIn('data="action-arrangement-drag-region"', self.plan)
        self.assertIn('data="active-action-reorder-list"', self.training)
        self.assertNotIn('icon=ft.Icons.ARROW_UPWARD', self.training)
        self.assertNotIn('icon=ft.Icons.ARROW_DOWNWARD', self.training)

    def test_search_result_tap_dismisses_keyboard_without_clearing_state(self):
        imports = self.training[:self.training.index("CARDIO_METRIC_LABELS")]
        self.assertIn("set_input_focused", imports)
        self.assertIn("def dismiss_search_focus(after_focus=None):", self.training)
        self.assertIn('focus = getattr(target, "focus", None)', self.training)
        self.assertIn("await focus()", self.training)
        self.assertNotIn('getattr(search.field, "blur", None)', self.training)
        self.assertIn("dismiss_search_focus(show_help)", self.training)
        self.assertIn("dismiss_search_focus(apply_toggle)", self.training)

    def test_active_training_has_three_compact_management_buttons(self):
        for label in ("减一组", "加一组", "调整训练顺序"):
            self.assertIn(label, self.training_views)
        self.assertIn("def adjust_current_set_count(direction):", self.training)
        self.assertIn("def open_active_action_manager(event=None):", self.training)
        self.assertIn("open_add_exercise_dialog(after_save=open_active_action_manager)", self.training)
        self.assertIn('data="active-rest-order-action"', self.training_views)
        self.assertIn("complete_rest_if_elapsed(current_session)", self.training)
        self.assertIn('"移出组合"', self.plan)
        self.assertIn("remove_exercise_from_group", self.training)
        self.assertIn('snack("至少选择两个动作")', self.training)
        self.assertIn('snack("已解除动作组合，动作均已保留")', self.training)
        group_start = self.training.index("    def open_exercise_group_dialog")
        group_end = self.training.index("    def clear_today_training", group_start)
        self.assertNotIn("snack(str(exc))", self.training[group_start:group_end])
        self.assertIn('"增加动作"', self.training)
        self.assertIn('"已经完成过组数的动作不能删除"', self.training)

    def test_profile_settings_are_a_sibling_card_below_profile(self):
        self.assertIn('profile_card = page_card', self.details)
        self.assertIn('settings_sections = [section_title("功能设置")]', self.details)
        self.assertIn("return ft.Column([profile_card, settings_card]", self.details)
        self.assertIn("settings_sections.append(backup_panel)", self.details)
        self.assertIn("settings_sections.append(update_panel)", self.details)
        self.assertIn("update_panel=build_update_panel(", self.profile)

    def test_theme_and_challenge_panels_use_neutral_borderless_surfaces(self):
        self.assertIn("bgcolor=SURFACE", self.theme)
        self.assertIn("border=None", self.theme)
        self.assertIn("color=TEXT, expand=True", self.challenge)
        self.assertIn("border=None", self.challenge)

    def test_phone_data_filters_keep_all_six_chinese_labels_visible(self):
        self.assertIn("chart_row = ft.Row(chart_chips, spacing=6)", self.analytics)
        self.assertIn("horizontal_padding=4", self.analytics)
        self.assertNotIn("chart_chips[:3]", self.analytics)
        self.assertNotIn("chart_chips[3:]", self.analytics)
        for label in ("体重", "体脂", "围度", "饮食", "训练", "恢复"):
            self.assertIn(f'"{label}"', (SRC / "analytics_model.py").read_text(encoding="utf-8-sig"))

    def test_food_search_and_dropdown_share_android_box_metrics(self):
        self.assertIn("for control in (meal_dd, qty, search, food_dd):", self.diet)
        self.assertIn("control.height = aligned_input_height", self.diet)
        self.assertIn("for control in (meal_dd, food_dd):", self.diet)
        self.assertIn("for control in (qty, search):", self.diet)
        self.assertIn("control.field.dense = False", self.diet)
        self.assertIn("control.field.content_padding = 12", self.diet)
        self.assertIn("food_dd.field.menu_height = 300", self.diet)

    def test_runtime_build_matches_pyproject(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8-sig")
        self.assertEqual(VERSION_NAME, re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE).group(1))
        self.assertEqual(BUILD_NUMBER, int(re.search(r"^build_number = (\d+)", pyproject, re.MULTILINE).group(1)))

    def test_release_build_advances_project_and_runtime_build_numbers_together(self):
        script = (ROOT / "build_apk_update.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('throw "pyproject.toml and src/app_version.py build numbers do not match."', script)
        self.assertIn('[System.IO.File]::WriteAllText($appVersionPath, $nextAppVersionText, $utf8NoBom)', script)

    def test_release_parser_and_comparison_use_explicit_build(self):
        payload = {
            "tag_name": "v1.2.3",
            "name": "碳水大王 v1.2.3（Build 77）",
            "html_url": "https://github.com/fivespeedbuck/carbs-king/releases/tag/v1.2.3",
            "assets": [{
                "name": "carbs_king.apk",
                "browser_download_url": "https://example.invalid/carbs_king.apk",
                "size": 202000000,
                "digest": "sha256:abc123",
            }],
        }
        release = parse_release(payload)
        self.assertEqual(parse_build_number(payload["name"]), 77)
        self.assertEqual(release["build"], 77)
        self.assertEqual(release["sha256"], "ABC123")
        self.assertTrue(update_available(release, current_build=76))
        loaded = fetch_latest_release(
            use_cache=False,
            opener=lambda request, timeout: _Response(payload),
        )
        self.assertEqual(loaded["apk_name"], "carbs_king.apk")


if __name__ == "__main__":
    unittest.main()
