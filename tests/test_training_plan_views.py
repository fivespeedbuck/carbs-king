import unittest
from pathlib import Path

import flet as ft

from training_models import TrainingSession
from form_views import build_dialog
from training_picker_views import bind_dialog_close_button
from training_summary_views import (
    TrainingSummaryActions,
    TrainingWorkspaceTabsActions,
    build_training_summary,
    build_today_completed_training,
    build_training_workspace_tabs,
)
from training_plan_views import build_action_arrangement_card, build_action_arrangement_list


SOURCE = (Path(__file__).parents[1] / "src" / "training_plan_views.py").read_text(encoding="utf-8-sig")
CONTROLLER_SOURCE = (Path(__file__).parents[1] / "src" / "training_controller.py").read_text(encoding="utf-8-sig")


class TrainingPlanViewContractsTests(unittest.TestCase):
    def test_history_reuse_dialog_close_button_works_with_flet_control_factory(self):
        dialog = build_dialog("复用历史训练", ft.Text("内容"), on_close=lambda event: None)
        button = bind_dialog_close_button(dialog, lambda event: None)

        self.assertEqual(button.width, 48)
        self.assertEqual(button.height, 48)

    def test_normal_card_keeps_content_wide_with_two_row_action_grid(self):
        normal_start = SOURCE.index("def build_action_arrangement_card")
        normal_end = SOURCE.index("\n\ndef build_action_arrangement_list", normal_start)
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
        self.assertIn("ft.Icons.EDIT_OUTLINED,", normal_card)
        self.assertIn("_drag_handle(size=32)", normal_card)
        self.assertEqual(normal_card.count("size=32"), 4)
        self.assertIn("size: int = 48", SOURCE)

    def test_group_card_removes_member_help_and_can_delete_whole_group(self):
        group_start = SOURCE.index('        if group:')
        group_end = SOURCE.index('        rendered.add(exercise_id)', group_start)
        group_card = SOURCE[group_start:group_end]

        self.assertNotIn('ft.Icons.HELP_OUTLINE, "动作技巧"', group_card)
        self.assertIn('ft.Icons.LINK_OFF, "解除组合"', group_card)
        self.assertIn("delete_group(value)", group_card)

    def test_normal_card_preserves_text_width_for_long_names(self):
        normal_start = SOURCE.index("def build_action_arrangement_card")
        normal_end = SOURCE.index("\n\ndef build_action_arrangement_list", normal_start)
        normal_card = SOURCE[normal_start:normal_end]

        self.assertIn("ft.Column(detail_controls, expand=True, spacing=1, tight=True)", normal_card)
        self.assertIn("overflow=ft.TextOverflow.ELLIPSIS", normal_card)
        self.assertEqual(normal_card.count("max_lines=1"), 3)

    def test_pre_and_in_session_arrangement_cards_shrink_long_names(self):
        noop = lambda *_args, **_kwargs: None
        exercise = {
            "id": "long-action",
            "name": "杠铃臀桥双腿部凳上（男+）",
            "recording_mode": "strength",
            "sets": [{"weight_kg": 40, "reps": 10}],
        }
        before = build_action_arrangement_card(
            exercise,
            1,
            edit_exercise=noop,
            group_exercise=noop,
            delete_exercise=noop,
        )
        active = build_action_arrangement_card(
            exercise,
            1,
            edit_exercise=noop,
            group_exercise=noop,
            delete_exercise=noop,
            completed_count=2,
        )

        for card in (before, active):
            title = card.content.controls[1].controls[0]
            self.assertEqual(title.data, "action-arrangement-title")
            self.assertLess(title.size, 16)
            self.assertGreaterEqual(title.size, 10)
            self.assertEqual(title.max_lines, 1)
            self.assertEqual(title.overflow, ft.TextOverflow.ELLIPSIS)

    def test_detail_lines_split_strength_summary_and_prescription(self):
        helper_start = SOURCE.index("def _exercise_detail_lines")
        helper_end = SOURCE.index("\n\ndef _drag_handle", helper_start)
        helper = SOURCE[helper_start:helper_end]

        self.assertIn('f"{len(sets)}组"', helper)
        self.assertIn('f"{to_float(first.get(\'weight_kg\')):g} kg ×', helper)

    def test_native_reorder_list_has_one_visible_handle_and_full_card_drag_region(self):
        self.assertIn("ft.ReorderableListView(", SOURCE)
        self.assertIn("show_default_drag_handles=False", SOURCE)
        self.assertIn("ft.ReorderableDragHandle", SOURCE)
        self.assertIn('data="action-arrangement-drag-region"', SOURCE)
        self.assertIn("auto_scroll=True", SOURCE)
        self.assertIn("on_reorder=reorder_blocks", SOURCE)
        self.assertIn("reorder_exercise(dragged_id, target_id)", SOURCE)
        self.assertNotIn("content_feedback=", SOURCE)
        self.assertNotIn("ft.Draggable(", SOURCE)

    def test_training_controller_keeps_custom_muscles_and_uses_one_history_modal(self):
        add_start = CONTROLLER_SOURCE.index("    def open_add_exercise_dialog(after_save=None):")
        add_end = CONTROLLER_SOURCE.index("    def planned_exercise", add_start)
        add_section = CONTROLLER_SOURCE[add_start:add_end]

        self.assertIn('"训练部位"', add_section)
        self.assertIn('"目标肌群"', add_section)
        self.assertIn('"器械"', add_section)
        self.assertIn('"target_muscles": [str(target_muscle.value or "其他")]', add_section)

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
        add_start = CONTROLLER_SOURCE.index("    def open_add_exercise_dialog(after_save=None):")
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
        self.assertTrue((Path(__file__).parents[1] / "assets" / "training_complete.mp3").is_file())


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
        self.assertEqual(tabs.padding.left, 0)
        self.assertEqual(tabs.padding.right, 0)
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
        self.assertIn("已完成 1/1 组 · 总容量 640 kg", texts)
        self.assertIn("第 1 组", texts)
        self.assertIn("80 kg × 8 次 = 640 kg", texts)
        self.assertIn("第 2 练 · 有氧", texts)
        self.assertIn("有氧 · 40:00 · 5 km", texts)
        start_button = view.controls[0].content.controls[1]
        start_button.on_click(None)
        self.assertEqual(calls, ["new"])

        first_delete = view.controls[1].controls[0].content.controls[0].controls[2]
        first_delete.on_click(None)
        self.assertEqual(calls, ["new", "delete:morning"])

    def test_completion_summary_keeps_each_sets_actual_weight_reps_and_volume(self):
        session = TrainingSession.from_dict({
            "id": "varied-sets",
            "date": "2026-07-29",
            "status": "completed",
            "exercises": [{
                "name": "杠铃卧推",
                "body_part": "胸",
                "recording_mode": "strength",
                "sets": [
                    {"order": 1, "weight_kg": 60, "reps": 12, "completed": True, "warmup": True},
                    {"order": 2, "weight_kg": 80, "reps": 8, "completed": True},
                    {"order": 3, "weight_kg": 85, "reps": 6, "completed": True},
                ],
            }],
        })
        view = build_training_summary(
            session,
            title="训练完成",
            duration_minutes=45,
            completed_sets=3,
            planned_sets=3,
            volume_kg=1870,
            advice="已保存",
            actions=TrainingSummaryActions(repeat=lambda e: None, create_new=lambda e: None),
        )
        texts = self.texts(view)

        self.assertIn("第 1 组 · 热身", texts)
        self.assertIn("60 kg × 12 次 = 720 kg", texts)
        self.assertIn("第 2 组", texts)
        self.assertIn("80 kg × 8 次 = 640 kg", texts)
        self.assertIn("第 3 组", texts)
        self.assertIn("85 kg × 6 次 = 510 kg", texts)
        self.assertIn("1870 kg", texts)

    def test_grouped_training_results_and_action_manager_render_one_visible_group_block(self):
        session = TrainingSession.from_dict({
            "id": "grouped",
            "date": "2026-07-29",
            "status": "completed",
            "exercises": [
                {"id": "a", "name": "杠铃臀桥双腿部凳上（男+）", "body_part": "胸", "recording_mode": "strength", "sets": [{"weight_kg": 60, "reps": 8, "completed": True}]},
                {"id": "b", "name": "哑铃划船", "body_part": "背", "recording_mode": "strength", "sets": [{"weight_kg": 30, "reps": 10, "completed": True}]},
            ],
            "exercise_groups": [{"id": "g", "group_type": "superset", "exercise_ids": ["a", "b"]}],
        })
        noop = lambda *_args, **_kwargs: None
        member_reorders = []
        removed_members = []
        manager = build_action_arrangement_list(
            session.to_dict(),
            edit_exercise=noop,
            group_exercise=noop,
            delete_exercise=noop,
            delete_group=noop,
            reorder_exercise=noop,
            reorder_group_member=lambda dragged, target: member_reorders.append((dragged, target)),
            remove_group_member=removed_members.append,
        )
        self.assertEqual(len(manager.controls), 1)
        self.assertEqual(manager.controls[0].data, "action-arrangement-group-card")
        self.assertEqual(manager.controls[0].content.controls[0].data, "action-arrangement-group-drag-region")
        member_list = manager.controls[0].content.controls[1]
        self.assertEqual(member_list.data, "action-arrangement-group-member-list")
        self.assertFalse(member_list.show_default_drag_handles)
        self.assertFalse(member_list.auto_scroll)
        self.assertEqual(member_list.item_extent, 74)
        self.assertEqual(member_list.spacing, 0)
        self.assertEqual(member_list.height, 140)
        member_list.on_reorder(type("ReorderEvent", (), {"old_index": 0, "new_index": 1})())
        self.assertEqual(member_reorders, [("a", "b")])
        first_member_row = member_list.controls[0].content.content.content
        first_member_title = first_member_row.controls[1].controls[0]
        self.assertEqual(first_member_title.data, "action-group-member-title")
        self.assertLess(first_member_title.size, 15)
        self.assertEqual(first_member_title.max_lines, 1)
        self.assertEqual(first_member_row.controls[-1].icon, ft.Icons.LINK_OFF)
        first_member_row.controls[-1].on_click(None)
        self.assertEqual(removed_members, ["a"])
        self.assertEqual(manager.height, 232)

        mixed_manager = build_action_arrangement_list(
            {
                **session.to_dict(),
                "exercises": [
                    *session.to_dict()["exercises"],
                    {
                        "id": "c",
                        "name": "杠铃深蹲",
                        "body_part": "腿",
                        "recording_mode": "strength",
                        "sets": [{"weight_kg": 80, "reps": 8}],
                    },
                ],
            },
            edit_exercise=noop,
            group_exercise=noop,
            delete_exercise=noop,
            delete_group=noop,
            reorder_exercise=noop,
            reorder_group_member=noop,
            remove_group_member=noop,
        )
        self.assertEqual(len(mixed_manager.controls), 2)
        self.assertEqual(mixed_manager.controls[0].margin.bottom, 8)
        self.assertEqual(mixed_manager.spacing, 0)

        actions = self.actions([])
        today = build_today_completed_training([session], actions)
        summary = build_training_summary(
            session,
            title="训练完成",
            duration_minutes=20,
            completed_sets=2,
            planned_sets=2,
            volume_kg=780,
            advice="已保存",
            actions=TrainingSummaryActions(repeat=noop, create_new=noop),
        )
        self.assertIn("超级组 · 2 个动作", self.texts(today))
        self.assertIn("超级组 · 2 个动作", self.texts(summary))

    def test_planned_training_uses_current_training_title(self):
        self.assertIn('ft.Text("当前的训练"', SOURCE)
        self.assertNotIn('ft.Text("今天的训练"', SOURCE)


if __name__ == "__main__":
    unittest.main()
