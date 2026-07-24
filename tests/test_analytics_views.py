import sys
import unittest
import asyncio
from pathlib import Path

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analytics_views import (  # noqa: E402
    CHART_OPTIONS,
    DataPageConfig,
    build_data_page_model,
    build_data_page_view,
    build_main_data_page_hook,
)
from analytics_calendar_views import (  # noqa: E402
    _CARBON_COLORS,
    CALENDAR_KCAL_COLORS,
    CALENDAR_CELL_HEIGHT,
    _calendar_activity_label,
    _calendar_activity_lines,
    _calendar_kcal_control,
    _calendar_kcal_label,
)
from analytics_model import (  # noqa: E402
    CALENDAR_KCAL_BAND_BELOW,
    CALENDAR_KCAL_BAND_HIGH,
    CALENDAR_KCAL_BAND_MISSING,
    CALENDAR_KCAL_BAND_OVER,
    CALENDAR_KCAL_BAND_TARGET,
    CALENDAR_KCAL_RATIO_THRESHOLDS,
)
from analytics_trend_views import (  # noqa: E402
    _InitiallyLatestRow,
    _render_readable_chart,
    _smooth_path_elements,
    _trend_statistics,
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

    def test_period_controls_share_today_anchored_series_axis_and_selection_window(self):
        records = {
            day: {"profile": {"measurement": {"weight_kg": value, "measured_at": f"{day}T08:00:00"}}}
            for day, value in (("2026-07-16", 71), ("2026-07-17", 70), ("2026-07-23", 69))
        }
        expected_starts = {7: "2026-07-17", 30: "2026-06-24", 90: "2026-04-25"}

        for days, expected_start in expected_starts.items():
            model = build_data_page_model(
                records,
                end_date="2026-07-23",
                config=DataPageConfig(period_days=days, selected_trend_date="2026-07-16"),
            )
            series_dates = [item["date"] for item in model["series"]]
            trend_dates = [item["date"] for item in model["trend"]["points"]]
            tick_dates = [trend_dates[index] for index in model["trend"]["date_tick_indices"]]

            self.assertEqual(series_dates, trend_dates)
            self.assertEqual((series_dates[0], series_dates[-1]), (expected_start, "2026-07-23"))
            self.assertEqual((tick_dates[0], tick_dates[-1]), (expected_start, "2026-07-23"))
            self.assertEqual(
                model["trend"]["selected_trend_date"],
                None if days == 7 else "2026-07-16",
            )

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

    def test_period_summary_exposes_recovery_and_body_change_metrics(self):
        records = {
            "2026-07-20": {
                "profile": {"measurement": {"weight_kg": 75, "bodyfat_percent": 18, "measured_at": "2026-07-20T08:00:00"}},
                "daily_total": {"kcal": 2000},
                "meals": {"早餐": [{"name": "燕麦"}]},
                "sleep": {"total_minutes": 450},
                "water": {"records_ml": [2500]},
                "training": {"session": session("胸")},
            },
            "2026-07-21": {
                "profile": {"measurement": {"weight_kg": 74.5, "bodyfat_percent": 17.5, "measured_at": "2026-07-21T08:00:00"}},
                "daily_total": {"kcal": 1800},
                "meals": {"早餐": [{"name": "鸡蛋"}]},
                "sleep": {"total_minutes": 480},
                "water": {"records_ml": [3000]},
                "calendar_event": {"type": "rest"},
            },
        }
        summary = build_data_page_model(records, end_date="2026-07-21")["summary"]

        self.assertEqual(summary["training_days"], 1)
        self.assertEqual(summary["rest_days"], 1)
        self.assertEqual(summary["weight_change"], -0.5)
        self.assertEqual(summary["bodyfat_change"], -0.5)
        self.assertEqual(summary["avg_sleep_hours"], 7.75)
        self.assertEqual(summary["avg_kcal"], 1900)
        self.assertEqual(summary["avg_water_ml"], 2750)

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

        self.assertEqual(days["2026-07-05"]["compact_labels"], ["高", "胸", "出差"])
        self.assertEqual(days["2026-07-06"]["compact_labels"], ["低", "休息"])
        self.assertEqual(days["2026-07-07"]["compact_labels"], [])

    def test_calendar_cells_include_kcal_note_and_keep_full_selected_detail(self):
        records = {
            "2026-07-05": {
                "profile": {"day_type": "高碳日"},
                "calendar_event": {"type": "custom", "text": "晚上加班后拉伸二十分钟"},
                "training": {"session": session("胸")},
                "daily_total": {"kcal": 1141.5, "carb": 120, "protein": 130, "fat": 42},
                "meals": {"早餐": [{"name": "燕麦"}]},
            }
        }
        model = build_data_page_model(
            records,
            end_date="2026-07-21",
            config=DataPageConfig(active_tab="月历", selected_date="2026-07-05"),
        )
        day = next(item for item in model["calendar"] if item.get("date") == "2026-07-05")

        self.assertEqual(day["compact_labels"], ["高", "胸", "1141.5", "晚上加班后拉伸二十分钟"])
        self.assertEqual(model["selected_day"]["event_text"], "晚上加班后拉伸二十分钟")
        self.assertEqual(model["selected_day"]["training"]["body_part_label"], "胸")
        self.assertEqual(model["selected_day"]["diet"]["kcal"], 1141.5)

    def test_calendar_cell_view_is_compact_and_prioritizes_readable_core_fields(self):
        records = {
            "2026-07-05": {
                "profile": {"day_type": "高碳日"},
                "calendar_event": {"type": "custom", "text": "这段长备注只在详情中完整显示"},
                "training": {"session": session("胸")},
                "daily_total": {"kcal": 1141.5},
                "meals": {"早餐": [{"name": "燕麦"}]},
            },
            "2026-07-06": {"profile": {"day_type": "低碳日"}, "calendar_event": {"type": "rest"}},
        }
        model = build_data_page_model(records, end_date="2026-07-23", config=DataPageConfig(active_tab="月历"))
        days = {item["date"]: item for item in model["calendar"] if item.get("date")}

        self.assertEqual(CALENDAR_CELL_HEIGHT, 92)
        self.assertEqual(days["2026-07-05"]["compact_day_type"], "高")
        self.assertEqual(_calendar_activity_label(days["2026-07-05"]), "胸")
        self.assertEqual(_calendar_kcal_label(days["2026-07-05"]["kcal"]), "1142")
        self.assertEqual(_calendar_activity_label(days["2026-07-06"]), "休息")
        self.assertEqual(_calendar_activity_label(days["2026-07-07"]), "")

    def test_calendar_training_parts_use_three_lines_and_summarize_overflow(self):
        item = {
            "activity_type": "training",
            "body_parts": ["胸", "三头", "腹部", "肩", "前臂"],
        }

        self.assertEqual(_calendar_activity_lines(item), ["胸", "三头", "腹部 +2"])
        self.assertEqual(_calendar_activity_label(item), "胸\n三头\n腹部 +2")

    def test_calendar_carbon_day_colors_are_distinct_and_semantic(self):
        self.assertEqual(_CARBON_COLORS["低"], "#116E59")
        self.assertEqual(_CARBON_COLORS["中"], "#C58A00")
        self.assertEqual(_CARBON_COLORS["高"], "#C33B3B")

    def test_calendar_calorie_bands_follow_final_boundary_rules(self):
        target = 2000
        samples = {
            "2026-07-01": (1599, target, CALENDAR_KCAL_BAND_BELOW, 0.7995),
            "2026-07-02": (1600, target, CALENDAR_KCAL_BAND_TARGET, 0.8),
            "2026-07-03": (2000, target, CALENDAR_KCAL_BAND_TARGET, 1.0),
            "2026-07-04": (2001, target, CALENDAR_KCAL_BAND_OVER, 1.0005),
            "2026-07-05": (2400, target, CALENDAR_KCAL_BAND_OVER, 1.2),
            "2026-07-06": (2401, target, CALENDAR_KCAL_BAND_HIGH, 1.2005),
            "2026-07-07": (2600, None, CALENDAR_KCAL_BAND_MISSING, None),
        }
        records = {
            day: {
                "profile": {"targets": {"calorie_target": calorie_target}},
                "daily_total": {"kcal": kcal},
                "meals": {"晚餐": [{"name": "测试餐"}]},
            }
            for day, (kcal, calorie_target, _, _) in samples.items()
        }
        model = build_data_page_model(records, end_date="2026-07-23")
        days = {item["date"]: item for item in model["calendar"] if item.get("date")}

        self.assertEqual(CALENDAR_KCAL_RATIO_THRESHOLDS, (0.8, 1.0, 1.2))
        for day, (_, _, expected_band, expected_ratio) in samples.items():
            self.assertEqual(days[day]["kcal_band"], expected_band)
            self.assertEqual(days[day]["kcal_ratio"], expected_ratio)

    def test_calendar_calorie_is_pure_number_bottom_right_with_semantic_color(self):
        expected_colors = {
            CALENDAR_KCAL_BAND_MISSING: "#4F5D58",
            CALENDAR_KCAL_BAND_BELOW: "#4F5D58",
            CALENDAR_KCAL_BAND_TARGET: "#116E59",
            CALENDAR_KCAL_BAND_OVER: "#B78600",
            CALENDAR_KCAL_BAND_HIGH: "#D64545",
        }
        self.assertEqual(CALENDAR_KCAL_COLORS, expected_colors)
        for band, color in expected_colors.items():
            control = _calendar_kcal_control({"kcal": 1981.4, "kcal_band": band})
            self.assertEqual(control.data, "calendar-kcal-bottom-right")
            self.assertEqual(control.alignment, ft.Alignment.BOTTOM_RIGHT)
            self.assertEqual(control.content.value, "1981")
            self.assertNotIn("卡", control.content.value)
            self.assertNotIn("kcal", control.content.value.lower())
            self.assertEqual(control.content.color, color)

        empty = _calendar_kcal_control({"kcal": None, "kcal_band": CALENDAR_KCAL_BAND_MISSING})
        self.assertEqual(empty.content.value, "")

    def test_calendar_custom_event_keeps_a_readable_compact_label(self):
        records = {
            "2026-07-05": {"calendar_event": {"type": "custom", "text": "公司出差开会"}},
        }
        model = build_data_page_model(
            records,
            end_date="2026-07-23",
            config=DataPageConfig(active_tab="月历"),
        )
        day = next(item for item in model["calendar"] if item.get("date") == "2026-07-05")

        self.assertEqual(_calendar_activity_label(day), "公司出")
        self.assertEqual(day["record_state"], "recorded")

    def test_calendar_month_navigation_model_handles_leap_year_and_selection(self):
        model = build_data_page_model(
            {},
            end_date="2026-07-21",
            config=DataPageConfig(active_tab="月历", calendar_month="2024-02", selected_date="2026-07-21"),
        )
        days = [item for item in model["calendar"] if item.get("in_month")]

        self.assertEqual(model["calendar_month"], "2024-02")
        self.assertEqual(len(days), 29)
        self.assertEqual(model["selected_date"], "2024-02-01")
        self.assertTrue(days[0]["selected"])

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
        self.assertEqual(model["trend"]["metric_key"], "waist_cm")
        self.assertEqual(model["trend"]["recorded_count"], 2)

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
        self.assertEqual(model["trend"]["empty_action_label"], "记录体重")

    def test_weight_line_has_units_ticks_dates_and_real_point_changes(self):
        records = {
            "2026-07-15": {"profile": {"measurement": {"weight_kg": 70, "measured_at": "2026-07-15T08:00:00"}}},
            "2026-07-17": {"profile": {"measurement": {"weight_kg": 69.5, "measured_at": "2026-07-17T08:00:00"}}},
        }
        trend = build_data_page_model(records, end_date="2026-07-21")["trend"]
        self.assertEqual(trend["title"], "体重")
        self.assertEqual(trend["unit"], "kg")
        self.assertEqual(trend["chart_type"], "line")
        self.assertGreaterEqual(len(trend["axis"]["ticks"]), 3)
        self.assertEqual(trend["date_tick_indices"], list(range(7)))
        self.assertIsNone(trend["points"][1]["value"])
        latest = next(item for item in trend["points"] if item["date"] == "2026-07-17")
        self.assertEqual(latest["change_from_previous"], -0.5)
        self.assertEqual(latest["previous_date"], "2026-07-15")
        self.assertEqual(trend["change"], -0.5)
        self.assertEqual(trend["change_from_earliest"], -0.5)

    def test_multi_point_chart_uses_smooth_area_and_only_labels_extremes(self):
        values = [75, 74.8, 74.9, 75, 74.8, 74.6, 74.7]
        records = {
            f"2026-07-{day:02d}": {
                "profile": {"measurement": {"weight_kg": value, "measured_at": f"2026-07-{day:02d}T08:00:00"}}
            }
            for day, value in zip(range(17, 24), values)
        }
        trend = build_data_page_model(records, end_date="2026-07-23")["trend"]
        chart = _render_readable_chart(trend, None)
        plot = chart.content.controls[1].controls[0]
        canvas = plot.controls[0]
        labels = [item for item in plot.controls if getattr(item, "data", None) == "trend-extreme-label"]
        shape_data = {getattr(shape, "data", None) for shape in canvas.shapes}

        self.assertEqual(plot.data["mode"], "smooth-area")
        self.assertIn("trend-area", shape_data)
        self.assertIn("trend-smooth-line", shape_data)
        smooth_line = next(shape for shape in canvas.shapes if getattr(shape, "data", None) == "trend-smooth-line")
        self.assertEqual(smooth_line.paint.style, ft.PaintingStyle.STROKE)
        self.assertEqual({label.content.value for label in labels}, {"75 kg", "74.6 kg"})
        self.assertEqual(len(labels), 2)
        self.assertTrue(all(label.bgcolor is None for label in labels))
        maximum_label = next(label for label in labels if label.content.value == "75 kg")
        minimum_label = next(label for label in labels if label.content.value == "74.6 kg")
        axis = trend["axis"]
        plot_height = 226 - 24 - 38
        y_at = lambda value: 24 + (axis["max"] - value) / (axis["max"] - axis["min"]) * plot_height
        self.assertLess(maximum_label.top + maximum_label.height, y_at(75))
        self.assertGreater(minimum_label.top, y_at(74.6))

    def test_smooth_path_uses_cubic_segments_through_every_point(self):
        elements = _smooth_path_elements([(10, 30), (40, 20), (70, 50)])

        self.assertEqual([item.__class__.__name__ for item in elements], ["MoveTo", "CubicTo", "CubicTo"])
        self.assertEqual((elements[-1].x, elements[-1].y), (70, 50))

    def test_selected_point_has_vertical_indicator_and_date_value_bubble(self):
        records = {
            day: {"profile": {"measurement": {"weight_kg": value, "measured_at": f"{day}T08:00:00"}}}
            for day, value in (("2026-07-17", 75), ("2026-07-20", 74.8), ("2026-07-23", 74.7))
        }
        trend = build_data_page_model(
            records,
            end_date="2026-07-23",
            config=DataPageConfig(selected_trend_date="2026-07-20"),
        )["trend"]
        selected = []
        chart = _render_readable_chart(trend, selected.append)
        plot = chart.content.controls[1].controls[0]
        canvas = plot.controls[0]
        bubbles = [item for item in plot.controls if getattr(item, "data", None) == "trend-selection-bubble"]
        hit_target = next(item for item in plot.controls if str(getattr(item, "tooltip", "")).startswith("2026-07-23"))

        self.assertTrue(any(getattr(shape, "data", None) == "trend-selection-line" for shape in canvas.shapes))
        self.assertEqual(len(bubbles), 1)
        self.assertEqual([item.value for item in bubbles[0].content.controls], ["2026-07-20", "74.8 kg"])
        extreme_labels = [item for item in plot.controls if getattr(item, "data", None) == "trend-extreme-label"]
        self.assertEqual(len(extreme_labels), 2)
        self.assertIs(plot.controls[-1], bubbles[0])
        hit_target.on_click(None)
        self.assertEqual(selected, ["2026-07-23"])

    def test_chart_ignores_target_values_and_renders_no_target_line_or_label(self):
        records = {
            "2026-07-22": {"profile": {"targets": {"calorie_target": 2000}}, "daily_total": {"kcal": 1800}, "meals": {"晚餐": [{"name": "米饭"}]}},
            "2026-07-23": {"profile": {"targets": {"calorie_target": 2000}}, "daily_total": {"kcal": 1900}, "meals": {"晚餐": [{"name": "米饭"}]}},
        }
        trend = build_data_page_model(
            records,
            end_date="2026-07-23",
            config=DataPageConfig(chart_kind="diet"),
        )["trend"]
        chart = _render_readable_chart(trend, None)
        plot = chart.content.controls[1].controls[0]
        canvas = plot.controls[0]

        self.assertTrue(any(point.get("target_min") == 2000 for point in trend["points"]))
        self.assertFalse(any("target" in str(getattr(shape, "data", "")) for shape in canvas.shapes))
        self.assertFalse(any("目标" in str(getattr(control, "value", "")) for control in plot.controls))

    def test_trend_statistics_show_count_interval_high_and_low(self):
        recorded = [
            (0, {"date": "2026-07-17"}, 75.0),
            (1, {"date": "2026-07-22"}, 74.6),
            (2, {"date": "2026-07-23"}, 74.7),
        ]
        statistics = _trend_statistics(recorded, "kg")
        cells = statistics.content.controls[0].controls + statistics.content.controls[2].controls

        self.assertEqual(statistics.data, "trend-statistics")
        self.assertEqual([cell.content.controls[0].value for cell in cells], ["记录次数", "区间变化", "最高", "最低"])
        self.assertEqual([cell.content.controls[1].value for cell in cells], ["3 次", "-0.3 kg", "75 kg", "74.6 kg"])

    def test_trend_summary_exposes_previous_and_earliest_comparisons(self):
        records = {
            "2026-07-17": {"profile": {"measurement": {"weight_kg": 75, "measured_at": "2026-07-17T08:00:00"}}},
            "2026-07-22": {"profile": {"measurement": {"weight_kg": 74.6, "measured_at": "2026-07-22T08:00:00"}}},
            "2026-07-23": {"profile": {"measurement": {"weight_kg": 74.7, "measured_at": "2026-07-23T08:00:00"}}},
        }
        model = build_data_page_model(records, end_date="2026-07-23")
        view = build_data_page_view(records, end_date="2026-07-23")
        texts = AnalyticsFletViewTests._text_values(view)

        self.assertEqual(model["trend"]["change"], 0.1)
        self.assertEqual(model["trend"]["change_from_earliest"], -0.3)
        self.assertIn("较上次 +0.1 kg", texts)
        self.assertIn("较最早 -0.3 kg", texts)

    def test_constant_single_and_empty_series_have_readable_axis(self):
        one = {"2026-07-21": {"profile": {"measurement": {"weight_kg": 70, "measured_at": "2026-07-21T08:00:00"}}}}
        axis = build_data_page_model(one, end_date="2026-07-21")["trend"]["axis"]
        self.assertLess(axis["min"], 70)
        self.assertGreater(axis["max"], 70)
        self.assertGreaterEqual(len(axis["ticks"]), 3)

    def test_varying_series_keeps_one_extra_tick_below_only(self):
        records = {
            "2026-07-22": {"profile": {"measurement": {"weight_kg": 74.6, "measured_at": "2026-07-22T08:00:00"}}},
            "2026-07-23": {"profile": {"measurement": {"weight_kg": 75.0, "measured_at": "2026-07-23T08:00:00"}}},
        }
        axis = build_data_page_model(records, end_date="2026-07-23")["trend"]["axis"]

        self.assertAlmostEqual(axis["min"], 74.2)
        self.assertAlmostEqual(axis["max"], 75.2)
        self.assertEqual(axis["ticks"][0], axis["min"])
        self.assertEqual(axis["ticks"][-1], axis["max"])

    def test_single_point_chart_draws_value_label_and_keeps_edge_ticks_in_bounds(self):
        records = {
            "2026-07-23": {
                "profile": {"measurement": {"weight_kg": 70, "measured_at": "2026-07-23T08:00:00"}}
            }
        }
        trend = build_data_page_model(
            records,
            end_date="2026-07-23",
            config=DataPageConfig(period_days=90),
        )["trend"]
        chart = _render_readable_chart(trend, None)
        axis, plot = chart.content.controls
        point_labels = [item for item in plot.controls if getattr(item, "data", None) == "single-trend-point-label"]
        date_labels = [item for item in plot.controls if getattr(item, "value", "") == "7/23"]
        canvas = plot.controls[0]

        self.assertEqual(len(point_labels), 1)
        self.assertEqual(point_labels[0].content.value, "70 kg")
        self.assertIsNone(point_labels[0].bgcolor)
        self.assertTrue(any(shape.__class__.__name__ == "Circle" for shape in canvas.shapes))
        self.assertEqual({item.value for item in date_labels}, {"7/23"})
        self.assertEqual(plot.data["mode"], "single")
        self.assertAlmostEqual(plot.data["date_x"]["2026-07-23"], plot.width / 2)
        self.assertEqual(axis.data, "trend-y-axis")
        self.assertGreaterEqual(len(axis.controls), 3)
        self.assertLessEqual(axis.width, 34)
        self.assertFalse(chart.data["scrollable"])
        self.assertEqual(chart.data["period_days"], 90)

    def test_period_metadata_is_strictly_anchored_to_today(self):
        expected = {
            7: ("2026-07-17", "2026-07-23"),
            30: ("2026-06-24", "2026-07-23"),
            90: ("2026-04-25", "2026-07-23"),
        }
        for days, window in expected.items():
            trend = build_data_page_model(
                {},
                end_date="2026-07-23",
                config=DataPageConfig(period_days=days),
            )["trend"]
            self.assertEqual((trend["window_start"], trend["window_end"]), window)
            self.assertEqual(trend["period_days"], days)

    def test_long_period_chart_scrolls_inside_and_keeps_real_date_spacing(self):
        _InitiallyLatestRow._initial_scroll_keys.clear()
        for days, window_start, minimum_width in (
            (30, "2026-06-24", 1000),
            (90, "2026-04-25", 3500),
        ):
            records = {
                window_start: {"profile": {"measurement": {"weight_kg": 71, "measured_at": f"{window_start}T08:00:00"}}},
                "2026-07-23": {"profile": {"measurement": {"weight_kg": 69, "measured_at": "2026-07-23T08:00:00"}}},
            }
            trend = build_data_page_model(
                records,
                end_date="2026-07-23",
                config=DataPageConfig(period_days=days),
            )["trend"]
            chart = _render_readable_chart(trend, None)
            axis, scroller = chart.content.controls
            plot = scroller.controls[0]

            self.assertTrue(chart.data["scrollable"])
            self.assertFalse(scroller.auto_scroll)
            self.assertEqual(scroller.__class__.__name__, "_InitiallyLatestRow")
            self.assertEqual(scroller.data, "trend-horizontal-scroll")
            self.assertLessEqual(axis.width, 34)
            self.assertGreater(plot.width, minimum_width)
            self.assertGreater(plot.data["date_x"]["2026-07-23"], plot.data["date_x"][window_start])
            value_labels = [item for item in plot.controls if getattr(item, "data", None) == "trend-extreme-label"]
            self.assertEqual({item.content.value for item in value_labels}, {"71 kg", "69 kg"})
            self.assertTrue(all(0 <= item.left <= plot.width - item.width for item in value_labels))

            scroll_calls = []

            async def capture_scroll(**kwargs):
                scroll_calls.append(kwargs)

            scroller.scroll_to = capture_scroll
            asyncio.run(scroller._show_latest_once())
            self.assertEqual(scroll_calls, [{"offset": -1, "duration": 0}])

    def test_long_period_chart_only_auto_scrolls_on_its_first_mount(self):
        _InitiallyLatestRow._initial_scroll_keys.clear()
        key = "weight:90:2026-04-25:2026-07-23"
        self.assertTrue(_InitiallyLatestRow.should_auto_scroll(key))
        self.assertFalse(_InitiallyLatestRow.should_auto_scroll(key))
        self.assertTrue(_InitiallyLatestRow.should_auto_scroll("bodyfat:90:2026-04-25:2026-07-23"))

    def test_selected_long_period_point_gets_an_explicit_scroll_target(self):
        records = {
            "2026-04-25": {"profile": {"measurement": {"weight_kg": 75, "measured_at": "2026-04-25T08:00:00"}}},
            "2026-05-10": {"profile": {"measurement": {"weight_kg": 74, "measured_at": "2026-05-10T08:00:00"}}},
            "2026-07-23": {"profile": {"measurement": {"weight_kg": 73, "measured_at": "2026-07-23T08:00:00"}}},
        }
        trend = build_data_page_model(
            records,
            end_date="2026-07-23",
            config=DataPageConfig(period_days=90, selected_trend_date="2026-05-10"),
        )["trend"]
        chart = _render_readable_chart(trend, None)
        scroller = chart.content.controls[1]
        selected_x = scroller.controls[0].data["date_x"]["2026-05-10"]

        self.assertEqual(scroller._selected_scroll_target, selected_x)
        scroll_calls = []

        async def capture_scroll(**kwargs):
            scroll_calls.append(kwargs)

        scroller.scroll_to = capture_scroll
        asyncio.run(scroller._show_selected_target())
        self.assertEqual(scroll_calls, [{"offset": max(0.0, selected_x - 120.0), "duration": 0}])

    def test_seven_day_chart_is_complete_without_horizontal_scroll(self):
        records = {
            day: {"profile": {"measurement": {"weight_kg": value, "measured_at": f"{day}T08:00:00"}}}
            for day, value in (("2026-07-17", 71), ("2026-07-20", 70), ("2026-07-23", 69))
        }
        trend = build_data_page_model(records, end_date="2026-07-23")["trend"]
        chart = _render_readable_chart(trend, None)
        axis, scroller = chart.content.controls
        plot = scroller.controls[0]

        self.assertFalse(chart.data["scrollable"])
        self.assertIsNone(scroller.scroll)
        self.assertEqual(set(plot.data["date_x"]), {item["date"] for item in trend["points"]})
        self.assertLessEqual(axis.width, 34)

    def test_period_date_ticks_are_sparse_for_30_and_90_days(self):
        for days in (30, 90):
            trend = build_data_page_model({}, end_date="2026-07-21", config=DataPageConfig(period_days=days))["trend"]
            self.assertGreaterEqual(len(trend["date_tick_indices"]), 5)
            self.assertLessEqual(len(trend["date_tick_indices"]), 7)

    def test_actionable_domain_metrics_and_targets_are_not_mixed(self):
        record = {
            "profile": {"targets": {"calorie_target": 2000, "carb_min": 150, "carb_max": 190}},
            "daily_total": {"kcal": 1800, "carb": 160},
            "meals": {"早餐": [{"name": "燕麦"}]},
            "training": {"session": session("胸", sets=[completed_set(80, 5)])},
            "sleep": {"total_minutes": 450, "bed_time": "23:30"},
            "water": {"records_ml": [500, 500], "target_ml": 2000},
        }
        records = {"2026-07-21": record}
        diet = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(chart_kind="diet"))["trend"]
        self.assertEqual([item["key"] for item in diet["metric_options"]], ["kcal", "carb", "protein", "fat"])
        self.assertEqual(diet["points"][-1]["target_min"], 2000)
        training = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(chart_kind="training"))["trend"]
        self.assertEqual(
            [item["key"] for item in training["metric_options"]],
            ["volume_kg", "formal_sets", "duration_min", "cardio_duration_min", "distance_km"],
        )
        recovery = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(chart_kind="recovery", metric_key="water_ml"))["trend"]
        self.assertEqual([item["key"] for item in recovery["metric_options"]], ["sleep_hours", "water_ml"])
        self.assertEqual(recovery["points"][-1]["target_min"], 2000)

    def test_circumference_supports_new_types_and_one_project_per_chart(self):
        records = {"2026-07-21": {"profile": {"circumference": {"calf_cm": 36.5, "measured_at": "2026-07-21T08:00:00"}}}}
        trend = build_data_page_model(records, end_date="2026-07-21", config=DataPageConfig(chart_kind="circumference", metric_key="calf_cm"))["trend"]
        self.assertEqual(trend["title"], "小腿围")
        self.assertEqual(trend["unit"], "cm")
        self.assertEqual(trend["points"][-1]["value"], 36.5)
        self.assertEqual(trend["empty_action_label"], "记录围度")

    def test_weekly_review_uses_only_partial_real_records(self):
        records = {
            "2026-07-15": {"profile": {"measurement": {"weight_kg": 70, "measured_at": "2026-07-15T08:00:00"}}},
            "2026-07-21": {
                "profile": {"measurement": {"weight_kg": 69, "measured_at": "2026-07-21T08:00:00"}, "targets": {"calorie_target": 2000}},
                "daily_total": {"kcal": 1800}, "meals": {"晚餐": [{"name": "米饭"}]},
                "sleep": {"total_minutes": 420, "bed_time": "23:30"},
                "training": {"session": session("胸")},
            },
        }
        review = build_data_page_model(records, end_date="2026-07-21")["weekly_review"]
        self.assertEqual(review["weight"]["value"], -1)
        self.assertEqual(review["diet"]["recorded_days"], 1)
        self.assertEqual(review["diet"]["completion_percent"], 90)
        self.assertEqual(review["sleep"]["recorded_days"], 1)
        self.assertIsNone(review["training"]["change_percent"])

    def test_weekly_review_empty_does_not_invent_zeroes(self):
        review = build_data_page_model({}, end_date="2026-07-21")["weekly_review"]
        self.assertEqual(review["weight"]["label"], "暂无足够数据")
        self.assertEqual(review["diet"]["label"], "暂无足够数据")
        self.assertEqual(review["sleep"]["label"], "暂无足够数据")

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

    def test_cardio_and_timed_work_are_separate_from_strength_sets_volume_and_pr(self):
        records = {
            "2026-07-22": {
                "training": {"session": {
                    "id": "mixed",
                    "status": "completed",
                    "total_duration_min": 40,
                    "exercises": [
                        {
                            "name": "杠铃卧推", "body_part": "胸", "recording_mode": "strength",
                            "sets": [completed_set(50, 10)],
                        },
                        {
                            "name": "跑步机爬坡", "body_part": "有氧", "recording_mode": "cardio",
                            "completed": True, "duration_seconds": 1800, "distance_km": 3.2,
                            "sets": [completed_set(999, 999)],
                        },
                        {
                            "name": "平板支撑", "body_part": "腹", "recording_mode": "timed",
                            "completed": True, "duration_seconds": 60,
                            "sets": [completed_set(500, 500)],
                        },
                    ],
                }},
            },
        }
        model = build_data_page_model(
            records,
            end_date="2026-07-22",
            config=DataPageConfig(chart_kind="training"),
        )
        training = next(item["training"] for item in model["series"] if item["date"] == "2026-07-22")

        self.assertEqual(training["formal_sets"], 1)
        self.assertEqual(training["volume_kg"], 500)
        self.assertEqual(training["duration_min"], 40)
        self.assertEqual(training["cardio_duration_min"], 30)
        self.assertEqual(training["timed_duration_min"], 1)
        self.assertEqual(training["distance_km"], 3.2)
        self.assertEqual([item["exercise"] for item in model["trend"]["best_lifts"]], ["杠铃卧推"])

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
    @staticmethod
    def _text_values(control):
        values = []
        value = getattr(control, "value", None)
        if isinstance(value, str):
            values.append(value)
        content = getattr(control, "content", None)
        if content is not None:
            values.extend(AnalyticsFletViewTests._text_values(content))
        for child in getattr(control, "controls", []) or []:
            values.extend(AnalyticsFletViewTests._text_values(child))
        return values

    def test_reusable_view_builds_without_main_py(self):
        view = build_data_page_view({}, end_date="2026-07-21")

        self.assertEqual(view.__class__.__name__, "Column")
        self.assertEqual(len(view.controls), 5)

    def test_circumference_page_omits_per_metric_record_count_cards(self):
        records = {
            "2026-07-21": {
                "profile": {
                    "circumference": {
                        "waist_cm": 81,
                        "arm_cm": 35,
                        "chest_cm": 102,
                        "measured_at": "2026-07-21T08:00:00",
                    }
                }
            }
        }
        view = build_data_page_view(
            records,
            end_date="2026-07-23",
            config=DataPageConfig(chart_kind="circumference"),
        )
        texts = self._text_values(view)
        source = Path(__file__).parents[1].joinpath("src", "analytics_trend_views.py").read_text(encoding="utf-8")

        self.assertNotIn("_render_circumference_summary", source)
        for metric_label in ("上臂围", "胸围", "臀围", "大腿围", "小腿围"):
            self.assertEqual(texts.count(metric_label), 1)
        self.assertIn("原始逐日列表", texts)

    def test_weekly_review_precedes_all_data_page_switches(self):
        view = build_data_page_view({}, end_date="2026-07-23")
        first_texts = self._text_values(view.controls[0])
        switch_texts = self._text_values(view.controls[1])

        self.assertIn("本周总结", first_texts)
        self.assertNotIn("7天", first_texts)
        self.assertNotIn("趋势", first_texts)
        self.assertIn("7天", switch_texts)
        self.assertIn("30天", switch_texts)
        self.assertIn("90天", switch_texts)
        self.assertIn("趋势", switch_texts)
        self.assertIn("月历", switch_texts)
        self.assertIn("汇总", switch_texts)

    def test_period_buttons_invoke_the_real_requested_window(self):
        selected = []
        view = build_data_page_view(
            {},
            end_date="2026-07-23",
            on_period_change=selected.append,
        )
        period_row = view.controls[1].content.controls[1]

        period_row.controls[1].on_click(None)
        period_row.controls[2].on_click(None)

        self.assertEqual(selected, [30, 90])

    def test_calendar_view_accepts_selected_date_callback(self):
        clicked = []
        view = build_data_page_view(
            {},
            end_date="2026-07-21",
            config=DataPageConfig(active_tab="月历", selected_date="2026-07-10"),
            on_selected_date_change=clicked.append,
        )

        self.assertEqual(view.__class__.__name__, "Column")
        self.assertEqual(len(view.controls), 5)

    def test_calendar_previous_month_button_invokes_month_callback(self):
        selected = []
        view = build_data_page_view(
            {},
            end_date="2026-07-23",
            config=DataPageConfig(active_tab="月历", calendar_month="2026-07"),
            on_calendar_month_change=selected.append,
        )
        calendar_card = view.controls[3]
        month_row = calendar_card.content.controls[1]

        month_row.controls[0].on_click(None)

        self.assertEqual(selected, ["2026-06"])

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
        self.assertEqual(len(view.controls), 5)

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
        self.assertIn('"calendar_month": None', hook)
        self.assertIn('"action_trend_open": False', hook)
        self.assertIn('"selected_exercise": None', hook)
        self.assertIn("on_selected_date_change=set_calendar_date", hook)
        self.assertIn("on_calendar_month_change=set_calendar_month", hook)

    def test_month_picker_uses_overlay_for_flet_compatibility(self):
        source = Path(__file__).parents[1].joinpath("src", "analytics_calendar_views.py").read_text(encoding="utf-8")
        self.assertIn("page.overlay.append(dialog)", source)
        self.assertIn("dialog.open = True", source)
        self.assertNotIn("page.open(dialog)", source)
        self.assertNotIn("height=106", source)
        self.assertNotIn("TextOverflow.ELLIPSIS", source)


if __name__ == "__main__":
    unittest.main()
