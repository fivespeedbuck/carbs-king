import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analytics_service import (  # noqa: E402
    assess_low_carb_training,
    build_period_series,
    calendar_day_summary,
    make_body_measurement,
    normalize_body_measurement,
    summarize_daily_training,
)


def completed_set(weight=50, reps=10, *, warmup=False):
    return {"weight_kg": weight, "reps": reps, "completed": True, "warmup": warmup}


def exercise(name, body_part, sets):
    return {"name": name, "body_part": body_part, "sets": sets}


def session(identity, exercises, *, duration=60, status="completed"):
    return {
        "id": identity,
        "status": status,
        "total_duration_min": duration,
        "exercises": exercises,
    }


class DailyTrainingTests(unittest.TestCase):
    def test_merges_sessions_and_current_without_double_counting(self):
        first = session("morning", [exercise("杠铃卧推", "胸", [completed_set(60, 10)])], duration=40)
        stale = session("evening", [exercise("卷腹", "腹", [completed_set(0, 20)])], duration=10)
        current = session("evening", [exercise("绳索下压", "三头", [completed_set(20, 12)])], duration=20)
        result = summarize_daily_training({"sessions": [first, stale], "session": current}, "2026-07-21")

        self.assertEqual(result["session_count"], 2)
        self.assertEqual(result["body_part_label"], "胸 + 三头")
        self.assertEqual(result["formal_sets"], 2)
        self.assertEqual(result["volume_kg"], 840)
        self.assertEqual(result["duration_min"], 60)
        self.assertEqual(result["exercises"], ["杠铃卧推", "绳索下压"])

    def test_new_sessions_archive_summary_counts_each_completed_workout_once(self):
        morning = session("morning", [exercise("Bench", "Chest", [completed_set(50, 8)])], duration=35)
        evening = session("evening", [exercise("Row", "Back", [completed_set(40, 10)])], duration=25)
        record = {
            "training": {
                "targets": [{"target": "Legacy", "detail": "Should not be mixed into structured sessions"}],
                "sessions": [morning, evening],
                "session": evening,
            }
        }

        result = summarize_daily_training(record, "2026-07-21")

        self.assertEqual(result["session_count"], 2)
        self.assertEqual([item["id"] for item in result["sessions"]], ["morning", "evening"])
        self.assertEqual(result["formal_sets"], 2)
        self.assertEqual(result["volume_kg"], 800)
        self.assertEqual(result["duration_min"], 60)
        self.assertEqual(result["exercises"], ["Bench", "Row"])

    def test_excludes_warmup_incomplete_and_empty_shells(self):
        valid = session("valid", [exercise("深蹲", "腿", [
            completed_set(20, 10, warmup=True),
            completed_set(80, 5),
            {"weight_kg": 80, "reps": 5, "completed": False},
        ])], duration=0)
        empty = {"id": "empty", "status": "completed", "exercises": [], "total_duration_min": 0}
        planned = session("planned", [exercise("腿举", "腿", [{"weight_kg": 100, "reps": 10}])], status="planned", duration=0)
        result = summarize_daily_training({"sessions": [valid, empty, planned]})

        self.assertEqual(result["session_count"], 1)
        self.assertEqual(result["formal_sets"], 1)
        self.assertEqual(result["volume_kg"], 400)

    def test_legacy_targets_supply_names_but_not_invented_sets(self):
        training = {
            "targets": [
                {"target": "胸部", "detail": "杠铃卧推"},
                {"target": "腹部", "detail": "卷腹"},
            ],
            "total_duration_min": "55",
        }
        result = summarize_daily_training(training)

        self.assertTrue(result["has_training"])
        self.assertEqual(result["body_parts"], ["胸", "腹"])
        self.assertEqual(result["formal_sets"], 0)
        self.assertEqual(result["volume_kg"], 0)
        self.assertEqual(result["duration_min"], 55)
        self.assertFalse(result["sessions"][0]["structured"])

    def test_empty_legacy_structure_is_neither_training_nor_rest(self):
        result = summarize_daily_training({
            "targets": [{"target": "", "detail": "", "note": ""}],
            "total_duration_min": "",
            "fatigue_status": "状态一般",
        })
        self.assertFalse(result["has_training"])
        self.assertEqual(result["session_count"], 0)


class LowCarbAssessmentTests(unittest.TestCase):
    def test_warns_for_sufficient_structured_back_sets(self):
        sets = [completed_set(40, 10) for _ in range(6)]
        result = assess_low_carb_training({"session": session("back", [exercise("高位下拉", "背部", sets)])})

        self.assertTrue(result["should_warn"])
        self.assertEqual(result["formal_sets"], 6)
        self.assertEqual(result["volume_kg"], 2400)
        self.assertEqual(result["exercises"], ["高位下拉"])

    def test_volume_can_trigger_with_fewer_sets(self):
        result = assess_low_carb_training({"session": session("legs", [
            exercise("腿举", "腿", [completed_set(200, 10), completed_set(200, 10)])
        ])})
        self.assertTrue(result["should_warn"])
        self.assertEqual(result["formal_sets"], 2)

    def test_legacy_target_does_not_invent_low_carb_load(self):
        result = assess_low_carb_training({"targets": [{"target": "腿", "detail": "深蹲", "intensity": "高强度"}]})
        self.assertFalse(result["should_warn"])
        self.assertFalse(result["has_structured_leg_or_back"])

    def test_idless_sessions_are_assessed_independently(self):
        chest = session("", [exercise("卧推", "胸", [completed_set(100, 10) for _ in range(6)])])
        back = session("", [exercise("划船", "背", [completed_set(20, 10) for _ in range(6)])])
        result = assess_low_carb_training({"sessions": [chest, back]})

        self.assertTrue(result["should_warn"])
        self.assertEqual(result["formal_sets"], 6)
        self.assertEqual(result["volume_kg"], 1200)
        self.assertEqual(result["exercises"], ["划船"])


class MeasurementTests(unittest.TestCase):
    def test_canonical_measurement_is_used_for_trends(self):
        record = {"profile": {
            "weight_kg": "72.0",
            "bodyfat_percent": "18",
            "measurement": make_body_measurement(weight_kg="71.2", measured_at="2026-07-21T07:30:00+08:00"),
        }}
        result = normalize_body_measurement(record, "2026-07-21")

        self.assertTrue(result["is_measured"])
        self.assertEqual(result["weight_kg"], 71.2)
        self.assertIsNone(result["bodyfat_percent"])
        self.assertEqual(result["carried_bodyfat_percent"], 18)

    def test_unmarked_profile_values_are_carried_not_measured(self):
        result = normalize_body_measurement({"profile": {"weight_kg": "72", "bodyfat_percent": "18"}})
        self.assertFalse(result["is_measured"])
        self.assertIsNone(result["weight_kg"])
        self.assertEqual(result["carried_weight_kg"], 72)
        self.assertEqual(result["carried_bodyfat_percent"], 18)

    def test_period_body_trend_excludes_carried_values_and_keeps_explicit_measurements(self):
        records = {
            "2026-07-20": {"profile": {"weight_kg": "72", "bodyfat_percent": "18"}},
            "2026-07-21": {"profile": {
                "weight_kg": "72",
                "bodyfat_percent": "18",
                "measurement": make_body_measurement(
                    weight_kg="71.4",
                    bodyfat_percent="17.5",
                    measured_at="2026-07-21T07:30:00+08:00",
                ),
            }},
        }

        result = build_period_series(records, end_date="2026-07-21", days=7)
        carried = next(item for item in result if item["date"] == "2026-07-20")
        measured = next(item for item in result if item["date"] == "2026-07-21")

        self.assertIsNone(carried["body"])
        self.assertEqual(measured["body"]["weight_kg"], 71.4)
        self.assertEqual(measured["body"]["bodyfat_percent"], 17.5)
        self.assertEqual(measured["body"]["measured_at"], "2026-07-21T07:30:00+08:00")

    def test_profile_measured_at_is_supported_for_migration(self):
        result = normalize_body_measurement({"profile": {
            "weight_kg": "70", "bodyfat_percent": "16", "measured_at": "2026-07-20T08:00:00+08:00"
        }})
        self.assertEqual(result["weight_kg"], 70)
        self.assertEqual(result["bodyfat_percent"], 16)


class PeriodSeriesTests(unittest.TestCase):
    def test_seven_day_series_keeps_missing_days_and_metrics_none(self):
        records = {
            "2026-07-19": {
                "profile": {
                    "day_type": "中碳日",
                    "measurement": {"weight_kg": 70.5, "measured_at": "2026-07-19T08:00:00+08:00"},
                },
                "meals": {"早餐": [{"name": "燕麦"}]},
                "daily_total": {"kcal": 1800, "carb": 180, "protein": 130, "fat": 55},
                "water": {"records_ml": [500, 700]},
                "sleep": {"total_minutes": 450, "bed_time": "23:30", "wake_time": "07:00"},
            },
            "2026-07-21": {
                "profile": {"weight_kg": 70.5, "day_type": "低碳日"},
                "training": {"session": session("chest", [exercise("卧推", "胸", [completed_set(50, 10)])])},
            },
        }
        result = build_period_series(records, end_date="2026-07-21", days=7)

        self.assertEqual(len(result), 7)
        self.assertEqual(result[0]["date"], "2026-07-15")
        self.assertIsNone(result[0]["body"])
        measured = next(item for item in result if item["date"] == "2026-07-19")
        self.assertEqual(measured["body"]["weight_kg"], 70.5)
        self.assertEqual(measured["diet"]["kcal"], 1800)
        self.assertEqual(measured["recovery"]["water_ml"], 1200)
        carried = result[-1]
        self.assertIsNone(carried["body"])
        self.assertEqual(carried["training"]["body_part_label"], "胸")

    def test_all_supported_periods_and_invalid_period(self):
        for days in (7, 30, 90):
            self.assertEqual(len(build_period_series({}, end_date="2026-07-21", days=days)), days)
        with self.assertRaises(ValueError):
            build_period_series({}, end_date="2026-07-21", days=14)

    def test_zero_placeholders_do_not_become_recorded_recovery(self):
        record = {
            "2026-07-21": {
                "water": {"records_ml": [], "total_ml": 0},
                "sleep": {"total_minutes": 0, "bed_time": "", "wake_time": "", "naps": []},
                "training": {"fatigue_status": "状态一般", "targets": []},
            }
        }
        point = build_period_series(record, end_date="2026-07-21", days=7)[-1]
        self.assertIsNone(point["recovery"])


class CalendarTests(unittest.TestCase):
    def test_training_has_priority_and_compacts_three_parts(self):
        record = {
            "profile": {"day_type": "高碳日", "targets": {"calorie_target": 2100}},
            "calendar_event": {"type": "custom", "text": "公司加班"},
            "training": {"session": session("mixed", [
                exercise("卧推", "胸", [completed_set()]),
                exercise("下压", "三头", [completed_set()]),
                exercise("卷腹", "腹", [completed_set(0, 20)]),
            ])},
        }
        result = calendar_day_summary(record, "2026-07-21")

        self.assertEqual(result["day_type"], "高碳日")
        self.assertEqual(result["activity_type"], "training")
        self.assertEqual(result["activity"], "胸+三头+1")
        self.assertEqual(result["calorie_target"], 2100)
        self.assertEqual(result["event_text"], "公司加班")

    def test_calendar_target_rejects_missing_non_numeric_and_non_positive_values(self):
        for value in (None, "", "invalid", 0, -100, float("nan"), float("inf")):
            result = calendar_day_summary({"profile": {"targets": {"calorie_target": value}}})
            self.assertIsNone(result["calorie_target"])

    def test_explicit_rest_and_custom_event_are_distinct_from_empty(self):
        rest = calendar_day_summary({"profile": {"day_type": "低碳日"}, "calendar_event": {"type": "rest"}})
        custom = calendar_day_summary({"calendar_event": {"type": "custom", "text": "出差开会超过六字"}})
        empty = calendar_day_summary({"profile": {"weight_kg": "70"}})

        self.assertEqual(rest["lines"], ["低碳日", "休息"])
        self.assertEqual(custom["activity"], "出差开会超过")
        self.assertIsNone(empty["activity_type"])
        self.assertIsNone(empty["day_type"])


if __name__ == "__main__":
    unittest.main()
