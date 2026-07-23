import unittest
from pathlib import Path

from training_models import TrainingSession
from training_summary_views import (
    TrainingWorkspaceTabsActions,
    build_today_completed_training,
    build_training_workspace_tabs,
)


SOURCE = (Path(__file__).parents[1] / "src" / "training_plan_views.py").read_text(encoding="utf-8-sig")


class TrainingPlanViewContractsTests(unittest.TestCase):
    def test_normal_card_uses_one_compact_row_with_fixed_actions(self):
        normal_start = SOURCE.index("        summary, prescription = _exercise_detail_lines(exercise)")
        normal_end = SOURCE.index("        register_target(exercise_id, row_card)", normal_start)
        normal_card = SOURCE[normal_start:normal_end]

        self.assertIn("content=ft.Row([", normal_card)
        self.assertIn("summary, prescription = _exercise_detail_lines(exercise)", normal_card)
        self.assertIn("ft.Text(summary", normal_card)
        self.assertIn("ft.Text(prescription", normal_card)
        self.assertIn("max_lines=1", normal_card)
        self.assertIn("], spacing=0, tight=True)", normal_card)
        self.assertIn("vertical_alignment=ft.CrossAxisAlignment.CENTER", normal_card)
        self.assertIn("padding=10", normal_card)
        self.assertEqual(normal_card.count("_fixed_icon_button("), 4)
        self.assertIn('ft.Icons.HELP_OUTLINE, "动作技巧"', normal_card)
        self.assertIn('ft.Icons.EDIT_OUTLINED, "编辑参数"', normal_card)
        self.assertIn("_drag_handle(", normal_card)
        self.assertEqual(normal_card.count("size=36"), 5)
        self.assertIn("size: int = 48", SOURCE)

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
