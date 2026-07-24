import unittest
from pathlib import Path

import flet as ft

from training_models import TrainingSession
from form_views import build_dialog
from training_picker_views import bind_dialog_close_button
from training_summary_views import (
    TrainingWorkspaceTabsActions,
    build_today_completed_training,
    build_training_workspace_tabs,
)


SOURCE = (Path(__file__).parents[1] / "src" / "training_plan_views.py").read_text(encoding="utf-8-sig")
CONTROLLER_SOURCE = (Path(__file__).parents[1] / "src" / "training_controller.py").read_text(encoding="utf-8-sig")


class TrainingPlanViewContractsTests(unittest.TestCase):
    def test_history_reuse_dialog_close_button_works_with_flet_control_factory(self):
        dialog = build_dialog("复用历史训练", ft.Text("内容"), on_close=lambda event: None)
        button = bind_dialog_close_button(dialog, lambda event: None)

        self.assertEqual(button.width, 48)
        self.assertEqual(button.height, 48)

    def test_normal_card_keeps_content_wide_with_two_row_action_grid(self):
        normal_start = SOURCE.index("        summary, prescription = _exercise_detail_lines(exercise)")
        normal_end = SOURCE.index("        register_target(exercise_id, row_card)", normal_start)
        normal_card = SOURCE[normal_start:normal_end]

        self.assertIn("content=ft.Row([", normal_card)
        self.assertIn("summary, prescription = _exercise_detail_lines(exercise)", normal_card)
        self.assertIn("ft.Text(summary", normal_card)
        self.assertIn("ft.Text(prescription", normal_card)
        self.assertIn("max_lines=1", normal_card)
        self.assertIn("ft.Column([", normal_card)
        self.assertIn("], spacing=0, tight=True)", normal_card)
        self.assertIn("vertical_alignment=ft.CrossAxisAlignment.CENTER", normal_card)
        self.assertIn("padding=10", normal_card)
        self.assertEqual(normal_card.count("_fixed_icon_button("), 3)
        self.assertNotIn('ft.Icons.HELP_OUTLINE, "动作技巧"', normal_card)
        self.assertIn('ft.Icons.EDIT_OUTLINED, "编辑参数"', normal_card)
        self.assertIn("_drag_handle(", normal_card)
        self.assertEqual(normal_card.count("size=32"), 4)
        self.assertIn("size: int = 48", SOURCE)

    def test_group_card_removes_member_help_and_can_delete_whole_group(self):
        group_start = SOURCE.index('        if group:')
        group_end = SOURCE.index('        rendered.add(exercise_id)', group_start)
        group_card = SOURCE[group_start:group_end]

        self.assertNotIn('ft.Icons.HELP_OUTLINE, "动作技巧"', group_card)
        self.assertIn('ft.Icons.DELETE_OUTLINE, "删除整个组合"', group_card)
        self.assertIn("actions.delete_group(value)", group_card)

    def test_normal_card_preserves_text_width_for_long_names(self):
        normal_start = SOURCE.index("        summary, prescription = _exercise_detail_lines(exercise)")
        normal_end = SOURCE.index("        register_target(exercise_id, row_card)", normal_start)
        normal_card = SOURCE[normal_start:normal_end]

        self.assertIn("], expand=True, spacing=1, tight=True)", normal_card)
        self.assertIn("overflow=ft.TextOverflow.ELLIPSIS", normal_card)
        self.assertEqual(normal_card.count("max_lines=1"), 3)

    def test_detail_lines_split_strength_summary_and_prescription(self):
        helper_start = SOURCE.index("def _exercise_detail_lines")
        helper_end = SOURCE.index("\n\ndef _drag_handle", helper_start)
        helper = SOURCE[helper_start:helper_end]

        self.assertIn('f"{len(sets)}组"', helper)
        self.assertIn('f"{to_float(first.get(\'weight_kg\')):g} kg ×', helper)

    def test_drag_hover_previews_order_but_accept_is_the_only_commit(self):
        self.assertIn("preview_session_exercise_block_order", SOURCE)
        self.assertIn("def show_drop_preview(target_id: str)", SOURCE)
        self.assertIn("exercise_list.controls = [row_targets[block_id] for block_id in preview_order]", SOURCE)
        self.assertIn("on_will_accept=", SOURCE)
        self.assertIn("on_move=", SOURCE)
        self.assertIn("on_accept=", SOURCE)
        preview_start = SOURCE.index("    def show_drop_preview")
        preview_end = SOURCE.index("    def start_drag", preview_start)
        accept_start = SOURCE.index("    def accept_preview")
        accept_end = SOURCE.index("    def complete_drag", accept_start)
        self.assertNotIn("actions.drag_accept", SOURCE[preview_start:preview_end])
        self.assertIn("actions.drag_accept(committed_target)", SOURCE[accept_start:accept_end])
        self.assertIn("animate_scale", SOURCE)
        self.assertIn("animate_opacity", SOURCE)

    def test_training_controller_keeps_custom_muscles_and_uses_one_history_modal(self):
        add_start = CONTROLLER_SOURCE.index("    def open_add_exercise_dialog():")
        add_end = CONTROLLER_SOURCE.index("    def planned_exercise", add_start)
        add_section = CONTROLLER_SOURCE[add_start:add_end]

        self.assertIn('"目标肌群（逗号或每行分隔）"', add_section)
        self.assertIn('"target_muscles": list(dict.fromkeys(parsed_target_muscles))', add_section)

        history_start = CONTROLLER_SOURCE.index("    def reuse_history_session")
        history_end = CONTROLLER_SOURCE.index("    def open_exercise_group_dialog", history_start)
        history_section = CONTROLLER_SOURCE[history_start:history_end]
        self.assertIn("close_control(history_dlg)\n            open_control(confirm_dlg)", history_section)
        self.assertIn("open_control(history_dlg)", history_section)

    def test_training_completion_uses_bundled_audio_and_active_help_callback(self):
        self.assertIn('fta.Audio(src="assets/training_complete.mp3", volume=1.0)', CONTROLLER_SOURCE)
        self.assertIn("play_completion_audio()", CONTROLLER_SOURCE)
        self.assertIn("show_help=lambda e: open_planned_exercise_help", CONTROLLER_SOURCE)

    def test_custom_library_delete_is_confirmed_and_does_not_touch_session_data(self):
        add_start = CONTROLLER_SOURCE.index("    def open_add_exercise_dialog():")
        add_end = CONTROLLER_SOURCE.index("    def planned_exercise", add_start)
        add_section = CONTROLLER_SOURCE[add_start:add_end]

        self.assertIn("def confirm_delete_custom_exercise", add_section)
        self.assertIn("删除自定义动作？", add_section)
        self.assertIn("delete_custom_exercise(exercise_name)", add_section)
        self.assertIn("历史与当前计划不受影响", add_section)

    def test_completion_audio_is_pre_attached_and_never_used_for_incomplete_finish(self):
        setup_end = CONTROLLER_SOURCE.index("    def safe_int")
        setup = CONTROLLER_SOURCE[:setup_end]
        self.assertIn('page.services.append(completion_audio["service"])', setup)

        finish_start = CONTROLLER_SOURCE.index("    def finalize_session")
        finish_end = CONTROLLER_SOURCE.index("    def finish_session", finish_start)
        finish_section = CONTROLLER_SOURCE[finish_start:finish_end]
        self.assertIn("if not incomplete:\n            play_completion_audio()", finish_section)
        self.assertNotIn("if incomplete:\n            play_completion_audio()", finish_section)
        self.assertTrue((Path(__file__).parents[1] / "src" / "assets" / "training_complete.mp3").is_file())


class TodayCompletedTrainingViewTests(unittest.TestCase):
    @staticmethod
    def actions(calls):
        return TrainingWorkspaceTabsActions(
            select_current=lambda e: calls.append("current"),
            select_completed=lambda e: calls.append("completed"),
            create_new=lambda e: calls.append("new"),
            delete_session=lambda session_id: calls.append(f"delete:{session_id}"),
        )

    @staticmethod
    def texts(control):
        values = []
        stack = [control]
        while stack:
            item = stack.pop()
            value = getattr(item, "value", None)
            if isinstance(value, str):
                values.append(value)
            content = getattr(item, "content", None)
            if content is not None:
                stack.append(content)
            stack.extend(getattr(item, "controls", []) or [])
        return values

    def test_workspace_tabs_show_current_and_completed_count(self):
        calls = []
        tabs = build_training_workspace_tabs("completed", 2, self.actions(calls))
        buttons = tabs.content.controls

        self.assertIn("当前训练", self.texts(buttons[0]))
        self.assertIn("今日已训练 2", self.texts(buttons[1]))
        buttons[0].on_click(None)
        buttons[1].on_click(None)
        self.assertEqual(calls, ["current", "completed"])

    def test_completed_view_lists_multiple_workouts_and_starts_second_session(self):
        sessions = [
            TrainingSession.from_dict({
                "id": "morning",
                "date": "2026-07-23",
                "status": "completed",
                "total_duration_min": 45,
                "exercises": [{
                    "name": "杠铃卧推",
                    "body_part": "胸",
                    "recording_mode": "strength",
                    "sets": [{"weight_kg": 80, "reps": 8, "completed": True}],
                }],
            }),
            TrainingSession.from_dict({
                "id": "evening",
                "date": "2026-07-23",
                "status": "completed",
                "total_duration_min": 40,
                "exercises": [{
                    "name": "跑步",
                    "body_part": "有氧",
                    "recording_mode": "cardio",
                    "duration_seconds": 2400,
                    "distance_km": 5,
                    "completed": True,
                }],
            }),
        ]
        calls = []
        view = build_today_completed_training(sessions, self.actions(calls))
        texts = self.texts(view)

        self.assertIn("已完成 2 场，开始二练不会覆盖已有记录。", texts)
        self.assertIn("第 1 练 · 胸", texts)
        self.assertIn("1组 · 80 kg × 8", texts)
        self.assertIn("第 2 练 · 有氧", texts)
        self.assertIn("有氧 · 40:00 · 5 km", texts)
        start_button = view.controls[0].content.controls[1]
        start_button.on_click(None)
        self.assertEqual(calls, ["new"])

        first_delete = view.controls[1].controls[0].content.controls[0].controls[2]
        first_delete.on_click(None)
        self.assertEqual(calls, ["new", "delete:morning"])

    def test_planned_training_uses_current_training_title(self):
        self.assertIn('ft.Text("当前的训练"', SOURCE)
        self.assertNotIn('ft.Text("今天的训练"', SOURCE)


if __name__ == "__main__":
    unittest.main()
