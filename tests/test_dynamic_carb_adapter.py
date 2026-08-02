import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynamic_carb_adapter import calculate_app_snapshot, normalize_training, targets_from_snapshot  # noqa: E402


def strength_exercise(name="深蹲", body_part="腿", sets=4, *, confirmed=True, load_kind="external"):
    return {
        "name": name,
        "body_part": body_part,
        "order": 1,
        "recording_mode": "strength",
        "load_kind": load_kind,
        "parameters_confirmed": confirmed,
        "sets": [
            {"order": index + 1, "weight_kg": 60, "reps": 10, "completed": False, "warmup": False}
            for index in range(sets)
        ],
    }


def state(training=None):
    return {
        "date": "2026-08-02",
        "weight": "60",
        "bodyfat": "20",
        "height": "165",
        "age": "30",
        "sex": "女",
        "activity_habit": "规律训练",
        "macro_goal": "保持",
        "day_type": "低碳日",
        "training": training or {"targets": [], "sessions": [], "session": None, "carb_mode": "auto"},
    }


class DynamicCarbAdapterTests(unittest.TestCase):
    def test_unknown_and_explicit_rest_are_distinct(self):
        self.assertEqual(normalize_training({"targets": []})["status"], "unknown")
        self.assertEqual(normalize_training({"targets": [{"target": "休息"}]})["status"], "explicit_rest")

    def test_training_overrides_a_stale_rest_target(self):
        training = {
            "targets": [{"target": "休息"}],
            "session": {"date": "2026-08-02", "status": "planned", "exercises": [strength_exercise()]},
            "sessions": [],
        }
        self.assertEqual(normalize_training(training)["status"], "planned_confirmed")

    def test_unconfirmed_plan_stays_provisional(self):
        training = {
            "session": {
                "date": "2026-08-02",
                "status": "planned",
                "exercises": [strength_exercise(confirmed=False)],
            }
        }
        facts = normalize_training(training)
        self.assertEqual(facts["status"], "planned_pending")
        self.assertNotIn("resistance", facts)

    def test_confirmed_bodyweight_is_not_treated_as_zero_or_unknown_load(self):
        exercise = strength_exercise(load_kind="bodyweight")
        for item in exercise["sets"]:
            item["weight_kg"] = 0
        facts = normalize_training({
            "session": {"date": "2026-08-02", "status": "planned", "exercises": [exercise]}
        })
        self.assertEqual(facts["status"], "planned_confirmed")
        self.assertEqual(facts["resistance"]["work_sets_total"], 4)

    def test_completed_session_uses_only_completed_non_warmup_sets(self):
        exercise = strength_exercise(sets=4)
        exercise["sets"][0]["warmup"] = True
        exercise["sets"][0]["completed"] = True
        exercise["sets"][1]["completed"] = True
        facts = normalize_training({
            "session": {"date": "2026-08-02", "status": "completed", "exercises": [exercise]}
        })
        self.assertEqual(facts["status"], "completed")
        self.assertEqual(facts["resistance"]["work_sets_total"], 1)

    def test_confirmed_ten_peak_sets_produce_formal_high_day_snapshot(self):
        training = {
            "carb_mode": "auto",
            "session": {
                "date": "2026-08-02",
                "status": "planned",
                "exercises": [strength_exercise(sets=10)],
            },
        }
        snapshot = calculate_app_snapshot(state(training), calculated_at="2026-08-02T08:00:00")
        self.assertEqual(snapshot["engine_snapshot"]["recommended_day"], "高碳日")
        self.assertEqual(snapshot["ui_projection"]["status"], "auto")
        self.assertIsNotNone(targets_from_snapshot(snapshot))

    def test_manual_day_is_applied_without_hiding_recommendation(self):
        training = {
            "carb_mode": "manual",
            "session": {
                "date": "2026-08-02",
                "status": "planned",
                "exercises": [strength_exercise(sets=10)],
            },
        }
        current = state(training)
        current["day_type"] = "中碳日"
        snapshot = calculate_app_snapshot(current, calculated_at="2026-08-02T08:00:00")
        self.assertEqual(snapshot["engine_snapshot"]["recommended_day"], "高碳日")
        self.assertEqual(snapshot["engine_snapshot"]["applied_day"], "中碳日")
        self.assertEqual(snapshot["ui_projection"]["recommended_difference"], "高碳日")

    def test_historical_recompute_keeps_the_original_shown_target(self):
        original = calculate_app_snapshot(state(), calculated_at="2026-08-02T08:00:00")
        changed = state({
            "carb_mode": "auto",
            "session": {
                "date": "2026-08-02",
                "status": "planned",
                "exercises": [strength_exercise(sets=10)],
            },
        })
        recomputed = calculate_app_snapshot(
            changed,
            existing=original,
            freeze_shown=True,
            calculated_at="2026-08-05T08:00:00",
        )
        self.assertEqual(recomputed["shown_target_snapshot"], original["shown_target_snapshot"])
        self.assertEqual(recomputed["ui_projection"]["day_label"], "高碳日")


if __name__ == "__main__":
    unittest.main()
