import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analytics_views import (  # noqa: E402
    CHART_OPTIONS,
    DataPageConfig,
    build_data_page_model,
    build_data_page_view,
    build_main_data_page_hook,
)


def completed_set(weight=50, reps=10):
    return {"weight_kg": weight, "reps": reps, "completed": True}


def session(body_part, *, sets=None):
    return {
        "id": body_part,
        "status": "completed",
        "total_duration_min": 45,
        "exercises": [{"name": f"{body_part}训练", "body_part": body_part, "sets": sets or [completed_set()]}],
    }


def named_session(body_part, exercise_name, *, sets=None):
    return {
        "id": f"{body_part}-{exercise_name}",
        "status": "completed",
        "total_duration_min": 45,
        "exercises": [{"name": exercise_name, "body_part": body_part, "sets": sets or [completed_set()]}],
    }


class AnalyticsViewModelTests(unittest.TestCase):
    def test_default_period_is_seven_days_and_can_switch_to_30_or_90(self):
        default_model = build_data_page_model({}, end_date="2026-07-21")
        self.assertEqual(default_model["summary"]["period_days"], 7)
        self.assertEqual(len(default_model["series"]), 7)

        for days in (30, 90):
            model = build_data_page_model({}, end_date="2026-07-21", config=DataPageConfig(period_days=days))
            self.assertEqual(model["summary"]["period_days"], days)
            self.assertEqual(len(model["series"]), days)

    def test_each_domain_has_one_main_trend_series(self):
        records = {
            "2026-07-20": {
                "profile": {
                    "measurement": {
                        "weight_kg": 71.2,
                        "bodyfat_percent": 17.8,
                        "waist_cm": 82.5,
                        "measured_at": "2026-07-20T07:20:00+08:00",
                    },
                    "day_type": "中碳日",
                },
                "daily_total": {"kcal": 1850, "protein": 130},
                "meals": {"早餐": [{"name": "燕麦"}]},
                "training": {"session": session("胸")},
                "sleep": {"total_minutes": 450, "bed_time": "23:30", "wake_time": "07:00"},
            }
        }

        for chart_kind, _ in CHART_OPTIONS:
            model = build_data_page_model(
                records,
                end_date="2026-07-21",
                config=DataPageConfig(chart_kind=chart_kind),
            )
            self.assertEqual(model["trend"]["chart_kind"], chart_kind)
            self.assertEqual(len(model["trend"]["points"]), 7)
            self.assertEqual(model["trend"]["recorded_count"], 1)

    def test_calendar_separates_rest_from_unrecorded_and_keeps_custom_events(self):
        records = {
            "2026-07-01": {"profile": {"day_type": "低碳日"}, "calendar_event": {"type": "rest"}},
            "2026-07-02": {"calendar_event": {"type": "custom", "text": "出差"}},
            "2026-07-03": {"profile": {"day_type": "高碳日"}, "training": {"session": session("背")}},
        }
        model = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(active_tab="月历"))
        days = {item["date"]: item for item in model["calendar"] if item.get("date")}

        self.assertEqual(days["2026-07-01"]["record_state"], "rest")
        self.assertEqual(days["2026-07-01"]["activity_type"], "rest")
        self.assertEqual(days["2026-07-02"]["record_state"], "recorded")
        self.assertEqual(days["2026-07-02"]["activity_type"], "custom")
        self.assertEqual(days["2026-07-03"]["activity_type"], "training")
        self.assertEqual(days["2026-07-04"]["record_state"], "unrecorded")
        self.assertGreater(model["summary"]["unrecorded_days"], 0)

    def test_calendar_month_summary_uses_real_month_records_only(self):
        records = {
            "2026-06-30": {
                "daily_total": {"kcal": 9999},
                "meals": {"早餐": [{"name": "不应计入"}]},
                "training": {"session": session("腿")},
            },
            "2026-07-01": {
                "daily_total": {"kcal": 1800},
                "meals": {"早餐": [{"name": "燕麦"}]},
                "training": {"session": session("胸", sets=[completed_set(80, 5), completed_set(60, 8)])},
            },
            "2026-07-02": {
                "daily_total": {"kcal": 2200},
                "meals": {"午餐": [{"name": "米饭"}]},
                "training": {"session": session("背", sets=[completed_set(70, 8)])},
            },
            "2026-07-03": {"daily_total": {"kcal": 0}, "meals": {}},
        }
        model = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(active_tab="月历"))
        summary = model["calendar_summary"]

        self.assertEqual(summary["training_days"], 2)
        self.assertEqual(summary["training_duration_min"], 90)
        self.assertEqual(summary["formal_sets"], 3)
        self.assertEqual(summary["total_kcal"], 4000)
        self.assertEqual(summary["diet_recorded_days"], 2)
        self.assertEqual(summary["avg_kcal_on_diet_days"], 2000)

    def test_calendar_month_summary_missing_values_are_none(self):
        model = build_data_page_model({}, end_date="2026-07-21", config=DataPageConfig(active_tab="月历"))
        summary = model["calendar_summary"]

        self.assertIsNone(summary["training_days"])
        self.assertIsNone(summary["training_duration_min"])
        self.assertIsNone(summary["formal_sets"])
        self.assertIsNone(summary["total_kcal"])
        self.assertIsNone(summary["diet_recorded_days"])
        self.assertIsNone(summary["avg_kcal_on_diet_days"])

    def test_calendar_cells_compress_labels_by_priority(self):
        records = {
            "2026-07-05": {
                "profile": {"day_type": "高碳日"},
                "calendar_event": {"type": "custom", "text": "出差"},
                "training": {"session": session("胸")},
            },
            "2026-07-06": {
                "profile": {"day_type": "低碳日"},
                "calendar_event": {"type": "rest"},
            },
        }
        model = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(active_tab="月历"))
        days = {item["date"]: item for item in model["calendar"] if item.get("date")}

        self.assertEqual(days["2026-07-05"]["compact_labels"], ["高碳日", "胸"])
        self.assertNotIn("出差", days["2026-07-05"]["compact_labels"])
        self.assertEqual(days["2026-07-06"]["compact_labels"], ["低碳日", "休息"])
        self.assertEqual(days["2026-07-07"]["compact_labels"], ["无记录"])

    def test_calendar_selected_date_detail_defaults_and_can_be_configured(self):
        records = {
            "2026-07-05": {
                "profile": {"day_type": "中碳日"},
                "daily_total": {"kcal": 1900, "carb": 180, "protein": 130, "fat": 55},
                "meals": {"早餐": [{"name": "燕麦"}]},
                "training": {"session": session("肩")},
            },
            "2026-07-21": {"calendar_event": {"type": "custom", "text": "加班"}},
        }
        default_model = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(active_tab="月历"))
        selected_model = build_data_page_model(
            records,
            end_date="2026-07-21",
            config=DataPageConfig(active_tab="月历", selected_date="2026-07-05"),
        )

        self.assertEqual(default_model["selected_date"], "2026-07-21")
        self.assertEqual(default_model["selected_day"]["activity"], "加班")
        self.assertEqual(selected_model["selected_day"]["day_type"], "中碳日")
        self.assertEqual(selected_model["selected_day"]["training"]["body_part_label"], "肩")
        self.assertEqual(selected_model["selected_day"]["diet"]["kcal"], 1900)
        selected_cell = next(item for item in selected_model["calendar"] if item.get("date") == "2026-07-05")
        self.assertTrue(selected_cell["selected"])

    def test_weight_and_bodyfat_are_counted_as_separate_explicit_measurements(self):
        records = {
            "2026-07-19": {
                "profile": {
                    "measurement": {"weight_kg": 72.1, "measured_at": "2026-07-19T07:30:00+08:00"}
                }
            },
            "2026-07-20": {
                "profile": {
                    "measurement": {"bodyfat_percent": 18.2, "measured_at": "2026-07-20T07:30:00+08:00"}
                }
            },
            "2026-07-21": {"profile": {"weight_kg": 72, "bodyfat_percent": 18}},
        }
        model = build_data_page_model(records, end_date="2026-07-21")

        self.assertEqual(model["summary"]["weight_measurements"], 1)
        self.assertEqual(model["summary"]["bodyfat_measurements"], 1)
        carried = next(item for item in model["series"] if item["date"] == "2026-07-21")
        self.assertIsNone(carried["body"])

    def test_circumference_reads_only_explicit_measurements(self):
        records = {
            "2026-07-19": {"profile": {"measurement": {"waist_cm": 82, "measured_at": "2026-07-19T07:30:00+08:00"}}},
            "2026-07-20": {"profile": {"measurement": {"arm_cm": 34.5, "measured_at": "2026-07-20T07:30:00+08:00"}}},
            "2026-07-21": {"profile": {"waist_cm": 81, "arm_cm": 35, "measured_at": "2026-07-21T07:30:00+08:00"}},
        }
        model = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(chart_kind="circumference"))

        self.assertEqual(model["summary"]["circumference_measurements"]["waist_cm"], 2)
        self.assertEqual(model["summary"]["circumference_measurements"]["arm_cm"], 2)
        direct = next(item for item in model["series"] if item["date"] == "2026-07-21")
        self.assertEqual(direct["circumference"]["waist_cm"], 81)
        self.assertEqual(model["trend"]["recorded_count"], 3)

    def test_circumference_ignores_carried_profile_values_without_measured_at(self):
        records = {"2026-07-21": {"profile": {"waist_cm": 81, "arm_cm": 35}}}
        model = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(chart_kind="circumference"))

        point = next(item for item in model["series"] if item["date"] == "2026-07-21")
        self.assertIsNone(point["circumference"]["waist_cm"])
        self.assertEqual(model["trend"]["recorded_count"], 0)

    def test_empty_trend_keeps_values_none_and_exposes_record_entry(self):
        model = build_data_page_model({}, end_date="2026-07-21", config=DataPageConfig(chart_kind="weight"))

        self.assertEqual(model["trend"]["recorded_count"], 0)
        self.assertEqual({point["value"] for point in model["trend"]["points"]}, {None})
        self.assertEqual(model["trend"]["empty_action_label"], "+记录")

    def test_training_trend_uses_only_real_completed_sets_for_weekly_totals_and_best_lifts(self):
        records = {
            "2026-07-20": {
                "training": {"session": session("胸", sets=[
                    completed_set(80, 5),
                    {"weight_kg": 100, "reps": 1, "completed": False},
                    {"weight_kg": 40, "reps": 10, "completed": True, "warmup": True},
                ])}
            },
            "2026-07-21": {
                "training": {"session": session("背", sets=[completed_set(70, 8)])}
            },
        }
        model = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(chart_kind="training"))

        self.assertEqual(sum(item["sets"] for item in model["trend"]["weekly_training"]), 2)
        self.assertEqual(sum(item["volume_kg"] for item in model["trend"]["weekly_training"]), 960)
        self.assertTrue(model["trend"]["exercise_trend_entry"])
        best = model["trend"]["best_lifts"][0]
        self.assertEqual(best["exercise"], "胸训练")
        self.assertEqual(best["weight_kg"], 80)
        self.assertEqual(best["reps"], 5)
        self.assertAlmostEqual(best["epley_1rm_kg"], 93.33)

    def test_training_best_lifts_can_filter_by_body_part(self):
        records = {
            "2026-07-21": {
                "training": {"sessions": [
                    session("胸", sets=[completed_set(80, 5)]),
                    session("背", sets=[completed_set(70, 8)]),
                ]}
            },
        }
        model = build_data_page_model(
            records,
            end_date="2026-07-21",
            config=DataPageConfig(chart_kind="training", body_part_filter="胸"),
        )

        self.assertEqual(len(model["trend"]["best_lifts"]), 1)
        self.assertEqual(model["trend"]["best_lifts"][0]["body_part"], "胸")

    def test_action_trend_lists_real_exercises_and_selected_series(self):
        records = {
            "2026-07-19": {
                "training": {"sessions": [
                    named_session("胸", "卧推", sets=[completed_set(80, 5), {"weight_kg": 120, "reps": 1, "completed": False}]),
                    named_session("背", "划船", sets=[completed_set(60, 10)]),
                ]}
            },
            "2026-07-21": {
                "training": {"session": named_session("胸", "卧推", sets=[completed_set(85, 4), {"weight_kg": 40, "reps": 10, "completed": True, "warmup": True}])}
            },
        }
        model = build_data_page_model(
            records,
            end_date="2026-07-21",
            config=DataPageConfig(chart_kind="training", action_trend_open=True, selected_exercise="卧推"),
        )
        trend = model["trend"]["exercise_trend"]

        self.assertTrue(trend["open"])
        self.assertEqual({item["exercise"] for item in trend["options"]}, {"卧推", "划船"})
        self.assertEqual(trend["selected_exercise"], "卧推")
        self.assertEqual(trend["recorded_count"], 2)
        first = next(item for item in trend["points"] if item["date"] == "2026-07-19")
        latest = next(item for item in trend["points"] if item["date"] == "2026-07-21")
        self.assertEqual(first["weight_kg"], 80)
        self.assertEqual(first["reps"], 5)
        self.assertAlmostEqual(first["epley_1rm_kg"], 93.33)
        self.assertEqual(latest["weight_kg"], 85)
        self.assertEqual(latest["reps"], 4)
        self.assertAlmostEqual(latest["epley_1rm_kg"], 96.33)
        self.assertEqual(trend["best_weight_kg"], 85)
        self.assertEqual(trend["best_reps"], 5)
        self.assertAlmostEqual(trend["best_epley_1rm_kg"], 96.33)

    def test_action_trend_defaults_to_real_option_and_empty_state_does_not_fake_points(self):
        empty = build_data_page_model(
            {},
            end_date="2026-07-21",
            config=DataPageConfig(chart_kind="training", action_trend_open=True),
        )
        self.assertTrue(empty["trend"]["exercise_trend"]["open"])
        self.assertEqual(empty["trend"]["exercise_trend"]["options"], [])
        self.assertEqual({item["epley_1rm_kg"] for item in empty["trend"]["exercise_trend"]["points"]}, set())
        self.assertEqual(empty["trend"]["exercise_trend"]["empty_action_label"], "+记录训练")

        records = {"2026-07-21": {"training": {"session": named_session("背", "划船", sets=[completed_set(70, 8)])}}}
        model = build_data_page_model(
            records,
            end_date="2026-07-21",
            config=DataPageConfig(chart_kind="training", action_trend_open=True),
        )
        self.assertEqual(model["trend"]["exercise_trend"]["selected_exercise"], "划船")

    def test_raw_daily_rows_are_collapsed_until_requested(self):
        collapsed = build_data_page_model({}, end_date="2026-07-21")
        expanded = build_data_page_model(
            {},
            end_date="2026-07-21",
            config=DataPageConfig(raw_expanded=True),
        )

        self.assertFalse(collapsed["config"].raw_expanded)
        self.assertTrue(expanded["config"].raw_expanded)
        self.assertEqual(len(expanded["raw_days"]), 7)


class AnalyticsFletViewTests(unittest.TestCase):
    def test_reusable_view_builds_without_main_py(self):
        view = build_data_page_view({}, end_date="2026-07-21")

        self.assertEqual(view.__class__.__name__, "Column")
        self.assertEqual(len(view.controls), 4)

    def test_calendar_view_accepts_selected_date_callback(self):
        clicked = []
        view = build_data_page_view(
            {},
            end_date="2026-07-21",
            config=DataPageConfig(active_tab="月历", selected_date="2026-07-10"),
            on_selected_date_change=clicked.append,
        )

        self.assertEqual(view.__class__.__name__, "Column")
        self.assertEqual(len(view.controls), 4)

    def test_action_trend_view_builds_inside_component(self):
        records = {"2026-07-21": {"training": {"session": named_session("胸", "卧推", sets=[completed_set(80, 5)])}}}
        view = build_data_page_view(
            records,
            end_date="2026-07-21",
            config=DataPageConfig(chart_kind="training", action_trend_open=True, selected_exercise="卧推"),
            on_action_trend_close=lambda _: None,
            on_selected_exercise_change=lambda _: None,
        )

        self.assertEqual(view.__class__.__name__, "Column")
        self.assertEqual(len(view.controls), 4)

    def test_main_hook_snippet_uses_single_reusable_component(self):
        hook = build_main_data_page_hook()

        self.assertIn("DataPageConfig", hook)
        self.assertIn("build_data_page_view(", hook)
        self.assertIn('"period_days": 7', hook)
        self.assertIn('"chart_kind": "weight"', hook)
        self.assertIn("on_period_change=set_period", hook)
        self.assertIn("on_add_record=", hook)
        self.assertIn("on_action_trend_open=open_action_trend", hook)
        self.assertIn("on_action_trend_close=close_action_trend", hook)
        self.assertIn("on_selected_exercise_change=set_exercise", hook)
        self.assertIn("on_body_part_filter_change=set_body_part", hook)
        self.assertIn('"selected_date": None', hook)
        self.assertIn('"action_trend_open": False', hook)
        self.assertIn('"selected_exercise": None', hook)
        self.assertIn("on_selected_date_change=set_calendar_date", hook)


if __name__ == "__main__":
    unittest.main()
