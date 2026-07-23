"""Top-level analytics page composition."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import flet as ft

from analytics_calendar_views import _render_calendar
from analytics_model import BODY_PART_FILTERS, CHART_OPTIONS, DataPageConfig, PERIOD_OPTIONS, SUB, VIEW_TABS, build_data_page_model
from analytics_summary_views import _render_raw_list, _render_summary
from analytics_trend_views import _render_trend_chart
from analytics_ui import _card, _chip, _text
from analytics_weekly_review_views import _render_weekly_review

def build_data_page_view(
    records: Any,
    *,
    end_date: str | date,
    config: DataPageConfig | None = None,
    on_period_change: Callable[[int], None] | None = None,
    on_tab_change: Callable[[str], None] | None = None,
    on_chart_change: Callable[[str], None] | None = None,
    on_metric_change: Callable[[str], None] | None = None,
    on_trend_point_select: Callable[[str], None] | None = None,
    on_add_record: Callable[[str], None] | None = None,
    on_exercise_trends: Callable[[Any], None] | None = None,
    on_action_trend_open: Callable[[Any], None] | None = None,
    on_action_trend_close: Callable[[Any], None] | None = None,
    on_selected_exercise_change: Callable[[str], None] | None = None,
    on_body_part_filter_change: Callable[[str], None] | None = None,
    on_selected_date_change: Callable[[str], None] | None = None,
    on_calendar_event_change: Callable[[str, str], None] | None = None,
    on_calendar_month_change: Callable[[str], None] | None = None,
    on_toggle_raw: Callable[[Any], None] | None = None,
) -> ft.Column:
    """Return a reusable Flet data page with trend, calendar, summary and raw rows."""

    cfg = config or DataPageConfig()
    model = build_data_page_model(records, end_date=end_date, config=cfg)
    period_row = ft.Row(
        [
            _chip(f"{days}天", cfg.period_days == days, None if on_period_change is None else lambda e, value=days: on_period_change(value))
            for days in PERIOD_OPTIONS
        ],
        spacing=6,
    )
    tab_row = ft.Row(
        [
            _chip(tab, cfg.active_tab == tab, None if on_tab_change is None else lambda e, value=tab: on_tab_change(value))
            for tab in VIEW_TABS
        ],
        spacing=6,
    )
    chart_row = ft.Row(
        [
            _chip(label, cfg.chart_kind == key, None if on_chart_change is None else lambda e, value=key: on_chart_change(value))
            for key, label in CHART_OPTIONS
        ],
        spacing=6,
    )

    body: ft.Control
    if cfg.active_tab == "月历":
        body = _render_calendar(model, on_selected_date_change, on_calendar_event_change, on_calendar_month_change)
    elif cfg.active_tab == "汇总":
        body = _render_summary(model)
    else:
        open_action_trend = on_action_trend_open or on_exercise_trends
        body = _render_trend_chart(
            model,
            on_add_record,
            open_action_trend,
            on_action_trend_close,
            on_selected_exercise_change,
            on_body_part_filter_change,
            on_metric_change,
            on_trend_point_select,
        )

    return ft.Column(
        [
            _render_weekly_review(model),
            _card(ft.Column([ft.Row([_text("数据", size=20, weight="bold"), _text("默认7天，可切30/90", size=12, color=SUB, weight="bold")], alignment="spaceBetween"), period_row, tab_row], spacing=10)),
            chart_row if cfg.active_tab == "趋势" else ft.Container(height=0),
            body,
            _render_raw_list(model, on_toggle_raw),
        ],
        spacing=8,
    )


def build_main_data_page_hook(
    *,
    state_name: str = "data_page_state",
    records_name: str = "records",
    refresh_name: str = "refresh",
    selected_date_name: str = "selected_date",
) -> str:
    """Return the small ``main.py`` hook body needed to mount this component."""

    return f'''from analytics_views import DataPageConfig, build_data_page_view

{state_name} = {{"period_days": 7, "active_tab": "趋势", "chart_kind": "weight", "metric_key": "weight_kg", "selected_trend_date": None, "body_part_filter": "全部", "selected_date": None, "calendar_month": None, "action_trend_open": False, "selected_exercise": None, "raw_expanded": False}}

def render_data_page():
    def set_period(days):
        {state_name}["period_days"] = days
        {state_name}["selected_trend_date"] = None
        {refresh_name}()

    def set_tab(tab):
        {state_name}["active_tab"] = tab
        {refresh_name}()

    def set_chart(kind):
        {state_name}["chart_kind"] = kind
        {state_name}["metric_key"] = None
        {state_name}["selected_trend_date"] = None
        {refresh_name}()

    def set_metric(metric):
        {state_name}["metric_key"] = metric
        {state_name}["selected_trend_date"] = None
        {refresh_name}()

    def set_body_part(part):
        {state_name}["body_part_filter"] = part
        {refresh_name}()

    def open_action_trend(_):
        {state_name}["action_trend_open"] = True
        {refresh_name}()

    def close_action_trend(_):
        {state_name}["action_trend_open"] = False
        {refresh_name}()

    def set_exercise(exercise):
        {state_name}["selected_exercise"] = exercise
        {state_name}["action_trend_open"] = True
        {refresh_name}()

    def set_calendar_date(day):
        {state_name}["selected_date"] = day
        {refresh_name}()

    def set_calendar_month(month):
        {state_name}["calendar_month"] = month
        {state_name}["selected_date"] = f"{{month}}-01"
        {refresh_name}()

    def toggle_raw(_):
        {state_name}["raw_expanded"] = not {state_name}.get("raw_expanded", False)
        {refresh_name}()

    return build_data_page_view(
        {records_name},
        end_date={selected_date_name},
        config=DataPageConfig(**{state_name}),
        on_period_change=set_period,
        on_tab_change=set_tab,
        on_chart_change=set_chart,
        on_metric_change=set_metric,
        on_trend_point_select=lambda day: ({state_name}.update({{"selected_trend_date": day}}), {refresh_name}()),
        on_add_record=lambda kind: set_view("recovery" if kind in {{"weight", "bodyfat", "circumference"}} else "training" if kind == "training" else "diet"),
        on_action_trend_open=open_action_trend,
        on_action_trend_close=close_action_trend,
        on_selected_exercise_change=set_exercise,
        on_body_part_filter_change=set_body_part,
        on_selected_date_change=set_calendar_date,
        on_calendar_month_change=set_calendar_month,
        on_toggle_raw=toggle_raw,
    )'''


__all__ = [
    "CHART_OPTIONS",
    "BODY_PART_FILTERS",
    "PERIOD_OPTIONS",
    "VIEW_TABS",
    "DataPageConfig",
    "build_data_page_model",
    "build_data_page_view",
    "build_main_data_page_hook",
]
