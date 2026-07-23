import sys
import unittest
import re
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from achievement_definitions import HIDDEN_ACHIEVEMENTS, LADDER_ACHIEVEMENTS, achievement_definitions  # noqa: E402
from achievement_service import (  # noqa: E402
    acknowledge_achievement_celebration,
    achievement_metric_snapshot,
    achievement_unlock_times,
    evaluate_achievements,
    normalize_achievement_unlock_state,
    pending_achievement_results,
    register_achievement_unlocks,
)
from achievement_views import (  # noqa: E402
    HIDDEN_LOCKED_TITLE,
    achievement_view_model,
    build_achievement_celebration,
    sort_achievement_views,
)


ENGLISH_SENTENCE_RE = re.compile(r"[A-Za-z][A-Za-z\s,'-]{3,}[.!?]")


def completed_set(weight=50, reps=10, *, warmup=False):
    return {"weight_kg": weight, "reps": reps, "completed": True, "warmup": warmup}


def exercise(name, body_part, sets):
    return {"name": name, "body_part": body_part, "sets": sets}


def session(session_id, date, exercises, *, duration=60, status="completed"):
    return {
        "id": session_id,
        "date": date,
        "status": status,
        "total_duration_min": duration,
        "exercises": exercises,
    }


class AchievementDefinitionTests(unittest.TestCase):
    def test_definition_counts_ids_and_tiers_are_stable(self):
        definitions = achievement_definitions()
        ids = [item.id for item in definitions]

        self.assertEqual(len(LADDER_ACHIEVEMENTS), 192)
        self.assertEqual(len(HIDDEN_ACHIEVEMENTS), 8)
        self.assertEqual(len(definitions), 200)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            {tier: sum(1 for item in LADDER_ACHIEVEMENTS if item.tier == tier) for tier in ("bronze", "silver", "gold", "diamond")},
            {"bronze": 48, "silver": 48, "gold": 48, "diamond": 48},
        )
        self.assertTrue(all(item.hidden and item.kind == "hidden" for item in HIDDEN_ACHIEVEMENTS))

        ladders = {}
        for item in LADDER_ACHIEVEMENTS:
            ladders.setdefault(item.id.rsplit("_", 1)[0], []).append(item)
        self.assertEqual(len(ladders), 48)
        for items in ladders.values():
            self.assertEqual([item.tier for item in items], ["bronze", "silver", "gold", "diamond"])
            self.assertEqual([item.target for item in items], sorted({item.target for item in items}))

    def test_user_visible_copy_is_chinese(self):
        visible_texts = [HIDDEN_LOCKED_TITLE, "达成条件后揭晓"]
        for item in achievement_definitions():
            visible_texts.extend([item.title, item.description])

        for text in visible_texts:
            with self.subTest(text=text):
                self.assertIsNone(ENGLISH_SENTENCE_RE.search(text))
                self.assertRegex(text, r"[\u4e00-\u9fff]")


class AchievementProgressTests(unittest.TestCase):
    def test_progress_is_calculated_from_real_daily_records(self):
        records = {
            "2026-07-01": {
                "meals": {"breakfast": [{"name": "oats"}]},
                "daily_total": {"kcal": 1800, "carb": 180, "protein": 120, "fat": 50},
                "water": {"records_ml": [1000, 1200]},
                "sleep": {"total_minutes": 450},
                "profile": {"measurement": {"weight_kg": 70.2, "measured_at": "2026-07-01T08:00:00"}},
                "training": {
                    "sessions": [
                        session(
                            "morning",
                            "2026-07-01",
                            [exercise("Bench", "Chest", [completed_set(60, 10), completed_set(20, 10, warmup=True)])],
                            duration=45,
                        ),
                        session(
                            "evening",
                            "2026-07-01",
                            [exercise("Row", "Back", [completed_set(40, 10)])],
                            duration=30,
                        ),
                    ]
                },
            },
            "2026-07-02": {
                "daily_total": {"kcal": 1600},
                "water": {"total_ml": 1500},
                "sleep": {"bed_time": "23:00", "wake_time": "07:00"},
                "training": {"session": session("legs", "2026-07-02", [exercise("Squat", "Legs", [completed_set(100, 5)])], duration=130)},
            },
            "2026-07-20": {
                "training": {"session": session("return", "2026-07-20", [exercise("Press", "Shoulders", [completed_set(30, 10)])], duration=40)}
            },
        }

        metrics = achievement_metric_snapshot(records)
        results = {item["id"]: item for item in evaluate_achievements(records)}

        self.assertEqual(metrics["training_days"], 3)
        self.assertEqual(metrics["training_sessions"], 4)
        self.assertEqual(metrics["formal_sets"], 4)
        self.assertEqual(metrics["volume_kg"], 1800)
        self.assertEqual(metrics["duration_min"], 245)
        self.assertEqual(metrics["unique_exercises"], 4)
        self.assertEqual(metrics["body_part_variety"], 4)
        self.assertEqual(metrics["chest_days"], 1)
        self.assertEqual(metrics["back_days"], 1)
        self.assertEqual(metrics["leg_days"], 1)
        self.assertEqual(metrics["shoulder_days"], 1)
        self.assertEqual(metrics["nutrition_logged_days"], 2)
        self.assertEqual(metrics["water_goal_days"], 1)
        self.assertEqual(metrics["sleep_logged_days"], 2)
        self.assertEqual(metrics["measurement_days"], 1)
        self.assertEqual(metrics["double_session_day"], 0)
        self.assertEqual(metrics["marathon_session"], 0)
        self.assertEqual(metrics["comeback"], 1)
        self.assertEqual(metrics["completed_reps"], 35)
        self.assertEqual(metrics["loaded_sets"], 4)
        self.assertEqual(metrics["meal_entries"], 1)
        self.assertEqual(metrics["unique_foods"], 1)
        self.assertEqual(metrics["macro_complete_days"], 1)
        self.assertEqual(metrics["protein_logged_days"], 1)
        self.assertEqual(metrics["water_logged_days"], 2)
        self.assertEqual(metrics["water_liters"], 3.7)
        self.assertEqual(metrics["sleep_duration_days"], 1)
        self.assertEqual(metrics["restful_sleep_days"], 1)
        self.assertEqual(metrics["weight_measurement_days"], 1)
        self.assertTrue(results["training_days_bronze"]["unlocked"])
        self.assertFalse(results["training_days_silver"]["unlocked"])
        self.assertEqual(results["formal_sets_bronze"]["progress"], 0.8)

    def test_training_store_is_counted_without_duplicate_record_sessions(self):
        duplicate = session("same", "2026-07-01", [exercise("Bench", "Chest", [completed_set(50, 8)])])
        records = {"2026-07-01": {"training": {"session": duplicate}}}
        training_data = {
            "sessions": [
                duplicate,
                session("store-only", "2026-07-02", [exercise("Deadlift", "Back", [completed_set(100, 5)])], duration=70),
            ]
        }

        metrics = achievement_metric_snapshot(records, training_data)

        self.assertEqual(metrics["training_sessions"], 2)
        self.assertEqual(metrics["training_days"], 2)
        self.assertEqual(metrics["volume_kg"], 900)
        self.assertEqual(metrics["completed_reps"], 13)

    def test_legacy_and_partial_records_remain_compatible(self):
        records = {
            "bad-key": None,
            "2026-07-01": {"profile": {"weight_kg": 72}},
            "2026-07-02": {"meals": {"早餐": [None, {"name": "燕麦"}]}, "water": [500]},
        }

        metrics = achievement_metric_snapshot(records, {"sessions": "invalid"})
        results = evaluate_achievements(records, {"sessions": "invalid"})

        self.assertEqual(len(results), 200)
        self.assertEqual(metrics["measurement_days"], 0)
        self.assertEqual(metrics["nutrition_logged_days"], 1)
        self.assertEqual(metrics["breakfast_days"], 1)

    def test_hidden_training_goals_reward_complete_balanced_work_not_overtraining(self):
        records = {
            "2026-07-01": {
                "training": {
                    "session": session(
                        "balanced",
                        "2026-07-01",
                        [
                            exercise("Bench", "Chest", [completed_set(), completed_set(), completed_set()]),
                            exercise("Extension", "Triceps", [completed_set()]),
                        ],
                    )
                }
            },
            "2026-07-03": {
                "training": {"session": session("second-day", "2026-07-03", [exercise("Row", "Back", [completed_set()])])}
            },
        }

        metrics = achievement_metric_snapshot(records)

        self.assertEqual(metrics["double_session_day"], 1)
        self.assertEqual(metrics["marathon_session"], 1)
        self.assertEqual(metrics["seven_day_training_streak"], 1)
        self.assertEqual(metrics["training_week_streak"], 1)
        self.assertEqual(metrics["arm_days"], 1)

    def test_hidden_display_masks_locked_and_reveals_unlocked(self):
        locked = {
            "id": "hidden_double_session_day",
            "title": "一日两练",
            "description": "同一天完成两场有效训练。",
            "hidden": True,
            "unlocked": False,
        }
        unlocked = {**locked, "unlocked": True}

        locked_view = achievement_view_model(locked)
        unlocked_view = achievement_view_model(unlocked)

        self.assertEqual(locked_view["title"], HIDDEN_LOCKED_TITLE)
        self.assertEqual(locked_view["description"], "达成条件后揭晓")
        self.assertFalse(locked_view["revealed"])
        self.assertEqual(unlocked_view["title"], "一日两练")
        self.assertTrue(unlocked_view["revealed"])

    def test_attention_sort_groups_progress_completed_and_zero_stably(self):
        items = [
            {"id": "zero", "current": 0, "target": 10, "unlocked": False},
            {"id": "half-more-left", "current": 50, "target": 100, "unlocked": False},
            {"id": "done-old", "current": 10, "target": 10, "unlocked": True},
            {"id": "near", "current": 9, "target": 10, "unlocked": False},
            {"id": "half-less-left", "current": 5, "target": 10, "unlocked": False},
            {"id": "done-new", "current": 20, "target": 10, "unlocked": True},
            {"id": "zero-2", "current": 0, "target": 20, "unlocked": False},
        ]
        ranked = sort_achievement_views(
            items,
            {"done-old": "2026-07-01T10:00:00", "done-new": "2026-07-22T10:00:00"},
        )
        self.assertEqual(
            [item["id"] for item in ranked],
            ["near", "half-less-left", "half-more-left", "done-new", "done-old", "zero", "zero-2"],
        )

    def test_unlocked_without_timestamp_and_hidden_entries_remain_stable_and_masked(self):
        items = [
            {"id": "done-a", "title": "A", "description": "A", "current": 1, "target": 1, "unlocked": True},
            {"id": "done-b", "title": "B", "description": "B", "current": 2, "target": 1, "unlocked": True},
            {"id": "secret", "title": "秘密条件", "description": "不能泄露", "current": 0, "target": 1, "unlocked": False, "hidden": True},
        ]
        ranked = sort_achievement_views(items)

        self.assertEqual([item["id"] for item in ranked], ["done-a", "done-b", "secret"])
        self.assertEqual(ranked[-1]["title"], HIDDEN_LOCKED_TITLE)
        self.assertEqual(ranked[-1]["description"], "达成条件后揭晓")


class AchievementCelebrationTests(unittest.TestCase):
    def setUp(self):
        self.results = [
            {
                "id": "training_days_bronze",
                "title": "训练天数·铜",
                "description": "在不同日期完成真实训练。",
                "unlocked": True,
            },
            {
                "id": "nutrition_logged_days_bronze",
                "title": "饮食记录·铜",
                "description": "记录餐食或每日营养总量。",
                "unlocked": True,
            },
        ]

    def test_legacy_unlocks_migrate_as_already_celebrated(self):
        legacy = {"training_days_bronze": "2026-07-20T08:00:00"}
        updated = register_achievement_unlocks(self.results[:1], legacy, "2026-07-23T09:00:00")
        state = normalize_achievement_unlock_state(updated)

        self.assertEqual(state["celebrated"], ["training_days_bronze"])
        self.assertEqual(state["pending"], [])
        self.assertEqual(pending_achievement_results(self.results, updated), [])

    def test_multiple_new_unlocks_are_queued_once_in_result_order(self):
        updated = register_achievement_unlocks(self.results, {}, "2026-07-23T09:00:00")
        repeated = register_achievement_unlocks(self.results, updated, "2026-07-23T09:01:00")

        self.assertEqual(
            normalize_achievement_unlock_state(repeated)["pending"],
            ["training_days_bronze", "nutrition_logged_days_bronze"],
        )
        self.assertEqual(
            [item["id"] for item in pending_achievement_results(self.results, repeated)],
            ["training_days_bronze", "nutrition_logged_days_bronze"],
        )

    def test_acknowledgement_never_drops_the_remaining_queue_or_repeats(self):
        stored = register_achievement_unlocks(self.results, {}, "2026-07-23T09:00:00")
        after_first = acknowledge_achievement_celebration(stored, "training_days_bronze")

        self.assertEqual(
            [item["id"] for item in pending_achievement_results(self.results, after_first)],
            ["nutrition_logged_days_bronze"],
        )
        after_second = acknowledge_achievement_celebration(after_first, "nutrition_logged_days_bronze")
        revisited = register_achievement_unlocks(self.results, after_second, "2026-07-23T10:00:00")
        self.assertEqual(pending_achievement_results(self.results, revisited), [])
        self.assertEqual(set(achievement_unlock_times(revisited)), {
            "training_days_bronze", "nutrition_logged_days_bronze",
        })

    def test_invalid_old_state_defaults_safely(self):
        self.assertEqual(
            normalize_achievement_unlock_state({"_pending": "bad", "_celebrated": None})["pending"],
            [],
        )
        self.assertEqual(normalize_achievement_unlock_state(None)["unlock_times"], {})

    def test_celebration_card_contains_required_copy_and_confirmation(self):
        confirmed = []
        dialog = build_achievement_celebration(self.results[0], on_confirm=lambda event: confirmed.append(True))

        def walk(control):
            if control is None:
                return []
            items = [control]
            for attribute in ("title", "content"):
                child = getattr(control, attribute, None)
                if child is not None and child is not control:
                    items.extend(walk(child))
            for child in getattr(control, "controls", []) or []:
                items.extend(walk(child))
            return items

        controls = walk(dialog)
        text = " ".join(str(getattr(item, "value", "")) for item in controls)
        self.assertTrue(dialog.modal)
        self.assertIn("训练天数·铜", text)
        self.assertIn("在不同日期完成真实训练。", text)
        self.assertIn("继续保持", text)
        confirm = next(item for item in controls if getattr(item, "on_click", None) is not None)
        confirm.on_click(None)
        self.assertEqual(confirmed, [True])


if __name__ == "__main__":
    unittest.main()
