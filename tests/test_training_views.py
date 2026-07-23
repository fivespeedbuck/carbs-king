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
        select_set=_noop,
        adjust_rest=_noop,
        toggle_rest=_noop,
        skip_rest=_noop,
        adjust_weight=_noop,
        edit_weight=_noop,
        adjust_reps=_noop,
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
        self.assertNotIn("杠铃卧推", texts)
        self.assertNotIn("完成本组", texts)
        self.assertTrue(result.control.content.expand)

        rest_card = next(
            item for item in result.control.content.controls
            if isinstance(item, ft.Container) and item.data == "active-rest-card"
        )
        next_card = result.control.content.controls[-1]
        self.assertTrue(rest_card.expand)
        self.assertFalse(bool(next_card.expand))
        self.assertLess(result.control.content.controls.index(rest_card), result.control.content.controls.index(next_card))

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

    def test_short_phone_uses_compact_fixed_focus_layout(self):
        result = build_active_training(
            _model(viewport_height=720),
            _actions(),
        )

        self.assertTrue(result.control.expand)
        self.assertEqual(result.control.padding, 8)
        self.assertEqual(result.control.content.spacing, 8)
        self.assertIsNone(result.control.content.scroll)

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


if __name__ == "__main__":
    unittest.main()
