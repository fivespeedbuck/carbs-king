import unittest
from pathlib import Path


MAIN_SOURCE = (Path(__file__).parents[1] / "src" / "main.py").read_text(encoding="utf-8-sig")
RECOVERY_SOURCE = (Path(__file__).parents[1] / "src" / "recovery_controller.py").read_text(encoding="utf-8-sig")
DATA_RECORD_SOURCE = (Path(__file__).parents[1] / "src" / "data_record_controller.py").read_text(encoding="utf-8-sig")
DAILY_RECORD_SOURCE = (Path(__file__).parents[1] / "src" / "daily_record_controller.py").read_text(encoding="utf-8-sig")
ANALYTICS_SOURCE = (Path(__file__).parents[1] / "src" / "analytics_model.py").read_text(encoding="utf-8-sig")
ANALYTICS_SERVICE_SOURCE = (Path(__file__).parents[1] / "src" / "analytics_service.py").read_text(encoding="utf-8-sig")
APP_DEFAULTS_SOURCE = (Path(__file__).parents[1] / "src" / "app_defaults.py").read_text(encoding="utf-8-sig")


def function_body(name):
    start = MAIN_SOURCE.index(f"    def {name}(")
    next_function = MAIN_SOURCE.find("\n    def ", start + 1)
    if next_function == -1:
        return MAIN_SOURCE[start:]
    return MAIN_SOURCE[start:next_function]


class MainAnalyticsIntegrationTests(unittest.TestCase):
    def test_recovery_body_save_writes_canonical_measurement(self):
        section = RECOVERY_SOURCE[RECOVERY_SOURCE.index("    def render_recovery_page"):]

        self.assertIn('state["measurement"] = make_body_measurement(', section)
        self.assertIn("measured_at=iso_now()", section)

    def test_history_summary_uses_session_training_summary(self):
        section = ANALYTICS_SOURCE

        self.assertIn("summarize_daily_training(record, key)", section)
        self.assertIn('training["has_training"]', section)
        self.assertNotIn("training_names", section)

    def test_history_body_stats_only_use_explicit_measurements(self):
        section = ANALYTICS_SERVICE_SOURCE

        self.assertIn("normalize_body_measurement(record, key)", section)
        self.assertIn('"carried_weight_kg"', section)
        self.assertIn('"weight_kg": measurement["weight_kg"]', section)

    def test_previous_body_helpers_only_use_explicit_measurements(self):
        start = DAILY_RECORD_SOURCE.index("    def latest_body(")
        end = DAILY_RECORD_SOURCE.index("    def payload(", start)
        latest = DAILY_RECORD_SOURCE[start:end]
        self.assertIn("normalize_body_measurement", latest)
        self.assertNotIn('profile.get("weight_kg")', latest)
        self.assertNotIn('profile.get("bodyfat_percent")', latest)

    def test_data_page_has_explicit_fullscreen_circumference_recording(self):
        section = DATA_RECORD_SOURCE[DATA_RECORD_SOURCE.index("    def render_data_page"):]
        self.assertIn('full_form_sheet("记录围度"', section)
        self.assertIn("CIRCUMFERENCE_FIELDS", section)
        self.assertIn('("calf_cm", "小腿围")', APP_DEFAULTS_SOURCE)
        self.assertIn('"chart_kind": "circumference"', section)
        self.assertIn('daily_records.update_circumference(', section)
        self.assertIn('daily_records.update_calendar_event(selected_date, event)', section)
        self.assertNotIn('repositories.records.save(records)', section)

    def test_data_page_trend_uses_today_and_period_change_clears_stale_point(self):
        section = DATA_RECORD_SOURCE[DATA_RECORD_SOURCE.index("    def render_data_page"):]

        self.assertIn("end_date=deps.today().isoformat()", section)
        self.assertIn("update_data_page(period_days=days, selected_trend_date=None)", section)

    def test_all_main_navigation_routes_share_profile_transient_reset(self):
        section = function_body("set_view")
        self.assertIn("reset_transient_navigation_state(state, previous_view, name)", section)


if __name__ == "__main__":
    unittest.main()
