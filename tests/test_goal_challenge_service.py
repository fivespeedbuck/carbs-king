"""Focused tests for active goal challenge progress and persistence rules."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ISOLATED_DATA_DIR = tempfile.TemporaryDirectory(prefix="carbs-king-goal-tests-")
os.environ["CARBS_KING_DATA_DIR"] = _ISOLATED_DATA_DIR.name

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from goal_challenge_service import (  # noqa: E402
    add_challenge,
    challenge_progress,
    consume_next_celebration,
    create_challenge,
    delete_active_challenges,
    lane_available,
    normalize_challenge_state,
    recalculate_state,
    recommendation_progress,
    visible_recommendations,
)
from goal_challenge_definitions import BODY_METRICS, TYPE_LABELS, recommended_templates  # noqa: E402


def completed_session(identity="s1", *, weight=50, reps=10, exercise="squat"):
    return {
        "id": identity, "status": "completed",
        "exercises": [{"id": exercise, "sets": [{"completed": True, "weight_kg": weight, "reps": reps}]}],
    }


class GoalChallengeServiceTests(unittest.TestCase):
    def test_write_tests_use_isolated_data_dir(self):
        self.assertEqual(os.environ["CARBS_KING_DATA_DIR"], _ISOLATED_DATA_DIR.name)
        self.assertTrue(Path(os.environ["CARBS_KING_DATA_DIR"]).is_dir())

    def test_all_training_metrics_recalculate_from_historical_records(self):
        records = {
            "2026-07-27": {"training": {"sessions": [completed_session("a", weight=50, reps=10)]}},
            "2026-07-28": {"training": {"sessions": [completed_session("b", weight=60, reps=8)]}},
        }
        base = {"start_date": "2026-07-01", "end_date": "2026-07-28", "target": 1, "unit": "次"}

        self.assertEqual(challenge_progress({**base, "challenge_type": "training_sessions"}, records, today="2026-07-28")["current"], 2)
        self.assertEqual(challenge_progress({**base, "challenge_type": "training_streak"}, records, today="2026-07-28")["current"], 2)
        self.assertEqual(challenge_progress({**base, "challenge_type": "training_volume"}, records, today="2026-07-28")["current"], 980)
        self.assertEqual(challenge_progress({**base, "challenge_type": "max_weight", "action_id": "squat"}, records, today="2026-07-28")["current"], 60)
        self.assertEqual(challenge_progress({**base, "challenge_type": "exercise_reps"}, records, today="2026-07-28")["current"], 18)

    def test_water_and_nutrition_streak_require_real_daily_records(self):
        records = {
            "2026-07-26": {"water": {"records_ml": [2000]}, "daily_total": {"protein": 130}},
            "2026-07-27": {"water": {"records_ml": [2500]}, "daily_total": {"protein": 125}},
            "2026-07-28": {"water": {"records_ml": [1000]}, "daily_total": {"protein": 130}},
        }
        water = {"challenge_type": "water_streak", "target": 3, "daily_target": 2000, "start_date": "2026-07-01", "end_date": "2026-07-28"}
        protein = {"challenge_type": "nutrition_streak", "target": 3, "daily_target": 120, "indicator": "protein", "start_date": "2026-07-01", "end_date": "2026-07-28"}

        self.assertEqual(challenge_progress(water, records, today="2026-07-28")["current"], 0)
        self.assertEqual(challenge_progress(protein, records, today="2026-07-28")["current"], 3)

    def test_body_target_uses_only_real_measurements_and_direction(self):
        records = {
            "2026-07-27": {"profile": {"measurement": {"measured_at": "2026-07-27T08:00:00"}, "weight_kg": 80}},
            "2026-07-28": {"profile": {"circumference": {"waist_cm": 79, "measured_at": "2026-07-28T08:00:00"}}},
        }
        goal = {"challenge_type": "body_target", "metric": "waist_cm", "direction": "at_most", "target": 80, "unit": "cm", "start_date": "2026-07-01", "end_date": "2026-07-28"}
        progress = challenge_progress(goal, records, today="2026-07-28")
        self.assertEqual(progress["current"], 79)
        self.assertTrue(progress["complete"])

    def test_completion_moves_atomically_and_celebrates_once(self):
        challenge = create_challenge({"title": "喝水", "lane": "recovery", "challenge_type": "water_streak", "target": 2, "unit": "天", "daily_target": 2000, "start_date": "2026-07-27", "end_date": "2026-07-28"}, now="2026-07-28T09:00:00")
        records = {"2026-07-27": {"water": {"records_ml": [2000]}}, "2026-07-28": {"water": {"records_ml": [2000]}}}
        state, completed = recalculate_state({"active": [challenge]}, records, now="2026-07-28T10:00:00")

        self.assertEqual(state["active"], [])
        self.assertEqual(len(state["completed"]), 1)
        self.assertEqual(state["pending_celebrations"], [challenge["id"]])
        self.assertEqual(len(completed), 1)
        consumed, item = consume_next_celebration(state)
        repeated, repeated_item = consume_next_celebration(consumed)
        self.assertEqual(item["id"], challenge["id"])
        self.assertIsNone(repeated_item)
        self.assertEqual(repeated["celebrated"], [challenge["id"]])

    def test_lane_limit_and_level_chain_visibility(self):
        first = visible_recommendations({})
        self.assertTrue(first)
        self.assertTrue(all(item["level"] == 0 for item in first))
        active = create_challenge(first[0], now="2026-07-28T09:00:00")
        self.assertTrue(lane_available({"active": [active]}, active["lane"]))
        finished = dict(active, status="completed", completed_at="2026-07-28T10:00:00")
        unlocked = visible_recommendations({"completed": [finished]})
        next_item = next(item for item in unlocked if item["chain_id"] == active["chain_id"])
        self.assertEqual(next_item["level"], 1)

    def test_user_can_assign_any_supported_type_to_any_lane(self):
        challenge = create_challenge({
            "title": "每天达成碳循环", "lane": "recovery", "challenge_type": "nutrition_streak",
            "target": 3, "unit": "天", "indicator": "carb_cycle",
            "start_date": "2026-07-01", "end_date": "2026-07-31",
        }, now="2026-07-28T09:00:00")
        self.assertEqual(challenge["lane"], "recovery")

    def test_three_active_challenges_can_share_the_same_lane(self):
        templates = visible_recommendations({})[:3]
        state = {}
        for index, template in enumerate(templates):
            challenge = create_challenge(template, now="2026-07-28T09:00:00", lane="recovery")
            state, _ = add_challenge(state, challenge, {}, now="2026-07-28T09:00:00")
        self.assertEqual([item["lane"] for item in state["active"]], ["recovery", "recovery", "recovery"])
        self.assertFalse(lane_available(state, "recovery"))

    def test_frozen_v1_types_and_body_metadata_are_all_defined(self):
        self.assertEqual(set(TYPE_LABELS), {
            "training_volume", "max_weight", "training_sessions", "training_streak",
            "training_days", "exercise_reps", "water_streak", "nutrition_streak", "body_target",
        })
        self.assertEqual(set(BODY_METRICS), {
            "weight", "bodyfat", "chest_cm", "waist_cm", "hip_cm", "arm_cm",
            "thigh_cm", "calf_cm",
        })
        templates = recommended_templates()
        self.assertTrue(any(item.challenge_type == "body_target" for item in templates))
        self.assertTrue(any(item.challenge_type == "max_weight" for item in templates))
        self.assertEqual({item.lane for item in templates if item.challenge_type == "body_target"}, {"recovery"})
        for chain_id in {item.chain_id for item in templates}:
            self.assertEqual([item.level for item in templates if item.chain_id == chain_id], [0, 1, 2, 3])

    def test_training_sessions_counts_multiple_sessions_on_the_same_day(self):
        records = {"2026-07-28": {"training": {"sessions": [completed_session("a"), completed_session("b")]}}}
        progress = challenge_progress({
            "challenge_type": "training_sessions", "target": 2,
            "start_date": "2026-07-28", "end_date": "2026-07-28",
        }, records, today="2026-07-28")
        self.assertEqual(progress["current"], 2)
        self.assertTrue(progress["complete"])

    def test_training_days_counts_dates_not_multiple_sessions(self):
        records = {
            "2026-07-27": {"training": {"sessions": [completed_session("a"), completed_session("b")]}},
            "2026-07-28": {"training": {"sessions": [completed_session("c")]}},
        }
        progress = challenge_progress({
            "challenge_type": "training_days", "target": 2,
            "start_date": "2026-07-01", "end_date": "2026-07-28",
        }, records, today="2026-07-28")
        self.assertEqual(progress["current"], 2)
        self.assertTrue(progress["complete"])

    def test_lbs_metrics_convert_from_stored_kg(self):
        records = {"2026-07-28": {"training": {"sessions": [completed_session(weight=50, reps=10)]}}}
        base = {"start_date": "2026-07-28", "end_date": "2026-07-28", "unit": "lbs"}
        maximum = challenge_progress({**base, "challenge_type": "max_weight", "action_id": "squat", "target": 100}, records, today="2026-07-28")
        volume = challenge_progress({**base, "challenge_type": "training_volume", "target": 1000}, records, today="2026-07-28")
        self.assertAlmostEqual(maximum["current"], 110.23, places=2)
        self.assertAlmostEqual(volume["current"], 1102.31, places=2)

    def test_carb_cycle_streak_needs_food_and_saved_compliance(self):
        records = {
            "2026-07-27": {"meals": {"晚餐": [{"name": "米饭"}]}, "profile": {"compliance": {"status": "达标"}}},
            "2026-07-28": {"profile": {"compliance": {"status": "达标"}}},
        }
        goal = {"challenge_type": "nutrition_streak", "indicator": "carb_cycle", "target": 2, "start_date": "2026-07-27", "end_date": "2026-07-28"}
        self.assertEqual(challenge_progress(goal, records, today="2026-07-28")["current"], 0)
        records["2026-07-28"]["meals"] = {"晚餐": [{"name": "鸡胸"}]}
        self.assertEqual(challenge_progress(goal, records, today="2026-07-28")["current"], 2)

    def test_carried_profile_values_do_not_complete_body_goal(self):
        records = {"2026-07-28": {"profile": {"weight_kg": 70, "bodyfat_percent": 15}}}
        goal = {"challenge_type": "body_target", "metric": "weight", "direction": "at_most", "target": 75, "start_date": "2026-07-01", "end_date": "2026-07-28"}
        progress = challenge_progress(goal, records, today="2026-07-28")
        self.assertEqual(progress["current"], 0)
        self.assertFalse(progress["complete"])

    def test_add_recalculates_immediately_and_delete_only_removes_active(self):
        records = {"2026-07-28": {"water": {"records_ml": [2200]}}}
        water = create_challenge({
            "title": "今天喝够水", "lane": "recovery", "challenge_type": "water_streak",
            "target": 1, "unit": "天", "daily_target": 2000,
            "start_date": "2026-07-28", "end_date": "2026-07-28",
        }, now="2026-07-28T09:00:00")
        state, saved = add_challenge({}, water, records, now="2026-07-28T10:00:00")
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(state["pending_celebrations"], [water["id"]])
        active = create_challenge({
            "title": "训练五次", "lane": "training", "challenge_type": "training_sessions",
            "target": 5, "unit": "次", "start_date": "2026-07-01", "end_date": "2026-07-31",
        }, now="2026-07-28T11:00:00")
        state, _ = add_challenge(state, active, records, now="2026-07-28T11:00:00")
        state, count = delete_active_challenges(state, [water["id"], active["id"]])
        self.assertEqual(count, 1)
        self.assertEqual(len(state["completed"]), 1)

    def test_recommendation_background_progress_is_read_only(self):
        template = visible_recommendations({})[0]
        records = {"2026-07-28": {"training": {"sessions": [completed_session()]}}}
        before = normalize_challenge_state({})
        progress = recommendation_progress(template, records, today="2026-07-28")
        self.assertGreaterEqual(progress["current"], 0)
        self.assertEqual(before, normalize_challenge_state({}))
        self.assertEqual(before["pending_celebrations"], [])


if __name__ == "__main__":
    unittest.main()
