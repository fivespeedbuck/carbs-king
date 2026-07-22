import unittest
from pathlib import Path


MAIN_SOURCE = (Path(__file__).parents[1] / "src" / "main.py").read_text(encoding="utf-8-sig")


def function_body(name):
    start = MAIN_SOURCE.index(f"    def {name}(")
    next_function = MAIN_SOURCE.find("\n    def ", start + 1)
    if next_function == -1:
        return MAIN_SOURCE[start:]
    return MAIN_SOURCE[start:next_function]


class MainAnalyticsIntegrationTests(unittest.TestCase):
    def test_recovery_body_save_writes_canonical_measurement(self):
        section = function_body("render_recovery_page")

        self.assertIn('state["measurement"] = make_body_measurement(', section)
        self.assertIn("measured_at=iso_now()", section)

    def test_history_summary_uses_session_training_summary(self):
        section = function_body("render_history")

        self.assertIn("summarize_daily_training(rec, key)", section)
        self.assertIn('training_summary["has_training"]', section)
        self.assertNotIn("training_names", section)

    def test_history_body_stats_only_use_explicit_measurements(self):
        section = function_body("render_history")

        self.assertIn("normalize_body_measurement(rec, key)", section)
        self.assertIn("normalize_body_measurement(rec, d)", section)
        self.assertNotIn('to_float(profile.get("weight_kg")', section)
        self.assertNotIn("to_float(profile.get('weight_kg')", section)

    def test_previous_body_helpers_only_use_explicit_measurements(self):
        latest = function_body("latest_record_body")
        previous = function_body("get_previous_body_info")

        for section in (latest, previous):
            self.assertIn("normalize_body_measurement", section)
            self.assertNotIn('profile.get("weight_kg")', section)
            self.assertNotIn('profile.get("bodyfat_percent")', section)


if __name__ == "__main__":
    unittest.main()
