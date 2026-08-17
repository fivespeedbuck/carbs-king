import sys
import unittest
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynamic_carb_adapter import calculate_app_snapshot, engine_from_snapshot, normalize_profile, normalize_training, targets_from_snapshot  # noqa: E402
from dynamic_carb_engine import MODEL_DOCUMENT_SHA256, create_phase_baseline  # noqa: E402


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


def completed_strength_session(name: str, body_part: str, sets: int) -> dict:
    exercise = strength_exercise(name=name, body_part=body_part, sets=sets)
    for item in exercise["sets"]:
        item["completed"] = True
    return {"status": "completed", "exercises": [exercise]}


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

    def test_completed_legacy_positive_weight_inference_is_explicitly_auditable(self):
        exercise = strength_exercise(sets=2, load_kind="unknown", confirmed=False)
        for item in exercise["sets"]:
            item["completed"] = True
        facts = normalize_training({"session": {
            "date": "2026-08-02",
            "status": "completed",
            "exercises": [exercise],
        }})

        self.assertEqual(facts["status"], "completed")
        self.assertEqual(facts["legacy_load_inference_count"], 1)
        self.assertEqual(
            facts["migration_flags"],
            ["legacy_positive_weight_unknown_load_inferred_external"],
        )

    def test_completed_legacy_unknown_load_counts_valid_work_without_guessing_semantics(self):
        exercise = strength_exercise(name="辅助引体向上", body_part="背", sets=4, load_kind="unknown", confirmed=False)
        for item in exercise["sets"]:
            item["weight_kg"] = 0
            item["completed"] = True
        facts = normalize_training({"session": {
            "date": "2026-08-02",
            "status": "completed",
            "exercises": [exercise],
        }})

        self.assertEqual(facts["status"], "completed")
        self.assertEqual(facts["resistance"]["work_sets_total"], 4)
        self.assertEqual(facts["legacy_unknown_load_counted_sets"], 4)
        self.assertEqual(facts["legacy_unknown_load_counted_exercises"], 1)
        self.assertEqual(
            facts["migration_flags"],
            ["legacy_completed_unknown_load_counted_without_load_semantics"],
        )

    def test_completed_legacy_unknown_load_still_rejects_missing_reps(self):
        exercise = strength_exercise(sets=1, load_kind="unknown", confirmed=False)
        exercise["sets"][0].update({"weight_kg": 0, "reps": 0, "completed": True})

        facts = normalize_training({"session": {
            "date": "2026-08-02",
            "status": "completed",
            "exercises": [exercise],
        }})

        self.assertEqual(facts["status"], "outcome_unknown")
        self.assertNotIn("resistance", facts)

    def test_adapter_counts_only_medium_or_higher_individual_sessions_for_upgrade(self):
        two_low = normalize_training({"sessions": [
            completed_strength_session("弯举", "二头", 4),
            completed_strength_session("卷腹", "腹", 4),
        ]})
        two_medium = normalize_training({"sessions": [
            completed_strength_session("卧推", "胸", 8),
            completed_strength_session("划船", "背", 8),
        ]})

        self.assertNotIn("medium_or_higher_sessions", two_low)
        self.assertEqual(two_medium["medium_or_higher_sessions"], 2)
        self.assertEqual(calculate_app_snapshot(state({"sessions": [
            completed_strength_session("弯举", "二头", 4),
            completed_strength_session("卷腹", "腹", 4),
        ]}))["engine_snapshot"]["recommended_day"], "低碳日")

    def test_unknown_cardio_intensity_is_conservative_and_segments_do_not_use_maximum(self):
        unknown = normalize_training({"session": {
            "status": "planned",
            "exercises": [{"recording_mode": "cardio", "duration_seconds": 3600, "parameters_confirmed": True}],
        }})
        segmented = normalize_training({"session": {
            "status": "planned",
            "exercises": [
                {"recording_mode": "cardio", "duration_seconds": 3000, "legacy_intensity": "低强度", "parameters_confirmed": True},
                {"recording_mode": "cardio", "duration_seconds": 600, "legacy_intensity": "高强度", "parameters_confirmed": True},
            ],
        }})

        self.assertEqual(unknown["cardio"]["intensity"], "unknown")
        self.assertEqual(unknown["cardio"]["effective_minutes"], 30)
        self.assertEqual(calculate_app_snapshot(state({"session": {
            "status": "planned", "exercises": [{"recording_mode": "cardio", "duration_seconds": 3600, "parameters_confirmed": True}],
        }}))["engine_snapshot"]["recommended_day"], "低碳日")
        self.assertEqual(segmented["cardio"]["effective_minutes"], 37.5)

    def test_mixed_session_total_duration_is_not_assigned_to_resistance(self):
        strength = strength_exercise(sets=4)
        cardio = {"recording_mode": "cardio", "duration_seconds": 1800, "legacy_intensity": "低强度", "parameters_confirmed": True}
        current = state({"session": {
            "status": "planned", "total_duration_min": 60, "exercises": [strength, cardio],
        }})
        snapshot = calculate_app_snapshot(current)

        self.assertIsNone(snapshot["training_facts"]["resistance"]["duration_min"])
        self.assertEqual(snapshot["engine_snapshot"]["recommended_day"], "高碳日")

    def test_timed_strength_or_mobility_work_is_not_counted_as_cardio(self):
        facts = normalize_training({"session": {
            "status": "completed",
            "exercises": [{
                "name": "平板支撑",
                "recording_mode": "timed",
                "duration_seconds": 300,
                "completed": True,
            }],
        }})

        self.assertEqual(facts["status"], "outcome_unknown")
        self.assertNotIn("cardio", facts)

    def test_confirmed_leg_training_produces_formal_high_day_snapshot(self):
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
        current["day_type"] = "低碳日"
        snapshot = calculate_app_snapshot(current, calculated_at="2026-08-02T08:00:00")
        self.assertEqual(snapshot["engine_snapshot"]["recommended_day"], "高碳日")
        self.assertEqual(snapshot["engine_snapshot"]["applied_day"], "低碳日")
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
        self.assertEqual(
            targets_from_snapshot(recomputed)["carb"],
            original["shown_target_snapshot"]["projection"]["macro_targets"]["carb"]["center_g"],
        )
        self.assertEqual(
            recomputed["shown_target_snapshot"]["engine_snapshot"],
            original["shown_target_snapshot"]["engine_snapshot"],
        )
        self.assertEqual(
            recomputed["recomputed_actual_ledger"]["recommended_day"],
            "暂定低碳",
        )

    def test_future_bodyfat_measurement_is_not_used_for_a_past_target(self):
        current = state()
        current["bodyfat_measured_at"] = "2026-08-05T08:00:00"
        snapshot = calculate_app_snapshot(current, effective_date="2026-08-02")

        self.assertEqual(snapshot["profile_facts"]["bodyfat_status"], "future_unavailable")
        self.assertNotIn("bodyfat_percent", snapshot["profile_facts"])

    def test_weight_only_measurement_does_not_refresh_carried_bodyfat(self):
        facts = normalize_profile({
            "weight": 60,
            "bodyfat": 20,
            "bodyfat_measured_at": "2026-07-01T08:00:00",
            "measurement": {
                "weight_kg": 59.5,
                "measured_at": "2026-08-02T08:00:00",
            },
        }, effective_date="2026-08-02")

        self.assertEqual(facts["bodyfat_status"], "carried")
        self.assertEqual(facts["bodyfat_age_days"], 32)

    def test_historical_shown_macros_and_body_metadata_share_one_immutable_engine(self):
        original = calculate_app_snapshot(state(), calculated_at="2026-08-02T08:00:00")
        changed = state()
        changed.update({"age": "50", "weight": "75"})
        frozen = calculate_app_snapshot(
            changed,
            existing=original,
            freeze_shown=True,
            calculated_at="2026-08-05T08:00:00",
        )

        self.assertEqual(engine_from_snapshot(frozen)["body"]["age_years"], 30)
        self.assertEqual(engine_from_snapshot(frozen)["body"]["weight_kg"], 60)
        self.assertEqual(frozen["engine_snapshot"]["body"]["age_years"], 50)
        self.assertEqual(frozen["engine_snapshot"]["body"]["weight_kg"], 75)

    def test_snapshot_binds_model_hash_and_separates_planned_from_actual_input_sha(self):
        current = state({"session": {
            "status": "planned", "exercises": [strength_exercise(sets=10)],
        }})
        snapshot = calculate_app_snapshot(current, calculated_at="2026-08-02T08:00:00")

        shown = snapshot["shown_target_snapshot"]
        self.assertEqual(snapshot["model_document_sha256"], MODEL_DOCUMENT_SHA256)
        self.assertEqual(shown["model_document_sha256"], MODEL_DOCUMENT_SHA256)
        self.assertTrue(shown["solver_context_sha256"])
        self.assertNotEqual(snapshot["input_revision"], snapshot["recomputed_actual_ledger"]["input_revision"])

    def test_pending_baseline_refresh_promotes_only_when_effective_date_arrives(self):
        today = date.today()
        current = state()
        current["date"] = today.isoformat()
        profile = normalize_profile(current, today.isoformat())
        base = create_phase_baseline(profile, today - timedelta(days=7))
        pending = {
            **base,
            "phase_id": "phase-promoted",
            "previous_phase_id": base["phase_id"],
            "started_at": today.isoformat(),
            "effective_from": today.isoformat(),
            "baseline_weight_kg": 59.5,
            "fat_anchor_g": 47.6,
        }
        current["carb_phase"] = {**base, "pending_refresh": pending}

        snapshot = calculate_app_snapshot(current)

        self.assertEqual(current["carb_phase"]["phase_id"], "phase-promoted")
        self.assertEqual(snapshot["profile_facts"]["phase_id"], "phase-promoted")

    def test_completed_and_planned_sessions_are_not_labeled_as_completed_sample(self):
        completed = completed_strength_session("卧推", "胸", 4)
        planned = strength_exercise("深蹲", "腿", 20)
        facts = normalize_training({
            "sessions": [completed, {"status": "planned", "exercises": [planned]}],
        })
        actual = normalize_training({
            "sessions": [completed, {"status": "planned", "exercises": [planned]}],
        }, completed_only=True)

        self.assertEqual(facts["status"], "planned_confirmed")
        self.assertEqual(facts["resistance"]["work_sets_total"], 24)
        self.assertEqual(actual["status"], "completed")
        self.assertEqual(actual["resistance"]["work_sets_total"], 4)

    def test_pending_training_overrides_a_stale_rest_target(self):
        pending = strength_exercise(sets=1, confirmed=False, load_kind="unknown")
        facts = normalize_training({
            "targets": [{"target": "休息"}],
            "session": {"status": "planned", "exercises": [pending]},
        })

        self.assertEqual(facts["status"], "planned_pending")


if __name__ == "__main__":
    unittest.main()
