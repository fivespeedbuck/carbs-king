import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from today_controller import TodayController  # noqa: E402


def _walk(control):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)
    for child in getattr(control, "controls", []) or []:
        yield from _walk(child)


class CompletedTrainingSubtitleTests(unittest.TestCase):
    def test_strength_cardio_and_mixed_days_use_their_own_units(self):
        strength = {
            "session": {
                "id": "strength", "status": "completed", "total_duration_min": 50,
                "exercises": [{
                    "recording_mode": "strength",
                    "sets": [{"completed": True, "weight_kg": 60, "reps": 10}],
                }],
            },
        }
        cardio = {
            "session": {
                "id": "cardio", "status": "completed", "total_duration_min": 20,
                "exercises": [{
                    "recording_mode": "cardio", "completed": True, "duration_seconds": 1200,
                }],
            },
        }
        mixed = {
            "sessions": [strength["session"], cardio["session"]],
            "session": cardio["session"],
        }

        self.assertEqual(TodayController.completed_training_subtitle(strength), "1 组 · 容量 600 kg")
        self.assertEqual(TodayController.completed_training_subtitle(cardio), "有氧 20 分钟")
        self.assertEqual(TodayController.completed_training_subtitle(mixed), "1 组 · 容量 600 kg · 有氧 20 分钟")


class TodayCalendarTests(unittest.TestCase):
    def test_calendar_reuses_marked_month_grid_and_loads_the_tapped_day(self):
        opened = []
        closed = []
        loaded = []
        state = {"date": "2026-08-08"}
        records = {
            "2026-08-08": {"training": {"session": {
                "id": "workout", "status": "completed", "total_duration_min": 40,
                "exercises": [{
                    "name": "划船", "body_part": "背", "recording_mode": "strength",
                    "sets": [{"completed": True, "weight_kg": 50, "reps": 10}],
                }],
            }}},
        }
        deps = SimpleNamespace(
            state=state,
            records=records,
            runtime=SimpleNamespace(
                page=SimpleNamespace(update=lambda: None),
                open_control=opened.append,
                close_control=closed.append,
            ),
            daily_records=SimpleNamespace(load=lambda selected, show=False: loaded.append((selected, show))),
            today=lambda: __import__("datetime").date(2026, 8, 11),
        )

        TodayController(deps).open_calendar_picker()

        sheet = opened[0]
        texts = [getattr(item, "value", None) for item in _walk(sheet)]
        cells = [
            item for item in _walk(sheet)
            if getattr(item, "height", None) == 92 and getattr(item, "on_click", None) is not None
        ]
        selected = next(item for item in cells if "08" in [getattr(child, "value", None) for child in _walk(item)])

        self.assertIn("背", texts)
        self.assertIn("11", texts)
        self.assertIn("今", texts)
        self.assertNotIn("绿=记录 · 黄=休息 · 紫=选中 · 灰=空白 · 今=今天", texts)
        self.assertNotIn("训练天数", texts)
        self.assertEqual(len(sheet.content.content.controls), 2)
        selected.on_click(None)
        self.assertEqual(loaded, [("2026-08-08", True)])
        self.assertEqual(closed, [sheet])


class TodayDecisionCardTests(unittest.TestCase):
    def test_unknown_and_explicit_rest_cards_open_the_decision_dialog(self):
        for training in ({}, {"targets": [{"target": "休息", "detail": "今日休息"}]}):
            opened = []
            state = {
                "date": "2026-08-11", "day_type": "低碳日", "training": training,
                "meals": {}, "water": [], "supplements": [],
            }
            deps = SimpleNamespace(
                state=state,
                records={},
                runtime=SimpleNamespace(
                    open_control=opened.append,
                    close_control=lambda control: None,
                    navigate=lambda view: None,
                ),
                nutrition=SimpleNamespace(
                    daily_total=lambda: {"kcal": 0, "carb": 0, "protein": 0, "fat": 0},
                    targets=lambda: {
                        "day_label": "低碳日", "carb_min": 0, "carb_max": 0,
                        "protein_min": 0, "protein_max": 0, "fat_min": 0, "fat_max": 0,
                    },
                    evaluate=lambda total: {"kcal_target": 0},
                ),
                training=SimpleNamespace(
                    find_active_session_date=lambda: None,
                    session_model=lambda: None,
                    session_data=lambda: None,
                    clock_text=lambda seconds: "0:00",
                    elapsed_seconds=lambda session: 0,
                    resume_session_date=lambda record_date: None,
                ),
                recovery=SimpleNamespace(sleep_total_minutes=lambda: 0, format_minutes=lambda minutes: ""),
                daily_records=SimpleNamespace(),
                meals=(),
                responsive_bar_width=lambda: 300,
                training_clock_refs={},
            )

            TodayController(deps).render_dashboard().controls[1].on_click(None)

            self.assertEqual(len(opened), 1)
            self.assertEqual(opened[0].title.controls[0].value, "今天准备训练吗？")


if __name__ == "__main__":
    unittest.main()
