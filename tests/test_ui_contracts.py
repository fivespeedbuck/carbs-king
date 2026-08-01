import re
import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

import training_controller as training_controller_module  # noqa: E402
from app_state import AppState  # noqa: E402
from controller_runtime import ControllerRuntime  # noqa: E402
from training_controller import TrainingControllerDependencies, create_training_controller  # noqa: E402
from training_picker_views import (  # noqa: E402
    CUSTOM_CARDIO_METRIC_FIELDS,
    apply_training_parameter_visibility,
    bind_dialog_close_button,
    bind_training_parameter_mode,
    build_exercise_card,
    training_parameter_mode_state,
)
from training_views import _segmented_progress  # noqa: E402
from ui_components import mobile_dropdown, page_card  # noqa: E402


MAIN_SOURCE = (Path(__file__).parents[1] / "src" / "main.py").read_text(encoding="utf-8-sig")
ANALYTICS_SOURCE = "\n".join(
    (Path(__file__).parents[1] / "src" / name).read_text(encoding="utf-8-sig")
    for name in (
        "analytics_page.py",
        "analytics_ui.py",
        "analytics_trend_views.py",
        "analytics_weekly_review_views.py",
        "analytics_calendar_views.py",
        "analytics_summary_views.py",
    )
)
DIET_SOURCE = (Path(__file__).parents[1] / "src" / "diet_views.py").read_text(encoding="utf-8-sig")
DIET_CONTROLLER_SOURCE = (Path(__file__).parents[1] / "src" / "diet_controller.py").read_text(encoding="utf-8-sig")
FORM_SOURCE = (Path(__file__).parents[1] / "src" / "form_views.py").read_text(encoding="utf-8-sig")
NAV_SOURCE = (Path(__file__).parents[1] / "src" / "navigation_views.py").read_text(encoding="utf-8-sig")
RECOVERY_SOURCE = (Path(__file__).parents[1] / "src" / "recovery_controller.py").read_text(encoding="utf-8-sig")
TODAY_SOURCE = (Path(__file__).parents[1] / "src" / "today_views.py").read_text(encoding="utf-8-sig")
TODAY_CONTROLLER_SOURCE = (Path(__file__).parents[1] / "src" / "today_controller.py").read_text(encoding="utf-8-sig")
TRAINING_SOURCE = (Path(__file__).parents[1] / "src" / "training_views.py").read_text(encoding="utf-8-sig")
TRAINING_CONTROLLER_SOURCE = (Path(__file__).parents[1] / "src" / "training_controller.py").read_text(encoding="utf-8-sig")
TRAINING_PICKER_SOURCE = (Path(__file__).parents[1] / "src" / "training_picker_views.py").read_text(encoding="utf-8-sig")
UI_SOURCE = (Path(__file__).parents[1] / "src" / "ui_components.py").read_text(encoding="utf-8-sig")
PROFILE_SOURCE = (Path(__file__).parents[1] / "src" / "profile_views.py").read_text(encoding="utf-8-sig")
PROFILE_DETAILS_SOURCE = (Path(__file__).parents[1] / "src" / "profile_details_views.py").read_text(encoding="utf-8-sig")


class UiContractsTests(unittest.TestCase):
    def test_active_training_weight_has_direct_editor_and_fixed_step_controls(self):
        self.assertIn("def open_weight_editor", TRAINING_CONTROLLER_SOURCE)
        self.assertIn('adjust_weight=lambda direction: adjust_current("weight_kg", direction)', TRAINING_CONTROLLER_SOURCE)
        self.assertIn("actions.adjust_weight(-1)", TRAINING_SOURCE)
        self.assertIn("actions.adjust_weight(1)", TRAINING_SOURCE)
        self.assertIn("height=56", TRAINING_SOURCE)
        self.assertIn("on_click=actions.edit_weight", TRAINING_SOURCE)
        self.assertIn("ft.Column([field], width=responsive_width(), spacing=8, tight=True)", TRAINING_CONTROLLER_SOURCE)
    def test_flet_inputs_do_not_use_floating_labels(self):
        for source in (MAIN_SOURCE, UI_SOURCE, FORM_SOURCE):
            self.assertIsNone(re.search(r"ft\.(?:TextField|Dropdown)\([^\n]*\blabel\s*=", source))

    def test_recovery_page_owns_daily_supplements_and_supplement_library(self):
        section = RECOVERY_SOURCE
        self.assertIn("render_water()", section)
        self.assertIn("render_supp_today()", section)
        self.assertIn("render_sleep()", section)
        self.assertIn('section_title("补剂库")', section)
        self.assertIn('"新增补剂"', section)
        self.assertNotIn("render_me()", section)
        self.assertNotIn("补剂库", DIET_CONTROLLER_SOURCE)

    def test_parallel_labeled_input_rows_are_top_aligned(self):
        self.assertIn("def responsive_field_grid(", UI_SOURCE)
        self.assertIn('vertical_alignment="start"', UI_SOURCE)
        self.assertIn('quantity_unit_grid(fields["base_qty"], fields["unit"]', DIET_CONTROLLER_SOURCE)
        self.assertGreaterEqual(DIET_CONTROLLER_SOURCE.count("two_field_grid("), 5)
        self.assertIn("responsive_field_grid([", RECOVERY_SOURCE)

    def test_multifield_editors_use_fullscreen_keyboard_safe_forms(self):
        self.assertIn("def build_full_form_sheet", FORM_SOURCE)
        self.assertNotIn("def full_form_sheet", MAIN_SOURCE)
        self.assertIn("fullscreen=True", FORM_SOURCE)
        self.assertIn("maintain_bottom_view_insets_padding=True", FORM_SOURCE)
        self.assertIn("scroll=context.scroll_mode", FORM_SOURCE)
        combined = MAIN_SOURCE + DIET_CONTROLLER_SOURCE + TRAINING_CONTROLLER_SOURCE + RECOVERY_SOURCE
        for title in ("添加饮食", "设置动作", "新增食物", "新增补剂"):
            self.assertIn(title, combined)
        self.assertGreaterEqual(combined.count("full_form_sheet("), 6)

    def test_dialog_lifecycle_uses_current_flet_api_with_legacy_fallback(self):
        self.assertIn("page.show_dialog(control)", MAIN_SOURCE)
        self.assertIn("closed = page.pop_dialog()", MAIN_SOURCE)

    def test_main_scroll_surfaces_hide_scrollbars_without_disabling_scroll(self):
        self.assertIn('ScrollMode", object()), "HIDDEN", "hidden"', MAIN_SOURCE)
        self.assertIn("main_column = ft.Column(spacing=0, scroll=_SCROLL_HIDDEN, expand=True, on_scroll=remember_scroll)", MAIN_SOURCE)
        self.assertNotIn("scroll=_SCROLL_AUTO", MAIN_SOURCE)
        self.assertIn("view_scroll_offsets", MAIN_SOURCE)
        self.assertIn("on_scroll=remember_scroll", MAIN_SOURCE)
        self.assertIn("request_main_scroll(offset=view_scroll_offsets[view]", MAIN_SOURCE)
        self.assertIn("await main_column.scroll_to(**kwargs)", MAIN_SOURCE)

    def test_main_navigation_uses_bottom_tabs_without_page_swipe_preview(self):
        self.assertNotIn("PageSwipeController", NAV_SOURCE)
        self.assertNotIn("swipe_drag_offset", NAV_SOURCE)
        self.assertNotIn("preview_surface", MAIN_SOURCE)
        self.assertNotIn("on_horizontal_drag_", MAIN_SOURCE)
        self.assertIn("content=main_column", MAIN_SOURCE)

    def test_today_peer_cards_share_one_parent_spacing_and_zero_bottom_margins(self):
        self.assertIn("TODAY_SECTION_SPACING = 8", TODAY_SOURCE)
        self.assertIn("control=ft.Column([macro_card, training_card, meals_card, recovery_card], spacing=TODAY_SECTION_SPACING)", TODAY_SOURCE)
        dashboard_source = TODAY_SOURCE[TODAY_SOURCE.index("def build_today_dashboard"):]
        self.assertEqual(dashboard_source.count("bottom=0)"), 4)
        self.assertIn('controls = getattr(dashboard, "controls", None)', TODAY_CONTROLLER_SOURCE)
        self.assertIn("dashboard_controls = list(controls) if isinstance(controls, list)", TODAY_CONTROLLER_SOURCE)
        self.assertIn("ft.Column([*dashboard_controls, self.render_toolbar()], spacing=TODAY_SECTION_SPACING)", TODAY_CONTROLLER_SOURCE)

    def test_main_page_cards_match_the_data_page_edge_width(self):
        control = page_card(None)

        self.assertEqual(control.margin.left, 0)
        self.assertEqual(control.margin.right, 0)
        self.assertEqual(TODAY_SOURCE.count("margin=ft.Margin(left=0, top=0, right=0, bottom=0)"), 4)
        self.assertIn("summary = page_card(", DIET_CONTROLLER_SOURCE)
        self.assertIn("return page_card(", DIET_CONTROLLER_SOURCE)
        self.assertIn("return page_card(", TRAINING_CONTROLLER_SOURCE)
        self.assertIn("return page_card(", PROFILE_SOURCE)
        self.assertIn("profile_card = page_card(", PROFILE_DETAILS_SOURCE)
        self.assertIn("settings_card = page_card(", PROFILE_DETAILS_SOURCE)

    def test_training_rest_card_exposes_full_controls_and_stays_visible_when_paused(self):
        self.assertIn('is_resting = model.rest_status in {"running", "paused"}', TRAINING_SOURCE)
        self.assertIn('"-10秒"', TRAINING_SOURCE)
        self.assertIn('"继续" if model.rest_status == "paused" else "暂停"', TRAINING_SOURCE)
        self.assertIn('"+10秒"', TRAINING_SOURCE)
        self.assertIn('"跳过"', TRAINING_SOURCE)

    def test_completed_training_set_can_be_undone_from_main_action(self):
        self.assertIn('selected_set_done = bool(training_set and training_set.get("completed"))', TRAINING_CONTROLLER_SOURCE)
        self.assertIn('complete_or_undo=undo_current_set if selected_set_done else complete_current_set', TRAINING_CONTROLLER_SOURCE)
        self.assertIn('ask_complete=ask_complete_current', TRAINING_CONTROLLER_SOURCE)
        self.assertIn('cancel_complete=cancel_complete_current', TRAINING_CONTROLLER_SOURCE)
        self.assertIn('"确认完成"', TRAINING_SOURCE)
        self.assertIn('"取消"', TRAINING_SOURCE)
        self.assertIn('"撤销本组" if model.selected_set_done else "完成本组"', TRAINING_SOURCE)

    def test_training_set_chips_keep_48dp_touch_target(self):
        self.assertIn("width=48,", TRAINING_SOURCE)
        self.assertIn("height=48,", TRAINING_SOURCE)
        self.assertIn("border_radius=24,", TRAINING_SOURCE)

    def test_rest_completion_tick_persists_then_plays_the_foreground_cue(self):
        start = TRAINING_CONTROLLER_SOURCE.index("    def complete_rest_if_elapsed")
        end = TRAINING_CONTROLLER_SOURCE.index("    def adjust_rest", start)
        section = TRAINING_CONTROLLER_SOURCE[start:end]

        self.assertIn("persist_session(session, record_date=record_date)", section)
        self.assertIn('trigger_foreground(str(finished.get("id", "")))', section)
        self.assertNotIn("rest_notifier.cancel", section)
        self.assertNotIn("play_rest_alert", TRAINING_CONTROLLER_SOURCE)

    def test_p0_readability_tokens_keep_body_text_legible(self):
        for source in (MAIN_SOURCE, ANALYTICS_SOURCE, DIET_SOURCE, UI_SOURCE, TODAY_SOURCE, TRAINING_SOURCE):
            self.assertIsNone(re.search(r"\bsize=(?:10|11)\b", source))
        self.assertIn('TEXT = "#182420"', UI_SOURCE)
        self.assertIn('SUB = "#4F5D58"', UI_SOURCE)
        self.assertIn('CARD = "#FFFFFF"', UI_SOURCE)
        self.assertIn("PRIMARY_SOFT = ft.Colors.PRIMARY_CONTAINER", UI_SOURCE)

    def test_date_picker_uses_simplified_chinese_labels(self):
        self.assertIn('locale=ft.Locale("zh", "CN")', TODAY_CONTROLLER_SOURCE)
        self.assertIn('help_text="选择日期"', TODAY_CONTROLLER_SOURCE)
        self.assertIn('cancel_text="取消"', TODAY_CONTROLLER_SOURCE)
        self.assertIn('confirm_text="确定"', TODAY_CONTROLLER_SOURCE)

    def test_primary_surfaces_use_theme_tokens_instead_of_fixed_green(self):
        self.assertNotIn('PRIMARY = "#116E59"', DIET_SOURCE)
        self.assertNotIn('bgcolor="#116E59"', TODAY_SOURCE)
        self.assertIn("bgcolor=PRIMARY", TODAY_SOURCE)

    def test_p0_buttons_and_tabs_keep_48dp_touch_targets(self):
        self.assertIn("def make_button(text, on_click=None, icon=None, bgcolor=None, color=None, expand=False, height=48):", UI_SOURCE)
        self.assertIn("height=max(48, height)", UI_SOURCE)
        self.assertIn("border=thin_border(PRIMARY if bg == PRIMARY else BORDER)", UI_SOURCE)
        self.assertIn("ink=True", UI_SOURCE)
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
        cls.training_section = TRAINING_SOURCE

    def test_rest_card_keeps_rendering_for_paused_cycle_and_exposes_controls(self):
        self.assertIn("actions.toggle_rest", self.training_section)
        self.assertIn('is_resting = model.rest_status in {"running", "paused"}', self.training_section)
        self.assertRegex(self.training_section, r'make_button\(".*", on_click=actions.toggle_rest')
        self.assertIn("actions.adjust_rest(-10)", self.training_section)
        self.assertIn("actions.adjust_rest(10)", self.training_section)
        self.assertNotIn("if rest_seconds > 0:", self.training_section)
        self.assertIn('data="active-rest-size-reference"', self.training_section)
        self.assertIn('data="active-rest-size-match"', self.training_section)
        self.assertIn('else:\n        controls.append(work_card)', self.training_section)
        self.assertIn('small_text("下一个训练项"', self.training_section)

    def test_adding_exercise_refreshes_only_after_setup_sheet_is_dismissed(self):
        start = TRAINING_CONTROLLER_SOURCE.index('session.setdefault("exercises", []).append(exercise_entry)')
        end = TRAINING_CONTROLLER_SOURCE.index('setup_dlg = full_form_sheet(', start)
        section = TRAINING_CONTROLLER_SOURCE[start:end]
        self.assertLess(section.index("persist_session(session)"), section.index('saved_setup["message"]'))
        self.assertLess(section.index('saved_setup["message"]'), section.index("close_control(setup_dlg)"))
        self.assertNotIn("\n                refresh()", section)
        self.assertIn("setup_dlg.on_dismiss = after_setup_dismiss", TRAINING_CONTROLLER_SOURCE)

    def test_exercise_setup_has_persisted_default_rest_seconds(self):
        self.assertIn("rest = mobile_text_field(", TRAINING_CONTROLLER_SOURCE)
        self.assertIn('hint_text=str(rest_default)', TRAINING_CONTROLLER_SOURCE)
        self.assertIn("four_field_grid(weight, reps, sets, rest", TRAINING_CONTROLLER_SOURCE)
        self.assertIn('"rest_seconds": rest_seconds', TRAINING_CONTROLLER_SOURCE)
        self.assertIn("rest_notifier.trigger_after", TRAINING_CONTROLLER_SOURCE)

    def test_exercise_library_closes_before_setup_sheet_opens(self):
        start = TRAINING_CONTROLLER_SOURCE.index("        def open_setup(exercise):")
        end = TRAINING_CONTROLLER_SOURCE.index("        def exercise_row(exercise):", start)
        section = TRAINING_CONTROLLER_SOURCE[start:end]
        self.assertLess(section.index('pending_setup["dialog"] = setup_dlg'), section.index("close_control(library_dlg)"))
        self.assertIn("library_dlg.on_dismiss = after_library_dismiss", TRAINING_CONTROLLER_SOURCE)

    def test_completed_set_can_be_unlocked_from_active_training_screen(self):
        self.assertIn("complete_or_undo", self.training_section)

    def test_training_icon_buttons_keep_48dp_touch_targets(self):
        self.assertRegex(self.training_section, r"width=48,\s+height=48,\s+border_radius=24")

    def test_total_progress_is_segmented_without_growing_or_overflowing(self):
        progress = _segmented_progress(0.5, 4)
        self.assertEqual(progress.height, 8)
        self.assertEqual(progress.clip_behavior.value, "hardEdge")
        self.assertEqual(progress.content.height, 8)
        self.assertEqual(len(progress.content.controls), 4)
        self.assertEqual(progress.content.controls[0].bgcolor, "#FFD166")
        self.assertEqual(progress.content.controls[1].bgcolor, "#21A366")
        self.assertEqual(progress.content.controls[2].bgcolor, "#31413C")
        self.assertIn('color="#DCE9E4"', self.training_section)

    def test_total_progress_marks_the_actual_completed_position_after_skipping_sets(self):
        progress = _segmented_progress(
            0.25,
            4,
            current_work_index=3,
            work_completed=(False, False, True, False),
        )
        segments = progress.content.controls
        self.assertEqual(
            [segment.bgcolor for segment in segments],
            ["#31413C", "#31413C", "#21A366", "#FFD166"],
        )
        self.assertEqual(segments[2].data, "active-progress-completed")
        self.assertEqual(segments[3].data, "active-progress-current")

    def test_active_training_end_button_is_visible_safe_and_bound_to_confirmation_flow(self):
        self.assertIn("end_button = ft.Container", self.training_section)
        self.assertIn('content=ft.Text("结束", size=13, weight="bold", color="#F97066"', self.training_section)
        self.assertIn('width=64', self.training_section)
        self.assertIn('height=48', self.training_section)
        self.assertIn('bgcolor="#241B1B"', self.training_section)
        self.assertIn('border=thin_border("#F97066")', self.training_section)
        self.assertIn("on_click=actions.finish", self.training_section)
        self.assertIn('text_align="center", expand=True', self.training_section)
        self.assertIn('], alignment="spaceBetween", spacing=12)', self.training_section)

        finish_start = TRAINING_CONTROLLER_SOURCE.index("    def finish_session")
        finish_end = TRAINING_CONTROLLER_SOURCE.index("    def repeat_session", finish_start)
        finish_section = TRAINING_CONTROLLER_SOURCE[finish_start:finish_end]
        self.assertIn("completion = session_completion_state(session)", finish_section)
        self.assertIn('remaining_work = completion["remaining_work"]', finish_section)
        self.assertIn('all_completed = completion["all_sets_completed"]', finish_section)
        self.assertIn("结束训练？", finish_section)
        self.assertIn("finalize_session(not all_completed)", finish_section)
        self.assertIn("全部训练项目已完成。", finish_section)

    def test_active_training_owns_the_full_screen_background(self):
        refresh_start = MAIN_SOURCE.index("    def refresh():")
        refresh_end = MAIN_SOURCE.index("    # Root layout:", refresh_start)
        refresh_section = MAIN_SOURCE[refresh_start:refresh_end]
        self.assertIn('active_training = bool(', refresh_section)
        self.assertIn('shell_bg = "#101513" if active_training else BG', refresh_section)
        self.assertIn("page.bgcolor = shell_bg", refresh_section)
        self.assertIn("body_container.bgcolor = shell_bg", refresh_section)
        self.assertIn("populate_view(main_column, view)", refresh_section)
        self.assertEqual(MAIN_SOURCE.count("training_controller.render_page()"), 1)
        self.assertNotIn("training_controller.render_page(), ft.Container(height=8)", refresh_section)

    def test_finish_training_dialog_is_compact_and_adaptive(self):
        finish_start = TRAINING_CONTROLLER_SOURCE.index("    def finish_session")
        finish_end = TRAINING_CONTROLLER_SOURCE.index("    def repeat_session", finish_start)
        finish_section = TRAINING_CONTROLLER_SOURCE[finish_start:finish_end]
        self.assertIn("dialog_width = responsive_width()", finish_section)
        self.assertIn("width=dialog_width, spacing=8, tight=True", finish_section)
        self.assertIn("content=ft.Row([", finish_section)
        self.assertIn("width=dialog_width", finish_section)
        self.assertNotIn("height=", finish_section)

    def test_add_exercise_dialog_defaults_to_frequent_sort_and_reuses_sort_service(self):
        start = TRAINING_CONTROLLER_SOURCE.index("    def open_add_exercise_dialog(after_save=None):")
        end = TRAINING_CONTROLLER_SOURCE.index("    def reuse_history_session", start)
        section = TRAINING_CONTROLLER_SOURCE[start:end]
        self.assertIn('"sort": "frequent"', section)
        self.assertIn("sort_exercises(results, usage_stats, selected[\"sort\"])", section)
        self.assertIn('make_button("热门"', TRAINING_PICKER_SOURCE)
        self.assertNotIn('make_button("名称"', TRAINING_PICKER_SOURCE)
        self.assertIn('on_select("frequent")', TRAINING_PICKER_SOURCE)

    def test_exercise_picker_supports_multi_select_and_batch_defaults(self):
        start = TRAINING_CONTROLLER_SOURCE.index("    def open_add_exercise_dialog(after_save=None):")
        end = TRAINING_CONTROLLER_SOURCE.index("    def planned_exercise", start)
        section = TRAINING_CONTROLLER_SOURCE[start:end]

        self.assertIn("selected_names: list[str] = []", section)
        self.assertIn("def add_selected_exercises", section)
        self.assertIn("previous_defaults(exercise_name, source_exercise)", section)
        self.assertIn('save_label="添加已选动作"', section)
        self.assertIn('"新建自定义动作"', section)
        self.assertIn("def numeric_default(key, fallback_key, fallback=0):", section)
        self.assertIn('numeric_default("duration_seconds", "default_duration_seconds")', section)

    def test_selected_exercise_card_uses_check_state_and_keeps_help(self):
        calls = []
        exercise = {
            "name": "杠铃卧推",
            "equipment": "杠铃",
            "gif": "assets/exercises/gifs/barbell-bench-press.gif",
            "recording_mode": "strength",
            "default_weight_kg": 60,
            "default_reps": 8,
            "default_sets": 4,
        }
        control = build_exercise_card(
            exercise,
            {},
            lambda e: calls.append("help"),
            lambda e: calls.append("toggle"),
            selected=True,
        )
        action_column = control.content.controls[-1]
        detail_column = control.content.controls[0]
        media = control.content.controls[1]
        help_button, toggle_button = action_column.controls[0], action_column.controls[-1]

        self.assertTrue(control.ink)
        self.assertIsNotNone(control.on_click)
        self.assertEqual(control.content.vertical_alignment, training_controller_module.ft.CrossAxisAlignment.STRETCH)
        self.assertEqual(detail_column.alignment, training_controller_module.ft.MainAxisAlignment.SPACE_BETWEEN)
        self.assertEqual(detail_column.controls[0].controls[0].height, 32)
        self.assertEqual(len(detail_column.controls[1].controls), 2)
        self.assertEqual(media.data, "exercise-card-media")
        self.assertEqual(media.width, 76)
        self.assertEqual(media.content.data, "exercise-card-media-image")
        self.assertTrue(media.content.src.endswith("barbell-bench-press.gif"))
        self.assertEqual(help_button.icon, training_controller_module.ft.Icons.HELP_OUTLINE)
        self.assertEqual(toggle_button.icon, training_controller_module.ft.Icons.CHECK_CIRCLE)
        help_button.on_click(None)
        toggle_button.on_click(None)
        self.assertEqual(calls, ["help", "toggle"])

    def test_planned_cards_expose_help_and_parameter_editing(self):
        self.assertIn("def open_planned_exercise_help", TRAINING_CONTROLLER_SOURCE)
        self.assertIn("def open_edit_planned_exercise", TRAINING_CONTROLLER_SOURCE)
        self.assertIn("show_help=open_planned_exercise_help", TRAINING_CONTROLLER_SOURCE)
        self.assertIn("edit_exercise=open_edit_planned_exercise", TRAINING_CONTROLLER_SOURCE)

    def test_custom_exercise_parameter_groups_follow_recording_mode(self):
        controls = {
            key: SimpleNamespace(visible=None)
            for key in ("strength", "duration", "distance", "metrics")
        }

        strength = training_parameter_mode_state(
            "strength", is_new_custom=True, distance_enabled=True, cardio_metric_fields=[]
        )
        apply_training_parameter_visibility(strength, **controls)
        self.assertEqual(
            tuple(controls[key].visible for key in controls),
            (True, False, False, False),
        )

        timed = training_parameter_mode_state(
            "timed", is_new_custom=True, distance_enabled=True, cardio_metric_fields=[]
        )
        apply_training_parameter_visibility(timed, **controls)
        self.assertEqual(
            tuple(controls[key].visible for key in controls),
            (False, True, False, False),
        )

        cardio = training_parameter_mode_state(
            "cardio", is_new_custom=True, distance_enabled=True, cardio_metric_fields=[]
        )
        apply_training_parameter_visibility(cardio, **controls)
        self.assertEqual(
            tuple(controls[key].visible for key in controls),
            (False, True, True, True),
        )
        self.assertEqual(cardio["metric_keys"], CUSTOM_CARDIO_METRIC_FIELDS)

    def test_mobile_dropdown_and_training_mode_use_real_flet_select_event(self):
        updates = []
        mode = mobile_dropdown(
            "记录模式",
            "strength",
            [
                training_controller_module.ft.dropdown.Option("strength", "力量"),
                training_controller_module.ft.dropdown.Option("timed", "计时"),
                training_controller_module.ft.dropdown.Option("cardio", "有氧"),
            ],
        )
        controls = {
            key: training_controller_module.ft.Container(visible=False)
            for key in ("strength", "duration", "distance", "metrics")
        }
        handler = bind_training_parameter_mode(
            mode,
            is_new_custom=True,
            distance_enabled=True,
            cardio_metric_fields=CUSTOM_CARDIO_METRIC_FIELDS,
            request_update=lambda: updates.append(mode.value),
            **controls,
        )

        self.assertIs(mode.field.on_select, handler)
        self.assertIs(mode.on_change, handler)
        self.assertTrue(controls["strength"].visible)
        self.assertFalse(controls["duration"].visible)

        mode.field.on_select(SimpleNamespace(control=SimpleNamespace(value="cardio")))
        self.assertEqual(mode.value, "cardio")
        self.assertEqual(
            tuple(controls[key].visible for key in controls),
            (False, True, True, True),
        )

        mode.field.on_select(SimpleNamespace(control=SimpleNamespace(value="timed")))
        self.assertEqual(mode.value, "timed")
        self.assertEqual(
            tuple(controls[key].visible for key in controls),
            (False, True, False, False),
        )
        self.assertEqual(updates, ["cardio", "timed"])

    def test_mobile_dropdown_on_change_compatibility_binds_on_select(self):
        selected = []
        dropdown = mobile_dropdown(
            "模式",
            "strength",
            [training_controller_module.ft.dropdown.Option("strength")],
            on_change=lambda event: selected.append(event.control.value),
        )

        self.assertIsNotNone(dropdown.field.on_select)
        dropdown.field.on_select(SimpleNamespace(control=SimpleNamespace(value="strength")))
        self.assertEqual(selected, ["strength"])
        self.assertNotIn("on_change", vars(dropdown.field))

    def test_custom_cardio_only_persists_filled_metric_keys_and_keeps_canonical_fields(self):
        start = TRAINING_CONTROLLER_SOURCE.index("        def open_setup(exercise):")
        end = TRAINING_CONTROLLER_SOURCE.index("        def exercise_row(exercise):", start)
        section = TRAINING_CONTROLLER_SOURCE[start:end]
        self.assertIn('selected_metric_keys = [', section)
        self.assertIn('if selected_mode == "cardio" and str(field.value or "").strip()', section)
        self.assertIn('"recording_mode": selected_mode', section)
        self.assertIn('"sets": [{', section)
        self.assertIn('] if selected_mode == "strength" else []', section)
        self.assertIn('"duration_seconds": duration_seconds if selected_mode != "strength" else None', section)
        self.assertIn('"distance_km": max(0, to_float(distance.value)) if selected_mode == "cardio"', section)
        self.assertIn('"cardio_metric_fields": selected_metric_keys', section)
        self.assertIn('"cardio_metrics": {', section)

    def test_history_reuse_confirmation_x_has_reliable_48dp_close_handler(self):
        closed = []
        dialog = training_controller_module.build_dialog(
            "确认", SimpleNamespace(), on_close=lambda e: None
        )
        close_button = bind_dialog_close_button(dialog, lambda e: closed.append("closed"))

        self.assertEqual(close_button.width, 48)
        self.assertEqual(close_button.height, 48)
        close_button.on_click(None)
        self.assertEqual(closed, ["closed"])

        start = TRAINING_CONTROLLER_SOURCE.index("        def choose_card(card_item):")
        end = TRAINING_CONTROLLER_SOURCE.index("        def rebuild_cards():", start)
        section = TRAINING_CONTROLLER_SOURCE[start:end]
        self.assertIn("def dismiss_confirm(e=None):", section)
        self.assertIn("bind_dialog_close_button(confirm_dlg, dismiss_confirm)", section)
        self.assertIn('make_button("取消", on_click=dismiss_confirm', section)


class ActiveTrainingRuntimeRegressionTests(unittest.TestCase):
    class RestNotifierStub:
        def cancel(self, *args, **kwargs):
            return None

        def trigger_after(self, *args, **kwargs):
            return None

    def build_controller(self, session, exercise_index=0, set_index=0, opened_controls=None):
        state = AppState.default(("早餐", "午餐", "晚餐", "练前", "练后", "偷吃"))
        state["date"] = "2026-07-23"
        state["current_view"] = "training"
        state["training"]["session"] = copy.deepcopy(session)
        state["training_exercise_index"] = exercise_index
        state["training_set_index"] = set_index
        runtime = ControllerRuntime(
            page=SimpleNamespace(width=430, height=860, update=lambda: None),
            refresh=lambda: None,
            snack=lambda *args, **kwargs: None,
            navigate=lambda target: None,
            open_control=(opened_controls.append if opened_controls is not None else lambda control: None),
            close_control=lambda control: None,
            responsive_width=lambda *args, **kwargs: 340,
            responsive_bar_width=lambda: 340,
        )

        def persist_session(_record_date, updated_session):
            state["training"]["session"] = copy.deepcopy(updated_session)

        controller = create_training_controller(TrainingControllerDependencies(
            state=state,
            repositories=SimpleNamespace(),
            records={},
            runtime=runtime,
            persist_daily=lambda *args, **kwargs: None,
            persist_training_session=persist_session,
            load_date=lambda *args, **kwargs: None,
            rest_notifier=self.RestNotifierStub(),
            training_clock_refs={},
            exercise_drag_state={},
            keyboard_number=None,
            scroll_hidden=None,
            current_scroll=lambda: 0,
            scroll_to=lambda **kwargs: None,
            viewport_height=lambda: 860,
        ))
        return controller, state

    @staticmethod
    def strength_exercise(exercise_id, name, completed):
        return {
            "id": exercise_id,
            "name": name,
            "body_part": "胸",
            "recording_mode": "strength",
            "sets": [
                {"id": f"{exercise_id}-{index}", "weight_kg": 20, "reps": 10, "completed": done}
                for index, done in enumerate(completed, 1)
            ],
        }

    def active_session(self, exercises):
        return {
            "id": "session-runtime",
            "date": "2026-07-23",
            "status": "active",
            "started_at": "2026-07-23T07:00:00",
            "exercises": exercises,
            "exercise_groups": [],
        }

    def capture_render(self, controller, captures):
        original = training_controller_module.build_active_training

        def capture(model, actions):
            captures.append((model, actions))
            return original(model, actions)

        return patch.object(training_controller_module, "build_active_training", side_effect=capture)

    @staticmethod
    def find_control(control, predicate):
        if predicate(control):
            return control
        content = getattr(control, "content", None)
        if content is not None:
            match = ActiveTrainingRuntimeRegressionTests.find_control(content, predicate)
            if match is not None:
                return match
        for child in getattr(control, "controls", []) or []:
            match = ActiveTrainingRuntimeRegressionTests.find_control(child, predicate)
            if match is not None:
                return match
        return None

    @staticmethod
    def controls_of_type(control, control_type):
        matches = [control] if isinstance(control, control_type) else []
        content = getattr(control, "content", None)
        if content is not None:
            matches.extend(ActiveTrainingRuntimeRegressionTests.controls_of_type(content, control_type))
        for child in getattr(control, "controls", []) or []:
            matches.extend(ActiveTrainingRuntimeRegressionTests.controls_of_type(child, control_type))
        return matches

    def test_cardio_session_without_strength_sets_renders_without_weight_validation(self):
        cardio = {
            "id": "cardio",
            "name": "自定义爬坡",
            "body_part": "自定义",
            "recording_mode": "cardio",
            "sets": [],
            "duration_seconds": 2400,
            "distance_km": None,
            "distance_enabled": True,
            "cardio_metric_fields": ["speed_kph", "incline_percent"],
            "cardio_metrics": {"speed_kph": 4.0, "incline_percent": 20.0},
            "completed": False,
        }
        controller, _state = self.build_controller(self.active_session([cardio]))
        captures = []

        with self.capture_render(controller, captures):
            view = controller.render_page()

        self.assertIsNotNone(view)
        model = captures[-1][0]
        self.assertEqual(model.recording_mode, "cardio")
        self.assertEqual(model.weight_text, "")
        self.assertEqual(model.duration_seconds, 2400)
        self.assertEqual(model.cardio_metrics[0][2], "4")

    def test_bodyweight_strength_session_renders_without_zero_weight_error(self):
        bodyweight = self.strength_exercise("pushup", "俯卧撑", [False])
        bodyweight["sets"][0]["weight_kg"] = 0
        controller, _state = self.build_controller(self.active_session([bodyweight]))
        captures = []

        with self.capture_render(controller, captures):
            view = controller.render_page()

        self.assertIsNotNone(view)
        self.assertEqual(captures[-1][0].weight_text, "自重")

    def test_bodyweight_tap_opens_blank_editor_and_blank_save_keeps_bodyweight(self):
        bodyweight = self.strength_exercise("pushup", "俯卧撑", [False])
        bodyweight["sets"][0]["weight_kg"] = None
        opened_controls = []
        controller, state = self.build_controller(
            self.active_session([bodyweight]),
            opened_controls=opened_controls,
        )
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            captures[-1][1].edit_weight(None)

        self.assertEqual(len(opened_controls), 1)
        weight_field = self.controls_of_type(opened_controls[0], ft.TextField)[0]
        self.assertEqual(weight_field.value, "")
        self.assertEqual(weight_field.hint_text, "自重留空")
        confirm_button = opened_controls[0].actions[0].content.controls[1]
        confirm_button.on_click(None)
        self.assertEqual(
            state["training"]["session"]["exercises"][0]["sets"][0]["weight_kg"],
            0.0,
        )

    def test_completing_ordinary_set_advances_and_rerenders_after_invalid_future_set_data(self):
        current = self.strength_exercise("bench", "杠铃卧推", [False])
        following = self.strength_exercise("incline", "上斜卧推", [False])
        following["sets"].insert(0, None)
        controller, state = self.build_controller(self.active_session([current, following]))
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            actions = captures[-1][1]
            actions.ask_complete(None)
            actions.complete_or_undo(None)
            controller.render_page()

        self.assertEqual(state["training_exercise_index"], 1)
        self.assertEqual(state["training_set_index"], 0)
        self.assertEqual(captures[-1][0].exercise_name, "上斜卧推")

    def test_weight_and_reps_taps_open_editors_even_for_a_completed_set(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [True])
        opened_controls = []
        controller, _state = self.build_controller(
            self.active_session([bench]),
            opened_controls=opened_controls,
        )
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            actions = captures[-1][1]
            actions.edit_weight(None)
            actions.edit_reps(None)

        self.assertEqual(len(opened_controls), 2)

    def test_resuming_active_session_starts_at_first_pending_set(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [True, True, False, False])
        controller, state = self.build_controller(self.active_session([bench]), set_index=0)
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()

        self.assertEqual(state["training_exercise_index"], 0)
        self.assertEqual(state["training_set_index"], 2)
        self.assertEqual(captures[-1][0].selected_set_index, 2)

    def test_repeated_complete_intent_cannot_skip_the_next_set(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [False, False, False])
        controller, state = self.build_controller(self.active_session([bench]))
        captures = []

        with self.capture_render(controller, captures), patch.object(training_controller_module, "is_rapid_repeat", return_value=False):
            controller.render_page()
            actions = captures[-1][1]
            actions.ask_complete(None)
            actions.complete_or_undo(None)
            actions.ask_complete(None)
            actions.complete_or_undo(None)
            actions.complete_or_undo(None)
            controller.render_page()

        session = state["training"]["session"]
        self.assertTrue(session["exercises"][0]["sets"][0]["completed"])
        self.assertFalse(session["exercises"][0]["sets"][1]["completed"])
        self.assertFalse(session["exercises"][0]["sets"][2]["completed"])
        self.assertEqual(state["training_set_index"], 1)
        self.assertFalse(captures[-1][0].confirm_complete)
        self.assertEqual(captures[-1][0].next_work_text, "下一个：杠铃卧推 · 第 2 组")

    def test_first_set_completion_keeps_cursor_and_rest_card_on_second_set(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [False, False, False, False])
        controller, state = self.build_controller(self.active_session([bench]))
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            before, actions = captures[-1]
            self.assertEqual(before.next_work_text, "下一个：杠铃卧推 · 第 2 组")
            actions.ask_complete(None)
            actions.complete_or_undo(None)
            controller.render_page()

        after = captures[-1][0]
        self.assertEqual(state["training_exercise_index"], 0)
        self.assertEqual(state["training_set_index"], 1)
        self.assertEqual(after.completed_sets, 1)
        self.assertEqual(after.rest_status, "running")
        self.assertEqual(after.selected_set_index, 1)
        self.assertEqual(after.next_work_text, "下一个：杠铃卧推 · 第 2 组")

    def test_consecutive_sets_and_next_exercise_survive_rest_transitions(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [False, False])
        incline = self.strength_exercise("incline", "上斜卧推", [False])
        controller, state = self.build_controller(self.active_session([bench, incline]))
        captures = []

        with self.capture_render(controller, captures), patch.object(training_controller_module, "is_rapid_repeat", return_value=False):
            for expected_name, expected_set in (("杠铃卧推", 0), ("杠铃卧推", 1)):
                controller.render_page()
                model, actions = captures[-1]
                self.assertEqual((model.exercise_name, model.selected_set_index), (expected_name, expected_set))
                actions.ask_complete(None)
                actions.complete_or_undo(None)
                actions.skip_rest(None)

            controller.render_page()

        self.assertEqual(state["training_exercise_index"], 1)
        self.assertEqual(state["training_set_index"], 0)
        self.assertEqual(captures[-1][0].exercise_name, "上斜卧推")

    def test_next_work_prefers_remaining_set_before_following_exercise(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [True, False, False, False])
        incline = self.strength_exercise("incline", "上斜卧推", [False, False])
        controller, state = self.build_controller(self.active_session([bench, incline]), set_index=1)
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            self.assertEqual(captures[-1][0].next_work_text, "下一个：杠铃卧推 · 第 3 组")
            actions = captures[-1][1]
            actions.ask_complete(None)
            actions.complete_or_undo(None)
            controller.render_page()

        self.assertEqual(state["training_exercise_index"], 0)
        self.assertEqual(state["training_set_index"], 2)
        self.assertEqual(captures[-1][0].exercise_name, "杠铃卧推")
        self.assertEqual(captures[-1][0].next_work_text, "下一个：杠铃卧推 · 第 3 组")

    def test_next_work_moves_to_following_exercise_only_after_current_final_set(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [True, True, True, False])
        incline = self.strength_exercise("incline", "上斜卧推", [False, False])
        controller, _state = self.build_controller(self.active_session([bench, incline]), set_index=3)
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()

        self.assertEqual(captures[-1][0].next_work_text, "下一个：上斜卧推 · 第 1 组")

    def test_superset_next_work_keeps_round_robin_order(self):
        first = self.strength_exercise("first", "杠铃卧推", [False, False])
        second = self.strength_exercise("second", "哑铃飞鸟", [False, False])
        first.update({"group_id": "group-1", "group_order": 1})
        second.update({"group_id": "group-1", "group_order": 2})
        session = self.active_session([first, second])
        session["exercise_groups"] = [{
            "id": "group-1",
            "group_type": "superset",
            "order": 1,
            "exercise_ids": ["first", "second"],
        }]
        controller, state = self.build_controller(session)
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            self.assertIn("哑铃飞鸟 · 第 1 组", captures[-1][0].next_work_text)
            actions = captures[-1][1]
            actions.ask_complete(None)
            actions.complete_or_undo(None)
            controller.render_page()
            self.assertIn("杠铃卧推 · 第 2 组", captures[-1][0].next_work_text)

        self.assertEqual(state["training_exercise_index"], 1)
        self.assertEqual(state["training_set_index"], 0)

    def test_active_training_can_add_and_remove_only_unfinished_sets(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [True, False])
        controller, state = self.build_controller(self.active_session([bench]), set_index=1)
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            actions = captures[-1][1]
            actions.adjust_sets(1)
            self.assertEqual(len(state["training"]["session"]["exercises"][0]["sets"]), 3)
            actions.adjust_sets(-1)

        sets = state["training"]["session"]["exercises"][0]["sets"]
        self.assertEqual(len(sets), 2)
        self.assertTrue(sets[0]["completed"])
        self.assertFalse(sets[1]["completed"])

    def test_active_training_opens_fullscreen_action_order_manager(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [False])
        incline = self.strength_exercise("incline", "上斜卧推", [False])
        opened = []
        controller, _state = self.build_controller(
            self.active_session([bench, incline]),
            opened_controls=opened,
        )
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            captures[-1][1].manage_actions(None)

        self.assertEqual(len(opened), 1)
        reorder_list = self.find_control(
            opened[0],
            lambda control: getattr(control, "data", None) == "active-action-reorder-list",
        )
        self.assertIsInstance(reorder_list, ft.ReorderableListView)
        self.assertFalse(reorder_list.show_default_drag_handles)
        self.assertEqual(reorder_list.controls[0].data, "action-arrangement-drag-region")
        first_card = reorder_list.controls[0].content
        action_grid = first_card.content.content.controls[2]
        self.assertEqual(
            [button.icon for button in action_grid.controls[0].controls],
            [ft.Icons.EDIT_OUTLINED, ft.Icons.ADD],
        )
        self.assertIsInstance(action_grid.controls[1].controls[0], ft.ReorderableDragHandle)
        self.assertEqual(action_grid.controls[1].controls[1].icon, ft.Icons.DELETE_OUTLINE)

        reorder_list.on_reorder(SimpleNamespace(old_index=0, new_index=1))
        self.assertEqual(
            [item["id"] for item in _state["training"]["session"]["exercises"]],
            ["incline", "bench"],
        )

    def test_active_group_save_rebuilds_the_open_manager_immediately(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [False])
        incline = self.strength_exercise("incline", "上斜卧推", [False])
        opened = []
        controller, _state = self.build_controller(
            self.active_session([bench, incline]),
            opened_controls=opened,
        )
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            captures[-1][1].manage_actions(None)

        reorder_list = self.find_control(
            opened[0],
            lambda control: getattr(control, "data", None) == "active-action-reorder-list",
        )
        first_card = reorder_list.controls[0].content
        first_card.content.content.controls[2].controls[0].controls[1].on_click(None)
        group_sheet = opened[-1]
        checkboxes = self.controls_of_type(group_sheet, ft.Checkbox)
        self.assertEqual(len(checkboxes), 2)
        checkboxes[1].value = True
        save_button = group_sheet.content.content.controls[2].content.controls[1]
        save_button.on_click(None)

        refreshed_list = self.find_control(
            opened[0],
            lambda control: getattr(control, "data", None) == "active-action-reorder-list",
        )
        self.assertEqual(len(refreshed_list.controls), 1)
        self.assertEqual(refreshed_list.controls[0].data, "action-arrangement-group-card")

    def test_active_action_editor_preserves_every_set_through_last_completed_position(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [True, False, True, False, False])
        for training_set, weight in zip(bench["sets"], (10, 20, 30, 40, 50)):
            training_set.update({"weight_kg": weight, "reps": weight // 10 + 5})
        opened = []
        controller, state = self.build_controller(
            self.active_session([bench]),
            opened_controls=opened,
        )
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            captures[-1][1].manage_actions(None)

        card = self.find_control(
            opened[0],
            lambda control: getattr(control, "data", None) == "action-arrangement-card",
        )
        card.content.content.controls[2].controls[0].controls[0].on_click(None)
        edit_sheet = opened[-1]
        edit_body = edit_sheet.content.content.controls[1].content
        self.assertEqual(edit_body.controls[1].value, "记录模式：力量")
        self.assertIsInstance(edit_body.controls[2], ft.ResponsiveRow)
        self.assertNotIn(
            "动作摘要",
            [text.value for text in self.controls_of_type(edit_sheet, ft.Text)],
        )
        weight_field, reps_field, sets_field, rest_field = self.controls_of_type(edit_sheet, ft.TextField)
        self.assertEqual(weight_field.value, "40")
        self.assertEqual(weight_field.hint_text, "自重留空")
        self.assertEqual(weight_field.hint_style.color, "#98A39F")
        self.assertNotIn("(", weight_field.hint_text)
        self.assertNotIn(" ", weight_field.hint_text)
        self.assertEqual(rest_field.value, "90")
        save_button = edit_sheet.content.content.controls[2].content.controls[1]

        sets_field.value = "2"
        save_button.on_click(None)
        self.assertEqual(len(state["training"]["session"]["exercises"][0]["sets"]), 5)

        weight_field.value = "55"
        reps_field.value = "5"
        sets_field.value = "4"
        rest_field.value = "120"
        save_button.on_click(None)
        updated_sets = state["training"]["session"]["exercises"][0]["sets"]
        self.assertEqual(len(updated_sets), 4)
        self.assertEqual([item["weight_kg"] for item in updated_sets[:3]], [10, 20, 30])
        self.assertEqual((updated_sets[3]["weight_kg"], updated_sets[3]["reps"]), (55, 5))
        self.assertEqual(state["training"]["session"]["exercises"][0]["rest_seconds"], 120)

    def test_active_progress_preserves_the_real_completed_set_position(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [False, False, False, False])
        controller, _state = self.build_controller(self.active_session([bench]))
        captures = []

        with self.capture_render(controller, captures), patch.object(
            training_controller_module,
            "is_rapid_repeat",
            return_value=False,
        ):
            controller.render_page()
            actions = captures[-1][1]
            actions.select_set(2)
            controller.render_page()
            actions = captures[-1][1]
            actions.ask_complete(None)
            actions.complete_or_undo(None)
            controller.render_page()

        model = captures[-1][0]
        self.assertEqual(model.current_work_index, 3)
        self.assertEqual(model.work_completed, (False, False, True, False))

    def test_previous_and_next_navigate_each_set_within_one_exercise(self):
        bench = self.strength_exercise("bench", "杠铃卧推", [False, False, False])
        controller, state = self.build_controller(self.active_session([bench]), set_index=1)
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            actions = captures[-1][1]
            actions.move_exercise(-1)
            self.assertEqual((state["training_exercise_index"], state["training_set_index"]), (0, 0))
            actions.move_exercise(1)
            self.assertEqual((state["training_exercise_index"], state["training_set_index"]), (0, 1))

    def test_previous_and_next_follow_superset_round_order(self):
        first = self.strength_exercise("first", "上斜哑铃卧推", [False, False])
        second = self.strength_exercise("second", "JM推举", [False, False])
        first.update({"group_id": "group-1", "group_order": 1})
        second.update({"group_id": "group-1", "group_order": 2})
        session = self.active_session([first, second])
        session["exercise_groups"] = [{
            "id": "group-1",
            "group_type": "superset",
            "order": 1,
            "exercise_ids": ["first", "second"],
        }]
        controller, state = self.build_controller(session, exercise_index=1, set_index=0)
        captures = []

        with self.capture_render(controller, captures):
            controller.render_page()
            actions = captures[-1][1]
            actions.move_exercise(-1)
            self.assertEqual((state["training_exercise_index"], state["training_set_index"]), (0, 0))
            actions.move_exercise(1)
            self.assertEqual((state["training_exercise_index"], state["training_set_index"]), (1, 0))
            actions.move_exercise(1)
            self.assertEqual((state["training_exercise_index"], state["training_set_index"]), (0, 1))

            controller.render_page()
            self.assertEqual(captures[-1][0].current_work_index, 2)


if __name__ == "__main__":
    unittest.main()
