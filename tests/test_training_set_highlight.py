import unittest

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import flet as ft  # noqa: E402

from training_views import ActiveTrainingActions, ActiveTrainingModel, build_active_training  # noqa: E402
from ui_components import PRIMARY  # noqa: E402


def _noop(*_args, **_kwargs):
    return None


def _actions():
    return ActiveTrainingActions(**{
        name: _noop
        for name in ActiveTrainingActions.__dataclass_fields__
    })


def _model(**overrides):
    values = {
        "completed_sets": 2,
        "planned_sets": 4,
        "progress": 0.5,
        "elapsed_text": "05:00",
        "rest_status": "",
        "rest_seconds": 0,
        "exercise_name": "单臂哑铃划船",
        "exercise_index": 2,
        "exercise_count": 8,
        "sets_completed": (True, True, False, False),
        "selected_set_index": 0,
        "weight_text": "10",
        "reps": 12,
        "selected_set_done": True,
    }
    values.update(overrides)
    return ActiveTrainingModel(**values)


def _walk(control):
    yield control
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if isinstance(controls, list):
        for child in controls:
            if isinstance(child, ft.Control):
                yield from _walk(child)


class TrainingSetHighlightContractTests(unittest.TestCase):
    def _tagged(self, result, tag):
        return [item for item in _walk(result.control) if getattr(item, "data", None) == tag]

    def test_plain_exercise_marks_only_the_selected_completed_set_gold(self):
        result = build_active_training(_model(), _actions())

        current = self._tagged(result, "active-set-chip-current")
        completed = self._tagged(result, "active-set-chip-completed")

        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].bgcolor, "#C78B20")
        self.assertEqual(current[0].border.top.color, "#FFD166")
        self.assertEqual(completed[0].bgcolor, PRIMARY)
        self.assertIsNone(completed[0].border)
        self.assertFalse(self._tagged(result, "active-group-member-current"))

    def test_superset_and_compound_keep_member_and_set_highlights_together(self):
        for group_label in ("超级组", "复合组"):
            with self.subTest(group_label=group_label):
                result = build_active_training(
                    _model(
                        group_label=group_label,
                        group_position_text="组内第 2/2 个",
                        group_members=(("高位下拉", "a", False, True), ("T 杠划船", "b", True, True)),
                    ),
                    _actions(),
                )

                current_set = self._tagged(result, "active-set-chip-current")
                current_member = self._tagged(result, "active-group-member-current")
                self.assertEqual(len(current_set), 1)
                self.assertEqual(current_set[0].bgcolor, "#C78B20")
                self.assertEqual(current_set[0].border.top.color, "#FFD166")
                self.assertEqual(len(current_member), 1)
                self.assertEqual(current_member[0].border.top.color, "#FFD166")


if __name__ == "__main__":
    unittest.main()
