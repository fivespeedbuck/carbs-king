import datetime as dt
import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from training_clock_service import (  # noqa: E402
    MAX_ACTIVE_SECONDS,
    active_session_with_start,
    finalize_session_clock,
    session_elapsed_seconds,
)
from app_state import AppState  # noqa: E402
from controller_runtime import ControllerRuntime  # noqa: E402
from daily_record_controller import DailyRecordController, DailyRecordDependencies  # noqa: E402
from repositories import AppRepositories  # noqa: E402
from training_controller import TrainingControllerDependencies, create_training_controller  # noqa: E402
from training_experience_service import start_rest_cycle  # noqa: E402
from training_service import find_active_daily_session  # noqa: E402


class MemoryRepository:
    def __init__(self, value):
        self.value = value

    def load(self):
        return self.value

    def save(self, value):
        self.value = value


class NutritionStub:
    def daily_total(self):
        return {"kcal": 0, "carb": 0, "protein": 0, "fat": 0}

    def evaluate(self, total):
        return {}

    def targets(self):
        return {}


class RestNotifierStub:
    def __init__(self):
        self.foreground = []

    def trigger_foreground(self, cycle_id):
        self.foreground.append(cycle_id)

    def trigger_after(self, *args, **kwargs):
        return None

    def cancel(self, *args, **kwargs):
        return None


class TrainingClockServiceTests(unittest.TestCase):
    def setUp(self):
        self.start = dt.datetime(2026, 7, 22, 18, 0, 0)
        self.active = {"id": "session-a", "status": "active", "started_at": self.start.isoformat()}

    def test_navigation_background_and_process_restore_use_wall_clock(self):
        self.assertEqual(session_elapsed_seconds(self.active, self.start + dt.timedelta(minutes=8)), 480)
        restored = dict(self.active)
        self.assertEqual(session_elapsed_seconds(restored, self.start + dt.timedelta(minutes=27)), 1620)

    def test_finish_freezes_duration(self):
        ended = finalize_session_clock(self.active, self.start + dt.timedelta(minutes=42))
        self.assertEqual(ended["status"], "completed")
        self.assertEqual(ended["total_duration_min"], 42)
        self.assertEqual(session_elapsed_seconds(ended, self.start + dt.timedelta(days=2)), 2520)

    def test_legacy_active_session_migrates_from_safe_stored_duration(self):
        legacy = {"id": "legacy", "status": "active", "total_duration_min": 12}
        migrated, changed = active_session_with_start(legacy, self.start)
        self.assertTrue(changed)
        self.assertTrue(migrated["clock_migrated"])
        self.assertEqual(session_elapsed_seconds(migrated, self.start), 720)

    def test_clock_rollback_and_extreme_gap_are_bounded(self):
        self.assertEqual(session_elapsed_seconds(self.active, self.start - dt.timedelta(minutes=5)), 0)
        self.assertEqual(session_elapsed_seconds(self.active, self.start + dt.timedelta(days=4)), MAX_ACTIVE_SECONDS)

    def test_rest_cycle_does_not_pause_whole_workout(self):
        session = {**self.active, "rest_cycle": {"status": "paused", "paused_remaining_seconds": 30}}
        self.assertEqual(session_elapsed_seconds(session, self.start + dt.timedelta(minutes=15)), 900)

    def test_same_day_sessions_keep_independent_clocks(self):
        morning = finalize_session_clock(self.active, self.start + dt.timedelta(minutes=30))
        evening = {"id": "session-b", "status": "active", "started_at": (self.start + dt.timedelta(hours=2)).isoformat()}
        now = self.start + dt.timedelta(hours=2, minutes=20)
        self.assertEqual(session_elapsed_seconds(morning, now), 1800)
        self.assertEqual(session_elapsed_seconds(evening, now), 1200)

    def test_main_navigation_exit_does_not_finalize_session(self):
        source = (ROOT / "src" / "training_controller.py").read_text(encoding="utf-8-sig")
        close_line = 'close=lambda e: set_view("today")'
        self.assertIn(close_line, source)
        self.assertNotIn('on_click=lambda e: finalize_session', source[source.index(close_line) - 200: source.index(close_line) + 200])
        self.assertIn('training_clock_refs["elapsed"]', source)

    def test_cross_date_background_rest_completion_updates_only_active_date(self):
        meals = ("早餐", "午餐", "晚餐", "练前", "练后", "偷吃")
        current_date = "2026-07-22"
        active_date = "2026-07-21"
        now = dt.datetime(2026, 7, 22, 10, 0, 5)
        old_session = {
            "id": "session-old-day",
            "date": active_date,
            "status": "active",
            "started_at": "2026-07-21T18:00:00",
            "rest_cycle": start_rest_cycle(1, now - dt.timedelta(seconds=5)),
            "rest_until": "",
        }
        current_session = {"id": "session-current-day", "date": current_date, "status": "planned"}
        records = {
            active_date: {"date": active_date, "training": {"session": old_session, "sessions": []}},
            current_date: {
                "date": current_date,
                "calendar_event": {"type": "custom", "text": "当前日事项"},
                "training": {"session": copy.deepcopy(current_session), "sessions": []},
            },
        }
        state = AppState.default(meals)
        state["date"] = current_date
        state["training"]["session"] = copy.deepcopy(current_session)
        records_repository = MemoryRepository(records)
        repositories = AppRepositories(
            records_repository,
            MemoryRepository([]),
            MemoryRepository([]),
            MemoryRepository({}),
            MemoryRepository({}),
        )
        daily_records = DailyRecordController(DailyRecordDependencies(
            state=state,
            repositories=repositories,
            records=records,
            nutrition=NutritionStub(),
            meals=meals,
            load_profile=lambda: {},
            sleep_total_minutes=lambda: 0,
            format_minutes=lambda value: "",
            restore_training_cursor=lambda: None,
            refresh=lambda: None,
            snack=lambda *args, **kwargs: None,
        ))

        class PageStub:
            width = 430
            height = 860

        runtime = ControllerRuntime(
            page=PageStub(),
            refresh=lambda: None,
            snack=lambda *args, **kwargs: None,
            navigate=lambda target: None,
            open_control=lambda control: None,
            close_control=lambda control: None,
            responsive_width=lambda *args, **kwargs: 340,
            responsive_bar_width=lambda: 340,
        )
        notifier = RestNotifierStub()
        training = create_training_controller(TrainingControllerDependencies(
            state=state,
            repositories=repositories,
            records=records,
            runtime=runtime,
            persist_daily=daily_records.save,
            persist_training_session=daily_records.persist_training_session,
            load_date=lambda *args, **kwargs: None,
            rest_notifier=notifier,
            training_clock_refs={},
            exercise_drag_state={},
            keyboard_number=None,
            scroll_hidden=None,
            current_scroll=lambda: 0,
            scroll_to=lambda **kwargs: None,
            viewport_height=lambda: 860,
        ))
        found_date, found_session = find_active_daily_session(records)
        current_record_before = copy.deepcopy(records[current_date])
        current_state_before = copy.deepcopy(state["training"])

        changed = training.complete_rest_if_elapsed(found_session, now, record_date=found_date)

        self.assertTrue(changed)
        self.assertEqual(found_date, active_date)
        self.assertEqual(records[active_date]["training"]["session"]["rest_cycle"]["status"], "finished")
        self.assertEqual(records[current_date], current_record_before)
        self.assertEqual(state["training"], current_state_before)
        self.assertEqual(len(notifier.foreground), 1)
        main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8-sig")
        self.assertIn("complete_rest_if_elapsed(session, record_date=active_date)", main_source)


if __name__ == "__main__":
    unittest.main()
