import unittest

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import flet as ft  # noqa: E402

from training_views import (  # noqa: E402
    ActiveTrainingActions,
    ActiveTrainingModel,
    build_active_training,
)
from ui_components import PRIMARY  # noqa: E402


def _noop(*_args, **_kwargs):
    return None


def _actions():
    return ActiveTrainingActions(
        close=_noop,
        finish=_noop,
        show_help=_noop,
        select_set=_noop,
        adjust_rest=_noop,
        toggle_rest=_noop,
        skip_rest=_noop,
        adjust_weight=_noop,
        edit_weight=_noop,
        adjust_reps=_noop,
        edit_reps=_noop,
        edit_duration=_noop,
        edit_distance=_noop,
        edit_metric=_noop,
        complete_or_undo=_noop,
        ask_complete=_noop,
        cancel_complete=_noop,
        move_exercise=_noop,
    )


def _model(**overrides):
    values = {
        "completed_sets": 1,
        "planned_sets": 4,
        "progress": 0.25,
        "elapsed_text": "05:00",
        "rest_status": "",
        "rest_seconds": 0,
        "exercise_name": "杠铃卧推",
        "exercise_index": 0,
        "exercise_count": 2,
        "sets_completed": (True, False, False, False),
        "selected_set_index": 1,
        "weight_text": "80",
        "reps": 8,
        "selected_set_done": False,
        "next_work_text": "下一个：杠铃卧推 · 第 3 组",
    }
    values.update(overrides)
    return ActiveTrainingModel(**values)


def _children(control):
    result = []
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        result.append(content)
    controls = getattr(control, "controls", None)
    if isinstance(controls, list):
        result.extend(item for item in controls if isinstance(item, ft.Control))
    return result


def _walk(control):
    yield control
    for child in _children(control):
        yield from _walk(child)


def _texts(control):
    return [item.value for item in _walk(control) if isinstance(item, ft.Text)]


class ActiveTrainingViewTests(unittest.TestCase):
    def test_rest_layout_hides_work_card_and_keeps_next_item_separate(self):
        result = build_active_training(
            _model(rest_status="running", rest_seconds=88),
            _actions(),
        )
        texts = _texts(result.control)

        self.assertIn("组间休息", texts)
        self.assertIn("下一个训练项", texts)
        self.assertIn("杠铃卧推 · 第 3 组", texts)
        self.assertTrue(result.control.content.expand)

        rest_wrapper = result.control.content.controls[-1]
        self.assertEqual(rest_wrapper.data, "active-rest-size-match")
        self.assertIsInstance(rest_wrapper, ft.Stack)
        self.assertEqual(rest_wrapper.controls[0].data, "active-rest-size-reference")
        rest_card = rest_wrapper.controls[-1]
        self.assertEqual(rest_card.data, "active-rest-card")
        self.assertIsNone(rest_card.height)
        self.assertIsInstance(rest_card.content, ft.Column)
        self.assertTrue(rest_card.content.controls[0].expand)
        self.assertEqual((rest_card.left, rest_card.top, rest_card.right, rest_card.bottom), (0, 0, 0, 0))
        bottom_group = rest_card.content.controls[-1]
        self.assertIsInstance(bottom_group.controls[0], ft.Row)
        self.assertEqual(bottom_group.controls[-1], next(item for item in _walk(rest_card) if getattr(item, "bgcolor", None) == "#252F2C" and getattr(item, "border", None) is not None))

    def test_rest_layout_uses_bounded_412_by_915_focus_viewport(self):
        result = build_active_training(
            _model(rest_status="running", rest_seconds=88, viewport_height=915),
            _actions(),
        )

        self.assertEqual(result.control.data, "active-training-surface")
        self.assertIsNone(result.control.height)
        self.assertEqual(result.control.clip_behavior, ft.ClipBehavior.HARD_EDGE)
        self.assertTrue(result.control.content.expand)
        self.assertIsNone(result.control.content.scroll)

    def test_rest_uses_the_matching_work_card_as_its_natural_size_reference(self):
        modes = ("strength", "timed", "cardio")
        for mode in modes:
            result = build_active_training(_model(recording_mode=mode, viewport_height=915), _actions())
            work_card = result.control.content.controls[-1]
            self.assertIsNone(work_card.expand)
            self.assertIsNone(work_card.height)

            resting = build_active_training(
                _model(recording_mode=mode, rest_status="running", viewport_height=915),
                _actions(),
            )
            rest_wrapper = resting.control.content.controls[-1]
            self.assertEqual(rest_wrapper.data, "active-rest-size-match")
            self.assertEqual(rest_wrapper.controls[0].content.content.__class__, work_card.content.__class__)

    def test_short_phone_uses_compact_fixed_focus_layout(self):
        result = build_active_training(
            _model(viewport_height=720),
            _actions(),
        )

        self.assertTrue(result.control.expand)
        self.assertEqual(result.control.padding, 8)
        self.assertEqual(result.control.content.spacing, 8)
        self.assertIsNone(result.control.content.scroll)
        self.assertIsNone(result.control.content.controls[-1].expand)
        self.assertIsNone(result.control.content.controls[-1].height)

        action_buttons = [
            item
            for item in _walk(result.control)
            if isinstance(item, ft.Container) and item.height == 52
        ]
        self.assertTrue(action_buttons)

    def test_main_locks_outer_scroll_only_for_active_training(self):
        main_source = (SRC / "main.py").read_text(encoding="utf-8-sig")

        self.assertIn("main_column.scroll = None if active_training else _SCROLL_HIDDEN", main_source)
        self.assertIn("main_column.on_scroll = None if active_training else remember_scroll", main_source)
        self.assertIn("if not active_training and view in view_scroll_offsets", main_source)

    def test_active_layout_shows_action_position_current_set_and_next_work(self):
        result = build_active_training(_model(), _actions())
        texts = _texts(result.control)

        self.assertIn("杠铃卧推", texts)
        self.assertIn("动作 1/2", texts)
        self.assertIn("完成本组", texts)
        self.assertIn("下一个训练项", texts)
        self.assertIn("杠铃卧推 · 第 3 组", texts)

        chip_colors = [
            item.bgcolor
            for item in _walk(result.control)
            if isinstance(item, ft.Container) and item.width == 36 and item.height == 36
        ]
        self.assertEqual(chip_colors[:2], [PRIMARY, "#C78B20"])

    def test_weight_and_reps_values_both_have_direct_edit_tap_targets(self):
        result = build_active_training(_model(), _actions())
        source = (SRC / "training_views.py").read_text(encoding="utf-8-sig")

        self.assertIn("on_click=actions.edit_weight", source)
        self.assertIn("on_click=actions.edit_reps", source)
        editable_values = [
            item for item in _walk(result.control)
            if isinstance(item, ft.Container) and item.ink and item.on_click is not None and item.height == 56
        ]
        self.assertGreaterEqual(len(editable_values), 2)

    def test_progress_bar_contains_one_separator_per_work_boundary(self):
        result = build_active_training(_model(planned_sets=4), _actions())
        separators = [
            item
            for item in _walk(result.control)
            if isinstance(item, ft.Container)
            and item.height == 8
            and item.border is not None
            and getattr(item.border, "right", None) is not None
        ]
        self.assertEqual(len(separators), 3)

    def test_progress_bar_marks_the_current_work_item_in_rest_timer_gold(self):
        result = build_active_training(
            _model(planned_sets=4, progress=0.75, current_work_index=1),
            _actions(),
        )
        marker = next(
            item for item in _walk(result.control)
            if getattr(item, "data", None) == "active-progress-current"
        )
        self.assertEqual(marker.bgcolor, "#FFD166")

    def test_active_screen_prioritizes_action_name_and_centers_timer_content(self):
        source = (SRC / "training_views.py").read_text(encoding="utf-8-sig")

        self.assertIn('size=32 if compact else 36', source)
        self.assertIn('size=28 if compact else 32', source)
        self.assertIn('horizontal_alignment=ft.CrossAxisAlignment.CENTER', source)
        self.assertIn('alignment=ft.MainAxisAlignment.CENTER', source)
        timer_start = source.index("controls = [")
        timer_end = source.index("_segmented_progress", timer_start)
        self.assertNotIn('small_text("训练时长"', source[timer_start:timer_end])

    def test_cardio_metrics_use_compact_natural_order_grid(self):
        source = (SRC / "training_views.py").read_text(encoding="utf-8-sig")
        helper_start = source.index("def _build_cardio_metric_grid")
        helper_end = source.index("\n\ndef build_active_training", helper_start)
        helper = source[helper_start:helper_end]

        self.assertIn('"时长"', helper)
        self.assertIn('"距离"', helper)
        self.assertIn('if total <= 3:', helper)
        self.assertIn('elif total == 4:', helper)
        self.assertIn('elif total == 5:', helper)
        self.assertIn('entries[:2], entries[2:]', helper)
        self.assertIn('entries[:3], entries[3:6]', helper)

    def test_cardio_grid_uses_the_required_two_to_six_item_row_shapes(self):
        metrics = (
            ("speed_kph", "速度", "8.7"),
            ("incline_percent", "坡度", "1"),
            ("cadence_rpm", "桨频", "80"),
            ("resistance_level", "阻力", "5"),
        )
        expected_shapes = {
            2: [2],
            3: [3],
            4: [2, 2],
            5: [2, 3],
            6: [3, 3],
        }
        for item_count, expected in expected_shapes.items():
            result = build_active_training(
                _model(
                    recording_mode="cardio",
                    distance_enabled=True,
                    distance_text="6.5",
                    duration_seconds=2700,
                    cardio_metrics=metrics[:item_count - 2],
                ),
                _actions(),
            )
            grid = next(item for item in _walk(result.control) if getattr(item, "data", None) == "active-cardio-metric-grid")
            self.assertEqual([len(row.controls) for row in grid.controls], expected)
            self.assertIsNone(result.control.content.scroll)

    def test_strength_superset_does_not_use_cardio_grid_and_keeps_active_help(self):
        result = build_active_training(
            _model(
                group_label="超级组",
                group_position_text="组内第 1/2 个",
                group_members=(("卧推", "a", True, False), ("划船", "b", False, False)),
            ),
            _actions(),
        )
        texts = _texts(result.control)
        self.assertIn("超级组", texts)
        self.assertFalse(any(getattr(item, "data", None) == "active-cardio-metric-grid" for item in _walk(result.control)))
        source = (SRC / "training_views.py").read_text(encoding="utf-8-sig")
        self.assertIn('tooltip="动作技巧"', source)


    def test_selected_completed_set_uses_gold_current_state_after_navigating_back(self):
        result = build_active_training(
            _model(
                sets_completed=(True, True, False, False),
                selected_set_index=0,
                selected_set_done=True,
            ),
            _actions(),
        )

        current_chip = next(
            item for item in _walk(result.control)
            if getattr(item, "data", None) == "active-set-chip-current"
        )
        completed_chip = next(
            item for item in _walk(result.control)
            if getattr(item, "data", None) == "active-set-chip-completed"
        )

        self.assertEqual(current_chip.bgcolor, "#C78B20")
        self.assertEqual(current_chip.border.top.color, "#FFD166")
        self.assertEqual(completed_chip.bgcolor, PRIMARY)
        self.assertIsNone(completed_chip.border)

    def test_superset_shows_current_member_border_and_gold_current_set_together(self):
        result = build_active_training(
            _model(
                sets_completed=(True, True, False, False),
                selected_set_index=0,
                selected_set_done=True,
                group_label="Superset",
                group_position_text="1/2",
                group_members=(("Bench", "a", True, True), ("Row", "b", False, True)),
            ),
            _actions(),
        )

        current_chip = next(
            item for item in _walk(result.control)
            if getattr(item, "data", None) == "active-set-chip-current"
        )
        current_member = next(
            item for item in _walk(result.control)
            if getattr(item, "data", None) == "active-group-member-current"
        )

        self.assertEqual(current_chip.bgcolor, "#C78B20")
        self.assertEqual(current_chip.border.top.color, "#FFD166")
        self.assertEqual(current_member.border.top.color, "#FFD166")


if __name__ == "__main__":
    unittest.main()
