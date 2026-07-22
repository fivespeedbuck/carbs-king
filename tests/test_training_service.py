import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from training_models import (  # noqa: E402
    Exercise,
    SessionExercise,
    SetPlan,
    TemplateExercise,
    TrainingData,
    TrainingSession,
    TrainingSet,
    TrainingTemplate,
)
from training_service import (  # noqa: E402
    append_session_once,
    assess_training_carb_linkage,
    completed_set_count,
    estimated_one_rep_max,
    find_active_daily_session,
    is_rapid_repeat,
    last_performance,
    make_body_measurement,
    migrate_daily_records,
    migrate_legacy_training,
    normalize_body_measurement,
    normalize_training_data,
    personal_bests,
    planned_set_count,
    recommend_carb_day,
    session_completion_state,
    raw_training_sessions,
    session_progress,
    session_summary_title,
    session_volume,
)


def make_session(date, session_id, weight, reps, extra_weight=None):
    sets = [TrainingSet(order=1, weight_kg=weight, reps=reps, completed=True)]
    if extra_weight is not None:
        sets.append(TrainingSet(order=2, weight_kg=extra_weight, reps=5, completed=True))
    return TrainingSession(
        id=session_id,
        date=date,
        status="completed",
        exercises=[SessionExercise(
            id=f"entry-{session_id}", exercise_id="bench", name="卧推", body_part="胸", order=1, sets=sets
        )],
    )


class TrainingModelTests(unittest.TestCase):
    def test_complete_store_is_json_round_trip_compatible(self):
        store = TrainingData(
            exercises=[Exercise(id="bench", name="卧推", body_part="胸", favorite=True)],
            templates=[TrainingTemplate(
                id="push", name="推日", exercises=[TemplateExercise(
                    exercise_id="bench", name="卧推", body_part="胸", order=1,
                    sets=[SetPlan(order=1, target_reps=8, target_weight_kg=80)],
                )],
            )],
            sessions=[make_session("2026-07-20", "s1", 80, 8)],
        )
        encoded = json.dumps(store.to_dict(), ensure_ascii=False)
        restored = TrainingData.from_dict(json.loads(encoded))

        self.assertEqual(restored.exercises[0].name, "卧推")
        self.assertEqual(restored.templates[0].exercises[0].sets[0].target_reps, 8)
        self.assertEqual(restored.sessions[0].exercises[0].sets[0].weight_kg, 80)


class TrainingCalculationTests(unittest.TestCase):
    def test_volume_counts_and_progress(self):
        session = TrainingSession(date="2026-07-21", exercises=[SessionExercise(
            name="深蹲", body_part="腿", order=1, sets=[
                TrainingSet(order=1, weight_kg=40, reps=10, completed=True, warmup=True),
                TrainingSet(order=2, weight_kg=100, reps=5, completed=True),
                TrainingSet(order=3, weight_kg=100, reps=5, completed=False),
            ],
        )])

        self.assertEqual(session_volume(session), 900)
        self.assertEqual(session_volume(session, include_warmup=False), 500)
        self.assertEqual(planned_set_count(session), 3)
        self.assertEqual(completed_set_count(session), 2)
        self.assertEqual(session_progress(session), 0.6667)

    def test_estimated_one_rep_max(self):
        self.assertEqual(estimated_one_rep_max(100, 1), 100)
        self.assertEqual(estimated_one_rep_max(100, 6), 120)
        self.assertIsNone(estimated_one_rep_max(0, 6))
        self.assertIsNone(estimated_one_rep_max(100, 0))

    def test_last_performance_and_personal_bests(self):
        sessions = [
            make_session("2026-07-10", "old", 80, 10),
            make_session("2026-07-18", "new", 85, 8, extra_weight=90),
        ]

        latest = last_performance(sessions, exercise_id="bench", before_date="2026-07-21")
        bests = personal_bests(sessions, exercise_id="bench")

        self.assertEqual(latest["session_id"], "new")
        self.assertEqual(latest["completed_sets"], 2)
        self.assertEqual(bests["heaviest_set"]["set"]["weight_kg"], 90)
        self.assertEqual(bests["most_reps_set"]["set"]["reps"], 10)
        self.assertEqual(bests["best_session_volume"]["volume"], 1130)


class LegacyMigrationTests(unittest.TestCase):
    def test_empty_training_shells_do_not_create_completed_sessions(self):
        empty_shells = [
            {},
            {
                "total_duration_min": "",
                "total_calories_kcal": "",
                "fatigue_status": "状态一般",
                "summary_note": "",
                "targets": [],
            },
            {
                "status": "completed",
                "exercises": [],
                "total_duration_min": 0,
                "summary_note": "",
                "fatigue_status": "状态一般",
            },
        ]

        for training in empty_shells:
            with self.subTest(training=training):
                self.assertIsNone(migrate_legacy_training(training, "2026-07-21"))

        records = {
            "2026-07-19": {"training": empty_shells[0]},
            "2026-07-20": {"training": empty_shells[1]},
            "2026-07-21": {"training": empty_shells[2]},
        }
        self.assertEqual(migrate_daily_records(records), [])

    def test_meaningful_legacy_duration_note_or_targets_are_preserved(self):
        cases = [
            ({"total_duration_min": "45", "fatigue_status": "状态一般"}, 45, "", 0),
            ({"summary_note": "临时训练", "fatigue_status": "状态一般"}, None, "临时训练", 0),
            ({"targets": [{"target": "胸", "detail": "卧推"}]}, None, "", 1),
        ]

        for training, duration, note, exercise_count in cases:
            with self.subTest(training=training):
                session = migrate_legacy_training(training, "2026-07-21")
                self.assertIsNotNone(session)
                self.assertEqual(session.status, "completed")
                self.assertEqual(session.total_duration_min, duration)
                self.assertEqual(session.summary_note, note)
                self.assertEqual(len(session.exercises), exercise_count)

    def test_migrates_current_dict_shape_without_inventing_sets(self):
        legacy = {
            "total_duration_min": "65",
            "total_calories_kcal": "420",
            "fatigue_status": "状态好",
            "summary_note": "完成顺利",
            "targets": [{"target": "胸", "detail": "杠铃卧推", "note": "稳定", "intensity": "高强度"}],
        }

        session = migrate_legacy_training(legacy, "2026-07-20")

        self.assertEqual(session.date, "2026-07-20")
        self.assertEqual(session.total_duration_min, 65)
        self.assertEqual(session.legacy_calories_kcal, 420)
        self.assertEqual(session.exercises[0].body_part, "胸")
        self.assertEqual(session.exercises[0].legacy_detail, "杠铃卧推")
        self.assertEqual(session.exercises[0].legacy_intensity, "高强度")
        self.assertEqual(session.exercises[0].sets, [])

    def test_migrates_legacy_list_and_date_keyed_records_deterministically(self):
        records = {
            "2026-07-19": {"training": [{"target": "腿", "detail": "深蹲", "note": "", "intensity": "中等"}]},
            "2026-07-20": {"training": {}},
        }

        first = migrate_daily_records(records)
        second = migrate_daily_records(records)

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].id, second[0].id)
        self.assertEqual(first[0].exercises[0].name, "深蹲")
        self.assertEqual(normalize_training_data(records).sessions[0].date, "2026-07-19")

    def test_normalizes_new_store_without_mutating_input(self):
        payload = {"schema_version": 1, "exercises": [], "templates": [], "sessions": []}
        normalized = normalize_training_data(payload)

        self.assertEqual(normalized.to_dict(), payload)
        self.assertEqual(payload, {"schema_version": 1, "exercises": [], "templates": [], "sessions": []})


class DailySessionIntegrationTests(unittest.TestCase):
    def test_summary_title_distinguishes_incomplete_sessions(self):
        self.assertEqual(session_summary_title({"incomplete": True}), "未完整训练")
        self.assertEqual(session_summary_title({"incomplete": False}), "训练完成")
        self.assertEqual(session_summary_title({}), "训练完成")

    def test_completed_session_title_ignores_stale_incomplete_flag(self):
        complete = make_session("2026-07-21", "done", 80, 8).to_dict()
        complete["incomplete"] = True

        self.assertEqual(session_completion_state(complete)["finish_kind"], "complete")
        self.assertEqual(session_summary_title(complete), "训练完成")

    def test_same_day_sessions_are_appended_and_deduplicated(self):
        first = {"id": "morning", "status": "completed", "exercises": []}
        second = {"id": "evening", "status": "completed", "exercises": []}
        archive = append_session_once([], first)
        archive = append_session_once(archive, second)
        archive = append_session_once(archive, {**first, "summary_note": "updated"})

        self.assertEqual([item["id"] for item in archive], ["morning", "evening"])
        self.assertEqual(archive[0]["summary_note"], "updated")
        self.assertEqual(
            [item["id"] for item in raw_training_sessions({"sessions": archive, "session": second})],
            ["morning", "evening"],
        )

    def test_current_session_wins_over_stale_archive_and_double_click_is_blocked(self):
        sessions = raw_training_sessions({
            "sessions": [{"id": "active", "status": "active", "completed_sets": 1}],
            "session": {"id": "active", "status": "active", "completed_sets": 2},
        })

        self.assertEqual(sessions[0]["completed_sets"], 2)
        self.assertTrue(is_rapid_repeat(100.0, 100.2))
        self.assertFalse(is_rapid_repeat(100.0, 101.0))

    def test_active_session_is_found_across_midnight_and_in_archive(self):
        records = {
            "2026-07-20": {"training": {"sessions": [{"id": "old", "status": "active"}]}},
            "2026-07-21": {"training": {"session": {"id": "done", "status": "completed"}}},
        }

        record_date, session = find_active_daily_session(records)

        self.assertEqual(record_date, "2026-07-20")
        self.assertEqual(session["id"], "old")


class MeasurementCompatibilityTests(unittest.TestCase):
    def test_weight_and_bodyfat_measurement_flags_are_independent(self):
        record = {"profile": {
            "weight_kg": "72",
            "bodyfat_percent": "18",
            "measurement": make_body_measurement(weight_kg="71.5", measured_at="2026-07-21T07:30:00+08:00"),
        }}

        result = normalize_body_measurement(record, "2026-07-21")

        self.assertTrue(result["is_weight_measured"])
        self.assertFalse(result["is_bodyfat_measured"])
        self.assertEqual(result["weight_kg"], 71.5)
        self.assertIsNone(result["bodyfat_percent"])
        self.assertEqual(result["carried_bodyfat_percent"], 18)

    def test_bodyfat_can_be_measured_without_marking_weight(self):
        record = {"profile": {
            "weight_kg": "72",
            "bodyfat_percent": "18",
            "measurement": make_body_measurement(bodyfat_percent="17.2", measured_at="2026-07-21T07:30:00+08:00"),
        }}

        result = normalize_body_measurement(record)

        self.assertFalse(result["is_weight_measured"])
        self.assertTrue(result["is_bodyfat_measured"])
        self.assertEqual(result["carried_weight_kg"], 72)
        self.assertEqual(result["bodyfat_percent"], 17.2)


class CarbLinkageCompatibilityTests(unittest.TestCase):
    def test_high_intensity_chest_and_shoulder_participate_in_carb_linkage(self):
        result = assess_training_carb_linkage({"targets": [
            {"target": "胸部", "detail": "杠铃卧推", "intensity": "高强度"},
            {"target": "肩部", "detail": "推举", "intensity": "大重量"},
        ]})

        self.assertTrue(result["should_link"])
        self.assertEqual(result["high_intensity_exercises"], ["杠铃卧推", "推举"])

    def test_structured_chest_volume_can_trigger_carb_linkage(self):
        result = assess_training_carb_linkage(
            {"session": make_session("2026-07-21", "chest", 100, 10, extra_weight=100).to_dict()},
            min_volume_kg=1500,
        )

        self.assertTrue(result["should_link"])
        self.assertEqual(result["volume_kg"], 1500)

    def test_fixed_carb_day_mapping_uses_composite_priority(self):
        self.assertEqual(recommend_carb_day(["背", "二头"]), "高碳日")
        self.assertEqual(recommend_carb_day(["胸", "三头", "腹"]), "中碳日")
        self.assertEqual(recommend_carb_day(["二头", "腹", "有氧"]), "低碳日")

    def test_rest_is_low_carb_but_missing_training_is_not_rest(self):
        self.assertEqual(recommend_carb_day({"targets": [{"target": "休息"}]}), "低碳日")
        self.assertIsNone(recommend_carb_day({"targets": []}))


if __name__ == "__main__":
    unittest.main()
