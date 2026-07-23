import datetime as dt
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from training_experience_service import (  # noqa: E402
    adjust_weight_kg,
    adjust_rest_cycle,
    copy_whole_session,
    create_exercise_group,
    exercise_usage_stats,
    finish_rest_cycle,
    format_weight_kg,
    history_training_cards,
    normalize_weight_input,
    normalize_exercise_groups,
    next_group_work,
    pause_rest_cycle,
    preview_session_exercise_block_order,
    reorder_session_exercise_blocks,
    reorder_session_exercises,
    rest_remaining_seconds,
    resume_rest_cycle,
    skip_rest_cycle,
    sort_exercises,
    start_rest_cycle,
    undo_completed_set,
    undo_completed_set_result,
)


def session(session_id, date, parts, *, status="completed", completed=True):
    exercises = []
    for index, part in enumerate(parts, 1):
        exercises.append({
            "id": f"exercise-{session_id}-{index}", "exercise_id": f"lib-{part}",
            "name": f"{part}动作", "body_part": part, "order": index,
            "sets": [{
                "id": f"set-{session_id}-{index}", "order": 1, "weight_kg": 20,
                "reps": 10, "completed": completed, "completed_at": f"{date}T10:00:00" if completed else "",
                "warmup": False, "rir": 2, "rpe": 8,
            }],
        })
    return {
        "id": session_id, "date": date, "status": status, "started_at": f"{date}T09:00:00",
        "ended_at": f"{date}T10:00:00", "total_duration_min": 60, "exercises": exercises,
        "summary_note": "done", "fatigue_status": "good", "rest_until": "later", "incomplete": False,
    }


class HistoryCardTests(unittest.TestCase):
    def test_latest_whole_combination_and_part_filter(self):
        records = {
            "2026-07-01": {"training": {"sessions": [session("old", "2026-07-01", ["腹", "胸", "三头"])]}},
            "2026-07-10": {"training": {"session": session("new", "2026-07-10", ["三头", "胸", "腹"])}},
            "2026-07-11": {"training": {"session": session("back", "2026-07-11", ["背", "二头"])}},
            "2026-07-12": {"training": {"session": session("planned", "2026-07-12", ["腿"], status="planned", completed=False)}},
        }
        cards = history_training_cards(records)
        self.assertEqual([item["combination"] for item in cards], ["背+二头", "胸+三头+腹"])
        self.assertEqual(cards[1]["session_id"], "new")
        self.assertEqual([item["combination"] for item in history_training_cards(records, "腹部")], ["胸+三头+腹"])

    def test_legacy_targets_are_kept_without_inventing_sets(self):
        records = {"2026-06-01": {"training": {"targets": [
            {"target": "胸", "detail": "卧推"}, {"target": "三头", "detail": "下压"}
        ]}}}
        card = history_training_cards(records)[0]
        self.assertEqual(card["combination"], "胸+三头")
        self.assertEqual(card["session"]["exercises"][0]["sets"], [])


class WholeSessionCopyTests(unittest.TestCase):
    def test_replace_rebuilds_ids_and_clears_execution_fields(self):
        source = session("source", "2026-07-10", ["胸", "三头", "腹"])
        ids = iter(["new-session", "new-e1", "new-s1", "new-e2", "new-s2", "new-e3", "new-s3"])
        copied = copy_whole_session(source, mode="replace", new_date="2026-07-21", id_factory=lambda prefix: next(ids))
        self.assertEqual(copied["id"], "new-session")
        self.assertEqual([item["body_part"] for item in copied["exercises"]], ["胸", "三头", "腹"])
        self.assertEqual(copied["status"], "planned")
        self.assertEqual(copied["started_at"], "")
        self.assertEqual(copied["summary_note"], "")
        self.assertIsNone(copied["total_duration_min"])
        self.assertFalse(copied["exercises"][0]["sets"][0]["completed"])
        self.assertEqual(copied["exercises"][0]["sets"][0]["completed_at"], "")
        self.assertIsNone(copied["exercises"][0]["sets"][0]["rpe"])
        self.assertNotEqual(copied["exercises"][0]["id"], source["exercises"][0]["id"])

    def test_append_keeps_existing_and_appends_entire_combination(self):
        current = session("current", "2026-07-21", ["肩"], status="planned", completed=False)
        source = session("source", "2026-07-10", ["胸", "三头", "腹"])
        copied = copy_whole_session(source, current, mode="append", new_date="2026-07-21")
        self.assertEqual(copied["id"], "current")
        self.assertEqual([item["body_part"] for item in copied["exercises"]], ["肩", "胸", "三头", "腹"])
        self.assertEqual(source["exercises"][0]["sets"][0]["completed"], True)

    def test_copy_rebuilds_group_and_member_ids_and_keeps_cardio_parameters(self):
        source = session("source", "2026-07-10", ["胸", "有氧"])
        source["exercises"][1].update({
            "recording_mode": "cardio", "sets": [], "duration_seconds": 1200,
            "distance_km": 5, "cardio_metrics": {"resistance_level": 8}, "completed": True,
        })
        source["exercise_groups"] = [{
            "id": "old-group", "group_type": "superset", "order": 1,
            "exercise_ids": [item["id"] for item in source["exercises"]],
        }]
        counters = {}

        def factory(prefix):
            counters[prefix] = counters.get(prefix, 0) + 1
            return f"new-{prefix}-{counters[prefix]}"

        copied = copy_whole_session(source, mode="replace", id_factory=factory)

        self.assertNotEqual(copied["exercise_groups"][0]["id"], "old-group")
        self.assertEqual(copied["exercise_groups"][0]["exercise_ids"], [item["id"] for item in copied["exercises"]])
        self.assertEqual(copied["exercises"][1]["sets"], [])
        self.assertEqual(copied["exercises"][1]["duration_seconds"], 1200)
        self.assertEqual(copied["exercises"][1]["cardio_metrics"]["resistance_level"], 8)
        self.assertFalse(copied["exercises"][1]["completed"])


class ExerciseRankingTests(unittest.TestCase):
    def test_counts_once_per_effective_session_and_sorts(self):
        first = session("a", "2026-07-01", ["胸"])
        first["exercises"].append({**first["exercises"][0], "id": "duplicate"})
        records = {
            "2026-07-01": {"training": {"session": first}},
            "2026-07-10": {"training": {"session": session("b", "2026-07-10", ["胸", "背"])}},
            "2026-07-11": {"training": {"session": session("ignored", "2026-07-11", ["腿"], status="active")}},
        }
        stats = exercise_usage_stats(records)
        self.assertEqual(stats["胸动作"]["session_count"], 2)
        self.assertEqual(stats["胸动作"]["last_date"], "2026-07-10")
        library = [{"name": "腿动作"}, {"name": "背动作"}, {"name": "胸动作"}]
        self.assertEqual([x["name"] for x in sort_exercises(library, stats)], ["胸动作", "背动作", "腿动作"])
        self.assertEqual([x["name"] for x in sort_exercises(library, stats, "recent")], ["胸动作", "背动作", "腿动作"])
        self.assertEqual(
            [x["name"] for x in sort_exercises([{"name": "C"}, {"name": "A"}, {"name": "B"}], stats, "name")],
            ["A", "B", "C"],
        )

    def test_frequent_sort_prefers_count_then_recency_without_mutating_library(self):
        library = [{"name": "Alpha"}, {"name": "Beta"}, {"name": "Gamma"}]
        stats = {
            "alpha": {"name": "Alpha", "session_count": 2, "last_date": "2026-07-01"},
            "beta": {"name": "Beta", "session_count": 1, "last_date": "2026-07-20"},
            "gamma": {"name": "Gamma", "session_count": 2, "last_date": "2026-07-10"},
        }

        frequent = sort_exercises(library, stats, "frequent")
        recent = sort_exercises(library, stats, "recent")

        self.assertEqual([item["name"] for item in frequent], ["Gamma", "Alpha", "Beta"])
        self.assertEqual([item["name"] for item in recent], ["Beta", "Gamma", "Alpha"])
        self.assertEqual(library, [{"name": "Alpha"}, {"name": "Beta"}, {"name": "Gamma"}])


class WeightEditingTests(unittest.TestCase):
    def test_step_is_exactly_one_point_two_five_and_clamped(self):
        self.assertEqual(adjust_weight_kg(70, 1), 71.25)
        self.assertEqual(adjust_weight_kg(71.25, -1), 70.0)
        self.assertEqual(adjust_weight_kg(0, -1), 0.0)
        self.assertEqual(adjust_weight_kg(999.5, 1), 1000.0)

    def test_direct_input_accepts_dot_and_comma_and_rejects_invalid_values(self):
        self.assertEqual(normalize_weight_input("71,25"), 71.25)
        self.assertEqual(normalize_weight_input(" 70.5 "), 70.5)
        self.assertEqual(normalize_weight_input("0"), 0.0)
        for value in ("", "abc", "-1", "1000.01"):
            with self.assertRaises(ValueError):
                normalize_weight_input(value)

    def test_weight_format_removes_float_noise_and_trailing_zero(self):
        self.assertEqual(format_weight_kg(70.0), "70")
        self.assertEqual(format_weight_kg(71.25), "71.25")
        self.assertEqual(format_weight_kg(70.5), "70.5")


class ExerciseReorderTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            {"id": "a", "name": "卧推", "sets": [{"id": "a1", "weight_kg": 80, "completed": True}], "note": "保留"},
            {"id": "b", "name": "划船", "sets": [{"id": "b1", "reps": 10}]},
            {"id": "c", "name": "深蹲", "sets": [{"id": "c1", "weight_kg": 100}]},
        ]

    def test_move_first_to_last_preserves_nested_data(self):
        result = reorder_session_exercises(self.items, "a", "c")
        self.assertEqual([item["id"] for item in result], ["b", "c", "a"])
        self.assertEqual(result[-1]["sets"][0]["weight_kg"], 80)
        self.assertEqual(result[-1]["note"], "保留")
        self.assertEqual([item["order"] for item in result], [1, 2, 3])

    def test_move_last_to_first_and_middle(self):
        self.assertEqual([item["id"] for item in reorder_session_exercises(self.items, "c", "a")], ["c", "a", "b"])
        self.assertEqual([item["id"] for item in reorder_session_exercises(self.items, "a", "b")], ["b", "a", "c"])

    def test_unknown_or_same_id_is_safe_copy(self):
        self.assertEqual(reorder_session_exercises(self.items, "missing", "a"), self.items)
        self.assertIsNot(reorder_session_exercises(self.items, "a", "a"), self.items)

    def test_group_order_tracks_dragged_stable_ids(self):
        groups = create_exercise_group(
            self.items, [], ["a", "c"], "superset", id_factory=lambda prefix: "group-stable"
        )
        reordered = reorder_session_exercises(self.items, "c", "a")
        normalized = normalize_exercise_groups(reordered, groups)

        self.assertEqual(normalized[0]["id"], "group-stable")
        self.assertEqual(normalized[0]["exercise_ids"], ["c", "a"])
        self.assertEqual(reordered[0]["group_id"], "group-stable")
        self.assertEqual(reordered[0]["group_order"], 1)
        self.assertEqual(reordered[1]["group_order"], 2)

    def test_group_reorder_moves_whole_visible_block(self):
        groups = create_exercise_group(
            self.items, [], ["a", "c"], "superset", id_factory=lambda prefix: "group-stable"
        )
        moved_after_middle = reorder_session_exercise_blocks(self.items, groups, "a", "b")
        self.assertEqual([item["id"] for item in moved_after_middle], ["b", "a", "c"])

        moved_before_group = reorder_session_exercise_blocks(self.items, groups, "b", "c")
        self.assertEqual([item["id"] for item in moved_before_group], ["b", "a", "c"])

    def test_drag_preview_matches_final_drop_order_and_keeps_group_as_one_block(self):
        groups = create_exercise_group(
            self.items, [], ["a", "c"], "compound", id_factory=lambda prefix: "group-stable"
        )

        self.assertEqual(
            preview_session_exercise_block_order(self.items, groups, "a", "b"),
            ["b", "a"],
        )
        self.assertEqual(
            preview_session_exercise_block_order(self.items, groups, "b", "c"),
            ["b", "a"],
        )
        self.assertEqual([item["id"] for item in self.items], ["a", "b", "c"])

    def test_group_requires_two_valid_unique_members_and_one_membership_each(self):
        with self.assertRaises(ValueError):
            create_exercise_group(self.items, [], ["a", "a"], "superset")
        with self.assertRaises(ValueError):
            create_exercise_group(self.items, [], ["a", "missing"], "compound")
        with self.assertRaises(ValueError):
            create_exercise_group(self.items, [], ["a", "b"], "invalid")

    def test_group_work_runs_members_in_order_and_rests_after_each_full_round(self):
        exercises = [
            {"id": "a", "recording_mode": "strength", "group_id": "g", "sets": [{"completed": True}, {"completed": False}]},
            {"id": "b", "recording_mode": "strength", "group_id": "g", "sets": [{"completed": False}, {"completed": False}]},
        ]
        grouped = {"exercises": exercises, "exercise_groups": [{"id": "g", "group_type": "superset", "exercise_ids": ["a", "b"]}]}

        first = next_group_work(grouped, "a", 0)
        self.assertEqual((first["exercise_id"], first["set_index"], first["grouped_round_complete"]), ("b", 0, False))
        exercises[1]["sets"][0]["completed"] = True
        second = next_group_work(grouped, "b", 0)
        self.assertEqual((second["exercise_id"], second["set_index"], second["grouped_round_complete"]), ("a", 1, True))
        exercises[0]["sets"][1]["completed"] = True
        third = next_group_work(grouped, "a", 1)
        self.assertEqual((third["exercise_id"], third["set_index"], third["grouped_round_complete"]), ("b", 1, False))
        exercises[1]["sets"][1]["completed"] = True
        final = next_group_work(grouped, "b", 1)
        self.assertTrue(final["grouped_round_complete"])
        self.assertTrue(final["group_complete"])


class RestCycleTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 7, 21, 10, 0, 0)
        self.cycle = start_rest_cycle(90, self.now, id_factory=lambda prefix: "rest-1")

    def test_adjust_pause_resume_and_bounds(self):
        cycle = adjust_rest_cycle(self.cycle, 10, self.now)
        self.assertEqual(rest_remaining_seconds(cycle, self.now), 100)
        cycle = adjust_rest_cycle(cycle, -10, self.now)
        self.assertEqual(rest_remaining_seconds(cycle, self.now), 90)
        cycle = pause_rest_cycle(cycle, self.now + dt.timedelta(seconds=20))
        self.assertEqual(rest_remaining_seconds(cycle, self.now + dt.timedelta(hours=1)), 70)
        cycle = adjust_rest_cycle(cycle, -100, self.now)
        self.assertEqual(cycle["status"], "running")
        self.assertEqual(rest_remaining_seconds(cycle, self.now), 0)
        cycle = resume_rest_cycle(cycle, self.now + dt.timedelta(hours=1))
        self.assertEqual(rest_remaining_seconds(cycle, self.now + dt.timedelta(hours=1)), 0)

    def test_paused_cycle_reduced_to_zero_can_claim_one_finish_notification(self):
        paused = pause_rest_cycle(self.cycle, self.now + dt.timedelta(seconds=10))
        reduced = adjust_rest_cycle(paused, -100, self.now + dt.timedelta(seconds=20))
        ended, notify = finish_rest_cycle(reduced, self.now + dt.timedelta(seconds=20))
        ended_again, notify_again = finish_rest_cycle(ended, self.now + dt.timedelta(seconds=21))

        self.assertTrue(notify)
        self.assertFalse(notify_again)
        self.assertEqual(ended["status"], "finished")
        self.assertEqual(ended_again["notified_at"], ended["notified_at"])

    def test_natural_finish_notifies_once_and_skip_never_notifies(self):
        ended, notify = finish_rest_cycle(self.cycle, self.now + dt.timedelta(seconds=90))
        self.assertTrue(notify)
        self.assertTrue(ended["notified"])
        ended_again, notify_again = finish_rest_cycle(ended, self.now + dt.timedelta(seconds=91))
        self.assertFalse(notify_again)
        self.assertEqual(ended_again["notified_at"], ended["notified_at"])

        skipped = skip_rest_cycle(self.cycle, self.now + dt.timedelta(seconds=30))
        skipped, notify = finish_rest_cycle(skipped, self.now + dt.timedelta(seconds=100))
        self.assertFalse(notify)
        self.assertEqual(skipped["status"], "skipped")

    def test_early_and_paused_cycles_do_not_claim_natural_finish_notification(self):
        early, notify = finish_rest_cycle(self.cycle, self.now + dt.timedelta(seconds=89))
        self.assertFalse(notify)
        self.assertEqual(early["status"], "running")
        self.assertFalse(early["notified"])

        paused = pause_rest_cycle(self.cycle, self.now + dt.timedelta(seconds=10))
        still_paused, notify = finish_rest_cycle(paused, self.now + dt.timedelta(minutes=30))
        self.assertFalse(notify)
        self.assertEqual(still_paused["status"], "paused")
        self.assertEqual(rest_remaining_seconds(still_paused, self.now + dt.timedelta(minutes=30)), 80)


class UndoSetTests(unittest.TestCase):
    def test_undo_is_pure_and_preserves_values(self):
        original = session("source", "2026-07-10", ["胸"])
        result = undo_completed_set(original, "set-source-1")
        self.assertTrue(original["exercises"][0]["sets"][0]["completed"])
        restored = result["exercises"][0]["sets"][0]
        self.assertFalse(restored["completed"])
        self.assertEqual(restored["completed_at"], "")
        self.assertEqual((restored["weight_kg"], restored["reps"]), (20, 10))

    def test_missing_set_is_explicit(self):
        with self.assertRaises(KeyError):
            undo_completed_set(session("source", "2026-07-10", ["胸"]), "missing")

    def test_undo_result_api_exposes_status_and_indexes(self):
        result = undo_completed_set_result(session("source", "2026-07-10", ["胸"]), "set-source-1")

        self.assertEqual(result["status"], "undone")
        self.assertEqual(result["exercise_index"], 0)
        self.assertEqual(result["set_index"], 0)
        self.assertFalse(result["completed"])


if __name__ == "__main__":
    unittest.main()
