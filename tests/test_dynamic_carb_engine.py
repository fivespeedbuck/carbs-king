import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from dynamic_carb_engine import (  # noqa: E402
    build_manual_switch_prompt,
    calibration_update_is_due,
    calculate_body_energy,
    calculate_daily_target,
    classify_training,
    estimate_long_term_maintenance,
    project_daily_target_for_ui,
    select_calibration_window,
    validate_exercise_parameters,
)
from tools.simulate_dynamic_carb_personas import run_replay  # noqa: E402
from tools.replay_dynamic_carb_fixture import DEFAULT_INPUT, replay_fixture  # noqa: E402
from tools.replay_dynamic_carb_edge_cases import run_edge_replay  # noqa: E402
from training_models import TRAINING_SCHEMA_VERSION, TrainingSession  # noqa: E402


BASE_PROFILE = {
    "sex": "男", "age": 31, "height": 175, "weight": 78,
    "bodyfat": 20, "goal": "减脂", "activity_habit": "规律训练",
}


class DynamicCarbEngineTests(unittest.TestCase):
    def test_unknown_and_explicit_rest_are_distinct(self):
        unknown = classify_training({"status": "unknown"})
        rest = classify_training({"status": "explicit_rest"})
        self.assertFalse(unknown["formal"])
        self.assertEqual(unknown["day_type"], "暂定低碳")
        self.assertTrue(rest["formal"])
        self.assertEqual(rest["day_type"], "低碳日")

    def test_resistance_thresholds_use_sets_peak_and_duration(self):
        low = classify_training({"status": "completed", "resistance": {"work_sets_total": 8, "peak_primary_muscle_sets": 5, "duration_min": 40}})
        medium = classify_training({"status": "completed", "resistance": {"work_sets_total": 11, "peak_primary_muscle_sets": 8, "duration_min": 60}})
        high = classify_training({"status": "completed", "resistance": {"work_sets_total": 11, "peak_primary_muscle_sets": 10, "duration_min": 60}})
        self.assertEqual([low["demand_key"], medium["demand_key"], high["demand_key"]], ["resistance_low", "resistance_medium", "resistance_high"])

    def test_parameter_gate_distinguishes_bodyweight_from_unknown_zero(self):
        common = {"recording_mode": "strength", "parameters_confirmed": True, "sets": [{"reps": 12, "weight_kg": 0}]}
        unknown = validate_exercise_parameters(common)
        bodyweight = validate_exercise_parameters({**common, "load_kind": "bodyweight"})
        external = validate_exercise_parameters({**common, "load_kind": "external"})
        self.assertFalse(unknown["ready"])
        self.assertIn("load_kind_unknown", unknown["reason_codes"])
        self.assertTrue(bodyweight["ready"])
        self.assertTrue(external["ready"])

    def test_one_click_confirmation_can_only_use_valid_proposed_parameters(self):
        valid_unconfirmed = {
            "recording_mode": "strength", "parameters_confirmed": False, "load_kind": "added_weight",
            "sets": [{"reps": 8, "weight_kg": 10}],
        }
        self.assertTrue(validate_exercise_parameters(valid_unconfirmed, require_confirmation=False)["ready"])
        self.assertFalse(validate_exercise_parameters(valid_unconfirmed)["ready"])

    def test_training_schema_preserves_parameter_and_load_semantics(self):
        restored = TrainingSession.from_dict({
            "date": "2025-02-01",
            "exercises": [{
                "name": "辅助引体", "body_part": "背", "order": 1,
                "recording_mode": "strength", "load_kind": "assisted", "parameters_confirmed": True,
                "sets": [{"order": 1, "reps": 8, "assistance_kg": 20}],
            }],
        }).to_dict()
        self.assertEqual(TRAINING_SCHEMA_VERSION, 3)
        exercise = restored["exercises"][0]
        self.assertEqual(exercise["load_kind"], "assisted")
        self.assertTrue(exercise["parameters_confirmed"])
        self.assertEqual(exercise["sets"][0]["assistance_kg"], 20)

    def test_cardio_mapping_is_unambiguous(self):
        short_easy = classify_training({"status": "completed", "cardio": {"duration_min": 40, "intensity": "low"}})
        moderate_hour = classify_training({"status": "completed", "cardio": {"duration_min": 60, "intensity": "moderate"}})
        hard_ninety = classify_training({"status": "completed", "cardio": {"duration_min": 90, "intensity": "high"}})
        self.assertEqual(short_easy["demand_key"], "cardio_light")
        self.assertEqual(short_easy["day_type"], "低碳日")
        self.assertEqual(moderate_hour["demand_key"], "cardio_moderate")
        self.assertEqual(hard_ninety["demand_key"], "cardio_high")

    def test_macro_solver_closes_energy_and_keeps_fat_bounds(self):
        for training in (
            {"status": "explicit_rest"},
            {"status": "completed", "resistance": {"work_sets_total": 14, "peak_primary_muscle_sets": 8, "duration_min": 60}},
            {"status": "completed", "resistance": {"work_sets_total": 22, "peak_primary_muscle_sets": 11, "duration_min": 85}},
        ):
            with self.subTest(training=training):
                macro = calculate_daily_target(BASE_PROFILE, training)["recommended_macros"]
                self.assertEqual(macro["status"], "ok")
                self.assertAlmostEqual(macro["energy_closure_error"], 0, places=6)
                self.assertGreaterEqual(macro["fat_energy_share"], 0.20)
                self.assertLessEqual(macro["fat_energy_share"], 0.35)

    def test_obesity_without_bodyfat_uses_estimated_lean_mass_guard(self):
        profile = {"sex": "女", "age": 39, "height": 160, "weight": 96, "goal": "减脂", "activity_habit": "偶尔运动"}
        body = calculate_body_energy(profile)
        self.assertIn("janmahasatian_ffm_estimate", body["protein_method"])
        self.assertIsNotNone(body["lean_mass_kg"])
        self.assertLess(body["protein_g"], 96 * 1.8)

    def test_manual_day_changes_applied_but_not_recommended_result(self):
        result = calculate_daily_target(BASE_PROFILE, {"status": "explicit_rest"}, manual_day_type="高碳日")
        self.assertEqual(result["mode"], "manual")
        self.assertEqual(result["recommended_day"], "低碳日")
        self.assertEqual(result["applied_day"], "高碳日")

    def test_ui_projection_hides_internal_model_details(self):
        snapshot = calculate_daily_target(
            BASE_PROFILE,
            {"status": "completed", "resistance": {"work_sets_total": 14, "peak_primary_muscle_sets": 8, "duration_min": 60}},
            effective_date="2025-02-01",
        )
        payload = project_daily_target_for_ui(snapshot)
        self.assertEqual(payload["status"], "auto")
        self.assertEqual(payload["day_label"], "中碳日")
        self.assertEqual(set(payload["macro_targets"]), {"carb", "protein", "fat"})
        self.assertNotIn("reason_codes", str(payload))
        self.assertNotIn("parameter_set_version", payload)

    def test_manual_switch_prompt_only_appears_for_a_difference(self):
        snapshot = calculate_daily_target(BASE_PROFILE, {"status": "explicit_rest"})
        same = build_manual_switch_prompt(snapshot, "低碳日")
        different = build_manual_switch_prompt(snapshot, "高碳日")
        self.assertFalse(same["requires_confirmation"])
        self.assertTrue(different["requires_confirmation"])
        self.assertIn("建议低碳日", different["message"])

    def test_calibration_uses_shortest_eligible_window_and_never_target_day(self):
        start = date(2025, 1, 1)
        history = []
        for index in range(32):
            current = start + timedelta(days=index)
            history.append({"date": current.isoformat(), "weight_status": "observed" if index % 2 == 0 else "carried", "weight_kg": 80, "diet_day_status": "complete", "goal": "减脂"})
        result = select_calibration_window(history, (start + timedelta(days=32)).isoformat())
        self.assertTrue(result["eligible"])
        self.assertEqual(result["window_days"], 31)

    def test_long_term_calibration_recovers_independent_simulated_maintenance(self):
        start = date(2025, 1, 1)
        tissue_weight = 80.0
        truth_maintenance_at_start = 2650.0
        truth_rho = 8200.0
        truth_epsilon = 26.0
        intake = 2350.0
        history = []
        for index in range(90):
            true_maintenance = truth_maintenance_at_start + truth_epsilon * (tissue_weight - 80.0)
            tissue_weight += (intake - true_maintenance) / truth_rho
            water_noise = 0.30 * math.sin(index * 0.71)
            history.append({
                "date": (start + timedelta(days=index)).isoformat(),
                "weight_status": "observed",
                "weight_kg": tissue_weight + water_noise,
                "diet_day_status": "complete",
                "energy_intake_kcal": intake + 90 * math.sin(index * 1.31),
                "goal": "减脂",
            })
        result = estimate_long_term_maintenance(history, start + timedelta(days=90), 2300)
        true_current = truth_maintenance_at_start + truth_epsilon * (tissue_weight - 80.0)
        self.assertEqual(result["application_status"], "shadow_candidate")
        self.assertLess(abs(result["observed_maintenance_kcal"] - true_current), 180)
        self.assertGreater(result["suggested_maintenance_kcal"], 2300)
        self.assertLessEqual(result["bounded_change_kcal"], 100)

    def test_long_term_calibration_requires_numeric_complete_intake(self):
        start = date(2025, 1, 1)
        history = [{
            "date": (start + timedelta(days=index)).isoformat(),
            "weight_status": "observed",
            "weight_kg": 80 - index * 0.01,
            "diet_day_status": "complete",
            "goal": "减脂",
        } for index in range(40)]
        result = estimate_long_term_maintenance(history, start + timedelta(days=40), 2500)
        self.assertEqual(result["application_status"], "missing_numeric_inputs")

    def test_stale_recent_records_and_phase_changes_disable_calibration(self):
        start = date(2025, 1, 1)
        history = []
        for index in range(40):
            history.append({
                "date": (start + timedelta(days=index)).isoformat(),
                "weight_status": "observed" if index < 29 else "carried",
                "weight_kg": 80,
                "diet_day_status": "complete",
                "energy_intake_kcal": 2400,
                "goal": "减脂",
                "calibration_phase_id": "phase_a" if index < 20 else "phase_b",
            })
        result = estimate_long_term_maintenance(history, start + timedelta(days=40), 2500)
        self.assertEqual(result["application_status"], "not_eligible")

    def test_calibration_update_cadence_is_fourteen_days(self):
        self.assertFalse(calibration_update_is_due("2025-02-14", "2025-02-01"))
        self.assertTrue(calibration_update_is_due("2025-02-15", "2025-02-01"))

    def test_twelve_personas_run_for_a_year_without_hard_violations(self):
        report = run_replay(365)
        self.assertEqual(report["persona_count"], 12)
        self.assertEqual(report["total_person_days"], 4380)
        self.assertEqual(report["total_violations"], 0)
        calibration = report["calibration_summary"]
        self.assertEqual(calibration["reliable_logging_improved"], calibration["reliable_logging_personas"])
        self.assertGreater(calibration["biased_logging_worsened"], 0)
        self.assertEqual(calibration["product_mode"], "shadow_only")

    def test_canonical_100_day_fixture_replays_through_reference_engine(self):
        report = replay_fixture(DEFAULT_INPUT)
        self.assertEqual(report["record_days"], 100)
        self.assertEqual(report["new_day_types"], {"中碳日": 47, "低碳日": 39, "高碳日": 14})
        self.assertEqual(report["violations"], [])

    def test_non_negotiable_edge_case_replay_has_no_failures(self):
        report = run_edge_replay()
        self.assertEqual(report["case_count"], 18)
        self.assertEqual(report["failure_count"], 0)


if __name__ == "__main__":
    unittest.main()
