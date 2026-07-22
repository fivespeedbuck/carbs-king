import re
import unittest
from pathlib import Path


MAIN_SOURCE = (Path(__file__).parents[1] / "src" / "main.py").read_text(encoding="utf-8-sig")
ANALYTICS_SOURCE = (Path(__file__).parents[1] / "src" / "analytics_views.py").read_text(encoding="utf-8-sig")
DIET_SOURCE = (Path(__file__).parents[1] / "src" / "diet_views.py").read_text(encoding="utf-8-sig")


class UiContractsTests(unittest.TestCase):
    def test_flet_inputs_do_not_use_floating_labels(self):
        self.assertIsNone(re.search(r"ft\.(?:TextField|Dropdown)\([^\n]*\blabel\s*=", MAIN_SOURCE))

    def test_recovery_page_contains_only_daily_recovery_sections(self):
        start = MAIN_SOURCE.index("    def render_recovery_page():")
        end = MAIN_SOURCE.index("    def render_diet_page():", start)
        section = MAIN_SOURCE[start:end]
        self.assertIn("render_water()", section)
        self.assertIn("render_supp_today()", section)
        self.assertIn("render_sleep()", section)
        self.assertNotIn("render_supp_library()", section)
        self.assertNotIn("render_me()", section)

    def test_parallel_labeled_input_rows_are_top_aligned(self):
        expected_rows = [
            'ft.Row([fields["unit"], fields["base_qty"]], spacing=8, vertical_alignment="start")',
            'ft.Row([weight, reps, sets], spacing=8, vertical_alignment="start")',
            'ft.Row([duration_field, calories_field], spacing=8, vertical_alignment="start")',
        ]
        for row in expected_rows:
            self.assertIn(row, MAIN_SOURCE)
        recovery = MAIN_SOURCE[MAIN_SOURCE.index("    def render_recovery_page():"):MAIN_SOURCE.index("    def render_diet_page():")]
        self.assertIn('ft.Column([weight, make_button("记录体重"', recovery)
        self.assertIn('ft.Column([bodyfat, make_button("记录体脂"', recovery)
        self.assertIn('], spacing=8, vertical_alignment="start")', recovery)

    def test_training_rest_card_exposes_full_controls_and_stays_visible_when_paused(self):
        start = MAIN_SOURCE.index('        if status == "active":')
        end = MAIN_SOURCE.index('        exercises = raw_session.get("exercises", [])', start)
        section = MAIN_SOURCE[start:end]

        self.assertIn('rest_visible = rest_status in {"running", "paused"}', section)
        self.assertIn('"-10秒"', section)
        self.assertIn('"继续" if rest_status == "paused" else "暂停"', section)
        self.assertIn('"+10秒"', section)
        self.assertIn('"跳过"', section)

    def test_completed_training_set_can_be_undone_from_main_action(self):
        self.assertIn('set_done = bool(training_set and training_set.get("completed"))', MAIN_SOURCE)
        self.assertIn('on_click=undo_current_set if set_done else complete_current_set', MAIN_SOURCE)
        self.assertIn('"撤销本组" if set_done else "完成本组"', MAIN_SOURCE)

    def test_training_set_chips_keep_48dp_touch_target(self):
        self.assertIn("width=48, height=48, border_radius=24", MAIN_SOURCE)

    def test_rest_notification_is_persisted_before_notifier_trigger(self):
        start = MAIN_SOURCE.index("    def complete_rest_if_elapsed")
        end = MAIN_SOURCE.index("    def adjust_rest", start)
        section = MAIN_SOURCE[start:end]

        self.assertLess(section.index("persist_session(session)"), section.index("rest_notifier.trigger"))
        self.assertIn('rest_notifier.trigger(str(finished.get("id", "")))', section)
        self.assertNotIn("play_rest_alert", MAIN_SOURCE)

    def test_p0_readability_tokens_keep_body_text_legible(self):
        for source in (MAIN_SOURCE, ANALYTICS_SOURCE, DIET_SOURCE):
            self.assertIsNone(re.search(r"\bsize=(?:10|11)\b", source))
        self.assertIn('TEXT = "#182420"', MAIN_SOURCE)
        self.assertIn('SUB = "#4F5D58"', MAIN_SOURCE)
        self.assertIn('CARD = "#FFFFFF"', MAIN_SOURCE)
        self.assertIn('PRIMARY_SOFT = "#F1F7F5"', MAIN_SOURCE)

    def test_p0_buttons_and_tabs_keep_48dp_touch_targets(self):
        self.assertIn("def make_button(text, on_click=None, icon=None, bgcolor=None, color=None, expand=False, height=48):", MAIN_SOURCE)
        self.assertIn("height=max(48, height)", MAIN_SOURCE)
        self.assertIn("border=thin_border(PRIMARY if bg == PRIMARY else BORDER)", MAIN_SOURCE)
        self.assertIn("ink=True", MAIN_SOURCE)
        self.assertIn("DIET_TAB_HEIGHT = 48", DIET_SOURCE)
        self.assertIn("height=48", ANALYTICS_SOURCE)

    def test_p0_reading_surfaces_are_opaque_not_glass(self):
        self.assertNotIn('CARD = "#F2FFFFFF"', MAIN_SOURCE)
        self.assertNotIn('bgcolor="#F2FFFFFF"', MAIN_SOURCE)
        self.assertIn("bgcolor=WHITE", ANALYTICS_SOURCE)
        self.assertIn("border=_border(BORDER)", ANALYTICS_SOURCE)


class TrainingUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start = MAIN_SOURCE.index("    def render_training_workspace():")
        end = MAIN_SOURCE.index("    def render_sleep():", start)
        cls.training_section = MAIN_SOURCE[start:end]

    def test_rest_card_keeps_rendering_for_paused_cycle_and_exposes_controls(self):
        self.assertIn("toggle_rest_pause", self.training_section)
        self.assertIn("rest_remaining_seconds(", self.training_section)
        self.assertIn('rest_status in {"running", "paused"}', self.training_section)
        self.assertRegex(self.training_section, r'make_button\(".*", on_click=toggle_rest_pause')
        self.assertIn("adjust_rest(-10)", self.training_section)
        self.assertIn("adjust_rest(10)", self.training_section)
        self.assertNotIn("if rest_seconds > 0:", self.training_section)

    def test_completed_set_can_be_unlocked_from_active_training_screen(self):
        self.assertIn("undo_current_set", self.training_section)
        self.assertIn("on_click=undo_current_set if set_done else complete_current_set", self.training_section)

    def test_training_icon_buttons_keep_48dp_touch_targets(self):
        self.assertIn("width=48, height=48, border_radius=24", self.training_section)

    def test_active_training_end_button_is_visible_safe_and_bound_to_confirmation_flow(self):
        self.assertIn("end_training_button = ft.Container", self.training_section)
        self.assertIn('content=ft.Text("结束", size=13, weight="bold", color="#F97066"', self.training_section)
        self.assertIn('width=64', self.training_section)
        self.assertIn('height=48', self.training_section)
        self.assertIn('bgcolor="#241B1B"', self.training_section)
        self.assertIn('border=thin_border("#F97066")', self.training_section)
        self.assertIn("on_click=finish_session", self.training_section)
        self.assertIn('text_align="center", expand=True', self.training_section)
        self.assertIn('], alignment="spaceBetween", spacing=12)', self.training_section)

        finish_start = MAIN_SOURCE.index("    def finish_session")
        finish_end = MAIN_SOURCE.index("    def repeat_session", finish_start)
        finish_section = MAIN_SOURCE[finish_start:finish_end]
        self.assertIn("completion = session_completion_state(session)", finish_section)
        self.assertIn('remaining = completion["remaining_sets"]', finish_section)
        self.assertIn('all_completed = completion["all_sets_completed"]', finish_section)
        self.assertIn("结束训练？", finish_section)
        self.assertIn("finalize_session(not all_completed)", finish_section)
        self.assertIn("全部训练组已完成。", finish_section)

    def test_active_training_owns_the_full_screen_background(self):
        refresh_start = MAIN_SOURCE.index("    def refresh():")
        refresh_end = MAIN_SOURCE.index("    # Root layout:", refresh_start)
        refresh_section = MAIN_SOURCE[refresh_start:refresh_end]
        self.assertIn('active_training = bool(', refresh_section)
        self.assertIn('shell_bg = "#101513" if active_training else BG', refresh_section)
        self.assertIn("page.bgcolor = shell_bg", refresh_section)
        self.assertIn("body_container.bgcolor = shell_bg", refresh_section)
        self.assertIn("main_column.controls.append(render_training_workspace())", refresh_section)
        self.assertNotIn("render_training_workspace(), ft.Container(height=8)", refresh_section)

    def test_finish_training_dialog_is_compact_and_adaptive(self):
        finish_start = MAIN_SOURCE.index("    def finish_session")
        finish_end = MAIN_SOURCE.index("    def repeat_session", finish_start)
        finish_section = MAIN_SOURCE[finish_start:finish_end]
        self.assertIn("dialog_width = responsive_width()", finish_section)
        self.assertIn("width=dialog_width, spacing=8, tight=True", finish_section)
        self.assertIn("content=ft.Row([", finish_section)
        self.assertIn("width=dialog_width", finish_section)
        self.assertNotIn("height=", finish_section)

    def test_add_exercise_dialog_defaults_to_frequent_sort_and_reuses_sort_service(self):
        start = MAIN_SOURCE.index("    def open_add_exercise_dialog():")
        end = MAIN_SOURCE.index("    def reuse_history_session", start)
        section = MAIN_SOURCE[start:end]
        self.assertIn('"sort": "frequent"', section)
        self.assertIn("sort_exercises(results, usage_stats, selected[\"sort\"])", section)
        self.assertIn('make_button("常练"', section)
        self.assertIn('choose_sort("frequent")', section)


if __name__ == "__main__":
    unittest.main()
