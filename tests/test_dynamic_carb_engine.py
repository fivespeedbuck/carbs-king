import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from dynamic_carb_engine import (  # noqa: E402
    DISPLAY_FAT_SHARE_ROUNDING_TOLERANCE,
    MODEL_DOCUMENT_SHA256,
    build_manual_switch_prompt,
    calibration_update_is_due,
    calculate_body_energy,
    calculate_daily_target,
    classify_training,
    create_phase_baseline,
    estimate_long_term_maintenance,
    evaluate_baseline_refresh,
    project_daily_target_for_ui,
    select_calibration_window,
    solve_period_preview,
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

    def test_resistance_tiers_use_primary_body_part(self):
        low = classify_training({"status": "completed", "body_parts": ["二头"], "resistance": {"work_sets_total": 24}})
        medium = classify_training({"status": "completed", "body_parts": ["胸"], "resistance": {"work_sets_total": 4}})
        high = classify_training({"status": "completed", "body_parts": ["背"], "resistance": {"work_sets_total": 4}})
        self.assertEqual([low["demand_key"], medium["demand_key"], high["demand_key"]], ["resistance_low", "resistance_medium", "resistance_high"])

    def test_two_low_sessions_do_not_upgrade_but_two_medium_sessions_do(self):
        aggregated_low = classify_training({
            "status": "completed", "sessions": 2, "medium_or_higher_sessions": 0,
            "body_parts": ["二头"], "resistance": {"work_sets_total": 8, "peak_body_part_sets": 4, "duration_min": 40},
        })
        two_medium = classify_training({
            "status": "completed", "sessions": 2, "medium_or_higher_sessions": 2,
            "body_parts": ["胸"], "resistance": {"work_sets_total": 16, "peak_body_part_sets": 8, "duration_min": 80},
        })

        self.assertEqual(aggregated_low["demand_key"], "resistance_low")
        self.assertEqual(two_medium["demand_key"], "mixed_high")

    def test_combining_sessions_or_modalities_never_downgrades_higher_cardio_demand(self):
        for extra in (
            {"medium_or_higher_sessions": 2},
            {"close_second_high_glycogen_session": True},
            {"resistance": {"work_sets_total": 14, "peak_body_part_sets": 8, "duration_min": 60}},
        ):
            with self.subTest(extra=extra):
                result = classify_training({
                    "status": "completed",
                    "cardio": {"duration_min": 130, "effective_minutes": 130, "intensity": "moderate"},
                    **extra,
                })
                self.assertEqual(result["demand_key"], "endurance_long")

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
        self.assertEqual(TRAINING_SCHEMA_VERSION, 4)
        exercise = restored["exercises"][0]
        self.assertEqual(exercise["load_kind"], "assisted")
        self.assertTrue(exercise["parameters_confirmed"])
        self.assertEqual(exercise["sets"][0]["assistance_kg"], 20)

        rated = TrainingSession.from_dict({
            "date": "2026-08-02",
            "status": "completed",
            "session_rating": 5,
        }).to_dict()
        self.assertEqual(rated["session_rating"], 5)
        self.assertIsNone(TrainingSession.from_dict({"date": "2026-08-02", "session_rating": 9}).session_rating)

    def test_cardio_mapping_is_unambiguous(self):
        short_easy = classify_training({"status": "completed", "cardio": {"duration_min": 40, "intensity": "low"}})
        moderate_hour = classify_training({"status": "completed", "cardio": {"duration_min": 60, "intensity": "moderate"}})
        hard_ninety = classify_training({"status": "completed", "cardio": {"duration_min": 90, "intensity": "high"}})
        self.assertEqual(short_easy["demand_key"], "cardio_light")
        self.assertEqual(short_easy["day_type"], "低碳日")
        self.assertEqual(moderate_hour["demand_key"], "cardio_high")
        self.assertEqual(hard_ninety["demand_key"], "cardio_high")

    def test_one_high_intensity_minute_cannot_upgrade_four_easy_hours_to_extreme(self):
        result = classify_training({
            "status": "completed",
            "cardio": {"duration_min": 240, "effective_minutes": 120.75, "intensity": "high"},
        })

        self.assertEqual(result["demand_key"], "endurance_long")

    def test_macro_solver_closes_energy_and_keeps_fat_floor(self):
        for training in (
            {"status": "explicit_rest"},
            {"status": "completed", "body_parts": ["胸"], "resistance": {"work_sets_total": 14}},
            {"status": "completed", "body_parts": ["背"], "resistance": {"work_sets_total": 22}},
        ):
            with self.subTest(training=training):
                macro = calculate_daily_target(BASE_PROFILE, training)["recommended_macros"]
                self.assertEqual(macro["status"], "ok")
                self.assertAlmostEqual(macro["energy_closure_error"], 0, places=6)
                self.assertAlmostEqual(macro["fat_g"] / BASE_PROFILE["weight"], 1.0)

    def test_automatic_low_medium_high_distribution_is_distinct(self):
        trainings = (
            {"status": "explicit_rest"},
            {"status": "completed", "body_parts": ["胸"], "resistance": {"work_sets_total": 14}},
            {"status": "completed", "body_parts": ["背"], "resistance": {"work_sets_total": 22}},
        )
        macros = [calculate_daily_target(BASE_PROFILE, training)["recommended_macros"] for training in trainings]

        self.assertLess(macros[0]["carb_g"], macros[1]["carb_g"])
        self.assertLess(macros[1]["carb_g"], macros[2]["carb_g"])
        self.assertEqual(len({round(item["protein_g"], 8) for item in macros}), 1)
        self.assertTrue(all(abs(item["fat_g"] - BASE_PROFILE["weight"]) < 1e-9 for item in macros))
        for macro in macros:
            self.assertAlmostEqual(macro["energy_closure_error"], 0, places=6)

    def test_endurance_demand_may_exceed_distribution_carb_but_never_breaks_fat_floor(self):
        macro = calculate_daily_target(
            BASE_PROFILE,
            {"status": "completed", "cardio": {"duration_min": 240, "effective_minutes": 240, "intensity": "moderate"}},
        )["recommended_macros"]

        self.assertEqual(macro["status"], "ok")
        self.assertAlmostEqual(macro["fat_g"] / BASE_PROFILE["weight"], 1.0)

    def test_supported_scope_starts_at_nineteen(self):
        with self.assertRaises(ValueError):
            calculate_body_energy({**BASE_PROFILE, "age": 18})
        self.assertEqual(calculate_body_energy({**BASE_PROFILE, "age": 19})["age_years"], 19)

    def test_weight_validation_matches_profile_limit(self):
        for weight in (24, 501):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                calculate_body_energy({**BASE_PROFILE, "weight": weight})

    def test_obesity_without_bodyfat_uses_estimated_lean_mass_guard(self):
        profile = {"sex": "女", "age": 39, "height": 160, "weight": 96, "goal": "减脂", "activity_habit": "偶尔运动"}
        body = calculate_body_energy(profile)
        self.assertEqual(body["protein_method"], "wiki_goal_bodyweight_fixed")
        self.assertIsNone(body["lean_mass_kg"])
        self.assertAlmostEqual(body["protein_g"], 96 * 1.7)

    def test_stale_bodyfat_remains_displayable_but_does_not_anchor_protein(self):
        body = calculate_body_energy({
            **BASE_PROFILE,
            "bodyfat": 25,
            "bodyfat_status": "carried",
            "bodyfat_age_days": 120,
        })

        self.assertAlmostEqual(body["lean_mass_kg"], 58.5)
        self.assertEqual(body["protein_method"], "wiki_goal_bodyweight_fixed")

    def test_elderly_obesity_fallback_does_not_reinflate_protein_by_actual_weight(self):
        body = calculate_body_energy({
            "sex": "女", "age": 70, "height": 160, "weight": 100,
            "goal": "保持", "activity_habit": "偶尔运动",
        })

        self.assertEqual(body["protein_g"], 175)
        self.assertEqual(body["protein_method"], "wiki_goal_bodyweight_fixed")

    def test_manual_day_changes_applied_but_not_recommended_result(self):
        result = calculate_daily_target(BASE_PROFILE, {"status": "explicit_rest"}, manual_day_type="高碳日")
        self.assertEqual(result["mode"], "runtime_fixed_day")
        self.assertEqual(result["override_mode"], "manual")
        self.assertEqual(result["recommended_day"], "低碳日")
        self.assertEqual(result["applied_day"], "高碳日")

    def test_manual_same_high_label_preserves_recommended_demand_grams(self):
        training = {"status": "completed", "cardio": {"duration_min": 60, "intensity": "moderate"}}
        automatic = calculate_daily_target(BASE_PROFILE, training)
        acknowledged = calculate_daily_target(BASE_PROFILE, training, manual_day_type="高碳日")

        self.assertEqual(automatic["recommended_demand"]["demand_key"], "cardio_high")
        for key in ("energy_internal_kcal", "protein_internal_g", "carb_internal_g", "fat_internal_g"):
            self.assertEqual(acknowledged["applied_macros"][key], automatic["recommended_macros"][key])
        self.assertIn("manual_day_override", acknowledged["applied_macros"]["reason_codes"])

    def test_wiki_goal_budgets_are_reproducible(self):
        gain = calculate_body_energy({**BASE_PROFILE, "goal": "增肌"})
        cut = calculate_body_energy(BASE_PROFILE)

        self.assertAlmostEqual(gain["guarded_budget_kcal_day"], 78 * (4 * 3.5 + 4 * 1.8 + 9 * 1.0))
        self.assertAlmostEqual(cut["guarded_budget_kcal_day"], 78 * (4 * 3.0 + 4 * 1.7 + 9 * 1.0))
        self.assertIn("wiki_goal_baseline", cut["budget_reason_codes"])

    def test_runtime_uses_versioned_reference_distribution_and_strict_display_order(self):
        result = calculate_daily_target({**BASE_PROFILE, "goal": "保持"}, {"status": "explicit_rest"})
        runtime = result["runtime_distribution"]

        self.assertEqual(result["mode"], "runtime_fixed_day")
        self.assertEqual(runtime["counts"], {"low": 3, "mid": 2, "high": 2})
        self.assertTrue(runtime["feasible"])
        self.assertTrue(runtime["display_tier_contract"]["ordered"])
        self.assertTrue(runtime["display_tier_contract"]["distinct_macro_signatures"])
        self.assertAlmostEqual(runtime["period_closure_error_kcal"], 0, places=8)

    def test_period_preview_reports_actual_mix_deviation_from_reference(self):
        preview = solve_period_preview({**BASE_PROFILE, "goal": "保持"}, {"low": 2, "mid": 2, "high": 1})
        blocked = solve_period_preview(BASE_PROFILE, {"low": 0, "mid": 0, "high": 7})

        self.assertEqual(preview["mode"], "period_preview_constrained")
        self.assertTrue(preview["feasible"])
        self.assertNotAlmostEqual(preview["period_total_closure_error_kcal"], 0, places=7)
        self.assertIn("period_mix_differs_from_reference", preview["reason_codes"])
        self.assertTrue(blocked["feasible"])
        self.assertIn("period_mix_differs_from_reference", blocked["reason_codes"])

    def test_phase_baseline_binds_the_frozen_model_document_hash(self):
        phase = create_phase_baseline(BASE_PROFILE, "2026-08-03")
        self.assertEqual(phase["model_document_sha256"], MODEL_DOCUMENT_SHA256)
        self.assertEqual(MODEL_DOCUMENT_SHA256, "8C680ABD0F34EC73C1D4B21D96D3345A4DD480B6B73491638F76EC9A1A3E79B4")

    def test_baseline_refresh_is_order_independent_and_only_effective_next_day(self):
        as_of = date(2026, 8, 3)
        weights = [
            {"record_id": f"w-{index:02d}", "date": (as_of - timedelta(days=22 - index * 2)).isoformat(), "weight_kg": 78 - index * 0.05}
            for index in range(12)
        ]
        bodyfat = [{"record_id": "bf-1", "date": as_of.isoformat(), "bodyfat_percent": 20}]
        kwargs = dict(
            baseline_weight_kg=78,
            target="减脂",
            sex="男",
            height_cm=175,
            age_years=31,
            as_of_date=as_of,
        )
        ordered = evaluate_baseline_refresh(weights, bodyfat, **kwargs)
        reversed_result = evaluate_baseline_refresh(list(reversed(weights)), bodyfat, **kwargs)

        self.assertTrue(ordered["refresh"])
        self.assertEqual(ordered, reversed_result)
        self.assertEqual(ordered["window_end"], "2026-08-03")
        self.assertEqual(ordered["effective_from"], "2026-08-04")
        self.assertFalse(ordered["affects_past"])

        old_only = evaluate_baseline_refresh(
            [{**item, "date": item["date"].replace("2026", "2025")} for item in weights],
            [],
            **kwargs,
        )
        self.assertFalse(old_only["refresh"])
        self.assertNotIn("effective_from", old_only)

    def test_ui_projection_hides_internal_model_details(self):
        snapshot = calculate_daily_target(
            BASE_PROFILE,
            {"status": "completed", "body_parts": ["胸"], "resistance": {"work_sets_total": 14}},
            effective_date="2025-02-01",
        )
        payload = project_daily_target_for_ui(snapshot)
        self.assertEqual(payload["status"], "auto")
        self.assertEqual(payload["day_label"], "中碳日")
        self.assertEqual(set(payload["macro_targets"]), {"carb", "protein", "fat"})
        self.assertNotIn("reason_codes", str(payload))
        self.assertNotIn("parameter_set_version", payload)

    def test_displayed_macro_centers_close_the_displayed_energy(self):
        profile = {
            "sex": "女", "age": 65, "height": 150, "weight": 40,
            "bodyfat": 10, "goal": "保持", "activity_habit": "规律训练",
        }
        snapshot = calculate_daily_target(
            profile,
            {"status": "completed", "cardio": {"duration_min": 60, "intensity": "moderate"}},
        )
        payload = project_daily_target_for_ui(snapshot)
        macros = payload["macro_targets"]
        visible_kcal = (
            4 * macros["carb"]["center_g"]
            + 4 * macros["protein"]["center_g"]
            + 9 * macros["fat"]["center_g"]
        )
        self.assertAlmostEqual(visible_kcal, payload["energy_kcal"], delta=0.5)
        self.assertAlmostEqual(macros["fat"]["center_g"], 46.0)

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
        self.assertEqual(report["new_day_types"], {"中碳日": 29, "高碳日": 29, "低碳日": 14, "暂定低碳": 28})
        self.assertEqual(
            report["recommendation_states"],
            {"formal_medium": 29, "formal_high": 29, "formal_low": 14, "provisional_low": 28},
        )
        self.assertEqual(report["demand_types"]["cardio_light"], 14)
        self.assertEqual(report["demand_types"]["provisional_low"], 28)
        self.assertEqual(report["violations"], [])

    def test_non_negotiable_edge_case_replay_has_no_failures(self):
        report = run_edge_replay()
        self.assertEqual(report["case_count"], 18)
        self.assertEqual(report["failure_count"], 0)


if __name__ == "__main__":
    unittest.main()
