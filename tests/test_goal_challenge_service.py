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
    challenge_failure_reason,
    challenge_progress,
    consume_next_celebration,
    consume_pending_celebrations,
    consume_pending_failures,
    create_challenge,
    delete_active_challenges,
    filter_recommendations_by_lane,
    lane_available,
    mark_failed_retried,
    normalize_challenge_state,
    recalculate_state,
    recommendation_progress,
    visible_recommendations,
)
from goal_challenge_definitions import BODY_METRICS, TYPE_LABELS, level_info, recommended_templates  # noqa: E402


def completed_session(identity="s1", *, weight=50, reps=10, exercise="squat"):
    return {
        "id": identity, "status": "completed",
        "exercises": [{"id": exercise, "sets": [{"completed": True, "weight_kg": weight, "reps": reps}]}],
    }


def recommendation_profile(*, goal="减脂", habit="高频训练"):
    return {
        "sex": "男", "weight": 61.5, "bodyfat": 12.9,
        "height": 175, "age": 30,
        "activity_habit": habit, "macro_goal": goal,
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

    def test_expired_and_broken_challenges_move_to_failed_state(self):
        expired = create_challenge({
            "title": "月底十万公斤", "lane": "training", "challenge_type": "training_volume",
            "target": 100000, "unit": "kg", "start_date": "2026-07-01", "end_date": "2026-07-27",
        }, now="2026-07-01T09:00:00")
        failed_state, _ = recalculate_state({"active": [expired]}, {}, now="2026-07-28T09:00:00")
        self.assertEqual(failed_state["active"], [])
        self.assertEqual(failed_state["failed"][0]["id"], expired["id"])
        self.assertIn("超过结束日期", failed_state["failed"][0]["failure_reason"])
        self.assertEqual(failed_state["pending_failures"], [expired["id"]])

        streak = create_challenge({
            "title": "连续训练", "lane": "training", "challenge_type": "training_streak",
            "target": 5, "unit": "天", "start_date": "2026-07-25", "end_date": "2026-08-10",
        }, now="2026-07-25T09:00:00")
        records = {
            "2026-07-25": {"training": {"sessions": [completed_session("a")]}},
            "2026-07-26": {"training": {"sessions": [completed_session("b")]}},
            "2026-07-27": {},
        }
        self.assertEqual(
            challenge_failure_reason(streak, records, today="2026-07-28"),
            "连续记录已经中断",
        )
        broken_state, _ = recalculate_state({"active": [streak]}, records, now="2026-07-28T09:00:00")
        self.assertEqual(broken_state["failed"][0]["id"], streak["id"])

    def test_unstarted_streak_does_not_fail_and_failure_can_be_acknowledged_and_retried(self):
        streak = create_challenge({
            "title": "连续训练", "lane": "training", "challenge_type": "training_streak",
            "target": 5, "unit": "天", "start_date": "2026-07-25", "end_date": "2026-08-10",
        }, now="2026-07-25T09:00:00")
        self.assertEqual(challenge_failure_reason(streak, {}, today="2026-07-28"), "")

        failed = dict(streak, status="failed", failed_at="2026-07-28T09:00:00", failure_reason="连续记录已经中断")
        stored = {"failed": [failed], "pending_failures": [failed["id"]]}
        acknowledged, items = consume_pending_failures(stored)
        self.assertEqual([item["id"] for item in items], [failed["id"]])
        self.assertEqual(acknowledged["pending_failures"], [])
        self.assertEqual(acknowledged["acknowledged_failures"], [failed["id"]])
        retried = mark_failed_retried(acknowledged, failed["id"], now="2026-07-28T10:00:00")
        self.assertEqual(retried["failed"][0]["retried_at"], "2026-07-28T10:00:00")

    def test_pending_celebrations_can_be_consumed_as_one_batch(self):
        completed = []
        for index in range(2):
            item = create_challenge({
                "title": f"挑战 {index + 1}",
                "lane": "training",
                "challenge_type": "training_sessions",
                "target": 1,
                "unit": "次",
                "start_date": "2026-07-28",
                "end_date": "2026-07-28",
            }, now=f"2026-07-28T0{index + 8}:00:00")
            item.update({"status": "completed", "completed_at": "2026-07-28T10:00:00"})
            completed.append(item)
        stored = {
            "completed": completed,
            "pending_celebrations": [item["id"] for item in completed],
        }

        state, consumed = consume_pending_celebrations(stored)

        self.assertEqual([item["id"] for item in consumed], [item["id"] for item in completed])
        self.assertEqual(state["pending_celebrations"], [])
        self.assertEqual(state["celebrated"], [item["id"] for item in completed])

    def test_lane_limit_and_level_chain_visibility(self):
        first = visible_recommendations({})
        self.assertTrue(first)
        self.assertTrue(all(item["level"] == 0 for item in first))
        progressive = next(item for item in first if item["chain_id"] == "training_sessions")
        active = create_challenge(progressive, now="2026-07-28T09:00:00")
        self.assertTrue(lane_available({"active": [active]}, active["lane"]))
        finished = dict(active, status="completed", completed_at="2026-07-28T10:00:00")
        unlocked = visible_recommendations({"completed": [finished]})
        next_item = next(item for item in unlocked if item["chain_id"] == active["chain_id"])
        self.assertEqual(next_item["level"], 1)

    def test_recommendation_skips_to_highest_level_already_met_by_history(self):
        records = {
            "2026-07-28": {
                "profile": {
                    "circumference": {
                        "waist_cm": 71,
                        "measured_at": "2026-07-28T08:00:00",
                    }
                }
            }
        }

        visible = visible_recommendations(
            {}, records, today="2026-07-28", profile=recommendation_profile()
        )
        waist = next(item for item in visible if item["chain_id"] == "waist_target")

        self.assertEqual(waist["level"], 3)
        self.assertEqual(waist["target"], 77)

    def test_recommendation_stops_at_highest_level_currently_met(self):
        records = {
            "2026-07-28": {
                "profile": {
                    "circumference": {
                        "waist_cm": 83,
                        "measured_at": "2026-07-28T08:00:00",
                    }
                }
            }
        }

        visible = visible_recommendations(
            {}, records, today="2026-07-28", profile=recommendation_profile()
        )
        waist = next(item for item in visible if item["chain_id"] == "waist_target")

        self.assertEqual(waist["level"], 1)
        self.assertEqual(waist["target"], 87.5)

    def test_completed_body_highest_hides_while_maintained_and_returns_after_regression(self):
        highest = next(
            item.to_dict()
            for item in recommended_templates(recommendation_profile())
            if item.chain_id == "waist_target" and item.level == 3
        )
        completed = create_challenge(highest, now="2026-07-28T09:00:00")
        completed.update({"status": "completed", "completed_at": "2026-07-28T10:00:00"})
        state = {"completed": [completed]}
        maintained = {
            "2026-07-28": {"profile": {"circumference": {"waist_cm": 71, "measured_at": "2026-07-28T08:00:00"}}}
        }
        regressed = {
            "2026-07-29": {"profile": {"circumference": {"waist_cm": 80, "measured_at": "2026-07-29T08:00:00"}}}
        }

        maintained_visible = visible_recommendations(
            state, maintained, today="2026-07-28", profile=recommendation_profile()
        )
        regressed_visible = visible_recommendations(
            state, regressed, today="2026-07-29", profile=recommendation_profile()
        )

        self.assertFalse(any(item["chain_id"] == "waist_target" for item in maintained_visible))
        waist = next(item for item in regressed_visible if item["chain_id"] == "waist_target")
        self.assertEqual((waist["level"], waist["target"]), (3, 77))

    def test_repeatable_chains_continue_after_legend(self):
        highest = next(
            item.to_dict()
            for item in recommended_templates()
            if item.chain_id == "water_streak" and item.level == 3
        )
        completed = create_challenge(highest, now="2026-07-28T09:00:00")
        completed.update({"status": "completed", "completed_at": "2026-07-28T10:00:00"})

        level_four = next(
            item for item in visible_recommendations({"completed": [completed]})
            if item["chain_id"] == "water_streak"
        )
        completed_four = create_challenge(level_four, now="2026-07-29T09:00:00")
        completed_four.update({"status": "completed", "completed_at": "2026-07-29T10:00:00"})
        level_five = next(
            item for item in visible_recommendations({"completed": [completed, completed_four]})
            if item["chain_id"] == "water_streak"
        )

        self.assertEqual((level_four["level"], level_four["target"]), (4, 150))
        self.assertEqual((level_five["level"], level_five["target"]), (5, 210))
        self.assertEqual(level_info(4)["name"], "精锐")
        self.assertEqual(level_info(5)["name"], "精锐 +1")

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
            "training_days", "exercise_reps", "training_sets", "heavy_sets",
            "effective_training_days", "effective_training_streak", "cardio_sessions",
            "time_window_sessions", "special_day_sessions",
            "water_streak", "nutrition_streak", "body_target",
        })
        self.assertEqual(set(BODY_METRICS), {
            "weight", "bodyfat", "chest_cm", "waist_cm", "hip_cm", "arm_cm",
            "thigh_cm", "calf_cm",
        })
        templates = recommended_templates(recommendation_profile())
        self.assertTrue(any(item.challenge_type == "body_target" for item in templates))
        self.assertTrue(any(item.challenge_type == "max_weight" for item in templates))
        self.assertEqual({item.lane for item in templates if item.challenge_type == "body_target"}, {"recovery"})
        for chain_id in {item.chain_id for item in templates}:
            chain = [item for item in templates if item.chain_id == chain_id]
            if len(chain) == 1:
                self.assertTrue(chain[0].config.get("one_time") or chain[0].config.get("repeatable_same"))
                self.assertEqual(chain[0].level, 0)
            else:
                self.assertEqual([item.level for item in chain], [0, 1, 2, 3])

    def test_user_curated_fixed_recommendations_and_repeat_rules(self):
        templates = recommended_templates(recommendation_profile(goal="增肌"))
        by_chain = {item.chain_id: item for item in templates}

        expected = {
            "monthly_100t": ("百吨巨兽", 100000),
            "seven_day_training_streak": ("钢铁意志", 7),
            "monthly_20_training_days": ("月度劳模", 20),
            "monthly_3000_reps": ("3000 次挑战", 3000),
            "monthly_squat_20000": ("深蹲大师", 20000),
            "monthly_effective_15": ("硬核出勤", 15),
            "five_day_intense_streak": ("魔鬼周", 5),
            "monthly_cardio_12": ("有氧达人", 12),
            "starter_monthly_5": ("初出茅庐", 5),
            "starter_three_day_streak": ("三日连胜", 3),
            "starter_volume_5000": ("力量初探", 5000),
            "starter_week_four_days": ("第一次全勤", 4),
            "starter_same_action_500": ("动作初体验", 500),
            "strength_monthly_50000": ("钢铁洪流", 50000),
            "strength_monthly_1000_reps": ("千锤百炼", 1000),
            "strength_monthly_200_sets": ("超级组魔王", 200),
            "strength_monthly_chest_10000": ("推胸狂人", 10000),
        }
        for chain_id, (title, target) in expected.items():
            self.assertIn(title, by_chain[chain_id].title)
            self.assertEqual(by_chain[chain_id].target, target)

        repeatable = create_challenge(by_chain["monthly_100t"], now="2026-07-28T09:00:00")
        repeatable.update({"status": "completed", "completed_at": "2026-07-28T10:00:00"})
        repeated = next(item for item in visible_recommendations({"completed": [repeatable]}) if item["chain_id"] == "monthly_100t")
        self.assertEqual((repeated["title"], repeated["target"]), (by_chain["monthly_100t"].title, 100000))

        one_time = create_challenge(by_chain["starter_monthly_5"], now="2026-07-28T09:00:00")
        one_time.update({"status": "completed", "completed_at": "2026-07-28T10:00:00"})
        self.assertFalse(any(item["chain_id"] == "starter_monthly_5" for item in visible_recommendations({"completed": [one_time]})))

    def test_recommended_challenge_dates_start_today_and_run_forward(self):
        templates = {item.chain_id: item for item in recommended_templates(recommendation_profile())}

        monthly = create_challenge(templates["monthly_100t"], now="2026-07-28T09:00:00")
        seven_days = create_challenge(templates["seven_day_training_streak"], now="2026-07-28T09:00:00")
        five_days = create_challenge(templates["five_day_intense_streak"], now="2026-07-28T09:00:00")
        three_days = create_challenge(templates["starter_three_day_streak"], now="2026-07-28T09:00:00")

        self.assertEqual((monthly["start_date"], monthly["end_date"]), ("2026-07-28", "2026-08-26"))
        self.assertEqual((seven_days["start_date"], seven_days["end_date"]), ("2026-07-28", "2026-08-03"))
        self.assertEqual((five_days["start_date"], five_days["end_date"]), ("2026-07-28", "2026-08-01"))
        self.assertEqual((three_days["start_date"], three_days["end_date"]), ("2026-07-28", "2026-07-30"))

    def test_new_custom_training_metrics_use_real_duration_sets_and_cardio(self):
        records = {
            "2026-07-27": {"training": {"sessions": [{
                "id": "a", "status": "completed", "total_duration_min": 50,
                "started_at": "2026-07-27T06:30:00", "ended_at": "2026-07-27T07:20:00",
                "exercises": [
                    {"id": "bench", "exercise_id": "bench", "name": "杠铃卧推", "body_part": "胸", "sets": [
                        {"completed": True, "weight_kg": 60, "reps": 10},
                        {"completed": True, "weight_kg": 20, "reps": 10, "warmup": True},
                    ]},
                    {"id": "run", "name": "跑步", "recording_mode": "cardio", "completed": True, "duration_seconds": 2400, "sets": []},
                ],
            }]}},
            "2026-07-28": {"training": {"sessions": [{
                "id": "b", "status": "completed", "total_duration_min": 45,
                "started_at": "2026-07-28T07:00:00", "ended_at": "2026-07-28T07:45:00",
                "exercises": [{"id": "bench", "exercise_id": "bench", "name": "杠铃卧推", "body_part": "胸", "sets": [
                    {"completed": True, "weight_kg": 70, "reps": 5},
                ]}],
            }]}},
        }
        base = {"start_date": "2026-07-01", "end_date": "2026-07-31", "target": 1}

        self.assertEqual(challenge_progress({**base, "challenge_type": "training_sets"}, records, today="2026-07-28")["current"], 2)
        self.assertEqual(challenge_progress({**base, "challenge_type": "heavy_sets", "min_weight": 65}, records, today="2026-07-28")["current"], 1)
        self.assertEqual(challenge_progress({**base, "challenge_type": "training_volume", "action_id": "bench"}, records, today="2026-07-28")["current"], 950)
        self.assertEqual(challenge_progress({**base, "challenge_type": "effective_training_days", "min_duration_min": 40}, records, today="2026-07-28")["current"], 2)
        self.assertEqual(challenge_progress({**base, "challenge_type": "effective_training_streak", "min_duration_min": 45}, records, today="2026-07-28")["current"], 2)
        self.assertEqual(challenge_progress({**base, "challenge_type": "cardio_sessions", "min_duration_min": 40}, records, today="2026-07-28")["current"], 1)
        self.assertEqual(challenge_progress({**base, "challenge_type": "time_window_sessions", "start_hour": 6, "end_hour": 8}, records, today="2026-07-28")["current"], 2)

    def test_personalized_recommendations_use_profile_frequency_and_macro_goal(self):
        gain = recommended_templates(recommendation_profile(goal="增肌", habit="高频训练"))
        sedentary_cut = recommended_templates(recommendation_profile(goal="减脂", habit="久坐少动"))

        gain_sessions = [item.target for item in gain if item.chain_id == "training_sessions"]
        cut_sessions = [item.target for item in sedentary_cut if item.chain_id == "training_sessions"]
        self.assertEqual(gain_sessions, [5, 10, 15, 20])
        self.assertEqual(cut_sessions, [2, 4, 6, 8])

        gain_water = next(item for item in gain if item.chain_id == "water_streak")
        cut_water = next(item for item in sedentary_cut if item.chain_id == "water_streak")
        self.assertEqual(gain_water.config["daily_target"], 2400)
        self.assertEqual(cut_water.config["daily_target"], 1800)

        gain_cycle = next(item for item in gain if item.chain_id == "carb_cycle_streak")
        self.assertIn("增肌碳循环目标", gain_cycle.title)
        gain_weight = [item.target for item in gain if item.chain_id == "weight_target"]
        self.assertEqual(gain_weight, [64.5, 67.5, 70.5, 73.5])
        expected_names = {
            "training_sessions": "别再鸽了",
            "training_consistency": "三天打鱼？",
            "training_volume": "这点重量不够看",
            "exercise_reps": "手还没酸",
            "bench_press_max_weight": "杠铃还没服",
            "squat_max_weight": "别只蹲空气",
            "deadlift_max_weight": "地板钉住了？",
            "water_streak": "水杯又失踪了",
            "protein_streak": "鸡胸别白吃",
            "carb_cycle_streak": "碳水别乱跑",
            "bodyfat_target": "腹肌还在加载",
            "waist_target": "裤腰先松口气",
            "arm_target": "袖口还很宽",
        }
        for chain_id, name in expected_names.items():
            self.assertIn(name, next(item.title for item in gain if item.chain_id == chain_id))

    def test_lane_filter_defaults_to_all_and_keeps_newcomer_group(self):
        visible = visible_recommendations({}, profile=recommendation_profile(goal="增肌"))

        all_lanes = filter_recommendations_by_lane(visible, "all")
        food = filter_recommendations_by_lane(visible, "food")
        training = filter_recommendations_by_lane(visible, "training")
        recovery = filter_recommendations_by_lane(visible, "recovery")

        self.assertEqual(all_lanes, visible)
        self.assertTrue(any(item["group"] == "新手起步" for item in all_lanes))
        self.assertTrue(all(item["lane"] == "food" for item in food))
        self.assertTrue(all(item["lane"] == "training" for item in training))
        self.assertTrue(all(item["lane"] == "recovery" for item in recovery))
        self.assertEqual(len(all_lanes), len(food) + len(training) + len(recovery))

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
        visible = visible_recommendations(before, records, today="2026-07-28")
        self.assertGreaterEqual(progress["current"], 0)
        self.assertTrue(visible)
        self.assertEqual(before, normalize_challenge_state({}))
        self.assertEqual(before["active"], [])
        self.assertEqual(before["completed"], [])
        self.assertEqual(before["pending_celebrations"], [])


if __name__ == "__main__":
    unittest.main()
