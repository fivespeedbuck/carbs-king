"""Top-level analytics page composition."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

import flet as ft

from analytics_calendar_views import _render_calendar
from analytics_model import BODY_PART_FILTERS, CHART_OPTIONS, DataPageConfig, PERIOD_OPTIONS, VIEW_TABS, build_data_page_model
from ui_components import SUB
from analytics_summary_views import _render_raw_list, _render_summary
from analytics_trend_views import _render_trend_chart
from analytics_ui import _card, _chip, _set_chip_selected, _text
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
    on_selected_exercise_change: Callable[[str], Any] | None = None,
    on_body_part_filter_change: Callable[[str], None] | None = None,
    on_selected_date_change: Callable[[str], None] | None = None,
    on_calendar_event_change: Callable[[str, str], None] | None = None,
    on_calendar_month_change: Callable[[str], None] | None = None,
    on_toggle_raw: Callable[[Any], None] | None = None,
    selector_scroll_offsets: Mapping[str, float] | None = None,
    on_selector_scroll_change: Callable[[str, float], None] | None = None,
) -> ft.Column:
    """Return a reusable Flet data page with trend, calendar, summary and raw rows."""

    cfg = config or DataPageConfig()
    view_state = {
        "period_days": cfg.period_days,
        "active_tab": cfg.active_tab,
        "chart_kind": cfg.chart_kind,
        "metric_key": cfg.metric_key,
        "selected_trend_date": cfg.selected_trend_date,
        "body_part_filter": cfg.body_part_filter,
        "selected_date": cfg.selected_date,
        "calendar_month": cfg.calendar_month,
        "action_trend_open": cfg.action_trend_open,
        "selected_exercise": cfg.selected_exercise,
        "raw_expanded": cfg.raw_expanded,
    }
    offsets = selector_scroll_offsets or {}

    def current_config() -> DataPageConfig:
        return DataPageConfig(**view_state)

    model_state = {"value": build_data_page_model(records, end_date=end_date, config=current_config())}

    def updated_model(result: Any = None) -> Mapping[str, Any]:
        model = result if isinstance(result, Mapping) else build_data_page_model(
            records, end_date=end_date, config=current_config()
        )
        model_state["value"] = model
        return model

    def request_update(control: ft.Control, event: Any = None) -> None:
        page = getattr(getattr(event, "control", None), "page", None)
        if page is None:
            try:
                page = control.page
            except RuntimeError:
                page = None
        if page is not None:
            try:
                control.update()
            except (RuntimeError, AssertionError):
                pass
            page.update()

    def select_row(row: ft.Row, key: str) -> None:
        for chip in row.controls:
            _set_chip_selected(chip, str(getattr(chip, "key", "")) == key)

    def chip(label: str, selected: bool, handler: Callable[[Any], None], key: str, *, horizontal_padding=10):
        control = _chip(label, selected, handler, horizontal_padding=horizontal_padding)
        control.key = key
        return control

    def update_nested(field: str, value: Any, callback: Callable[..., Any] | None, *args: Any):
        view_state[field] = value
        return updated_model(callback(*args) if callback is not None else None)

    def render_body(model: Mapping[str, Any]) -> ft.Control:
        if view_state["active_tab"] == "月历":
            def select_date(value: str):
                next_model = update_nested("selected_date", value, on_selected_date_change, value)
                body_holder.controls.clear(); body_holder.controls.append(render_body(next_model))
                request_update(body_holder)
                return next_model

            def select_month(value: str):
                view_state["selected_date"] = f"{value}-01"
                next_model = update_nested("calendar_month", value, on_calendar_month_change, value)
                body_holder.controls.clear(); body_holder.controls.append(render_body(next_model))
                request_update(body_holder)
                return next_model

            return _render_calendar(model, select_date, on_calendar_event_change, select_month)
        if view_state["active_tab"] == "汇总":
            return _render_summary(model)

        def open_action(event: Any = None):
            view_state["action_trend_open"] = True
            next_model = updated_model((on_action_trend_open or on_exercise_trends)(event) if (on_action_trend_open or on_exercise_trends) is not None else None)
            body_holder.controls.clear(); body_holder.controls.append(render_body(next_model))
            request_update(body_holder, event)
            return next_model

        def close_action(event: Any = None):
            view_state["action_trend_open"] = False
            next_model = updated_model(on_action_trend_close(event) if on_action_trend_close is not None else None)
            body_holder.controls.clear(); body_holder.controls.append(render_body(next_model))
            request_update(body_holder, event)
            return next_model

        return _render_trend_chart(
            model,
            on_add_record,
            open_action,
            close_action,
            lambda value: update_nested("selected_exercise", value, on_selected_exercise_change, value),
            lambda value: update_nested("body_part_filter", value, on_body_part_filter_change, value),
            lambda value: update_nested("metric_key", value, on_metric_change, value),
            lambda value: update_nested("selected_trend_date", value, on_trend_point_select, value),
            offsets,
            on_selector_scroll_change,
        )

    def choose_period(event: Any, days: int) -> None:
        if days == view_state["period_days"]:
            return
        view_state.update({"period_days": days, "selected_trend_date": None})
        model = updated_model(on_period_change(days) if on_period_change is not None else None)
        select_row(period_row, f"data-period:{days}")
        weekly_holder.controls.clear(); weekly_holder.controls.append(_render_weekly_review(model))
        body_holder.controls.clear(); body_holder.controls.append(render_body(model))
        raw_holder.controls.clear(); raw_holder.controls.append(render_raw(model))
        request_update(weekly_holder, event)
        request_update(body_holder, event)
        request_update(raw_holder, event)
        request_update(period_row, event)

    def choose_tab(event: Any, value: str) -> None:
        if value == view_state["active_tab"]:
            return
        view_state.update({"active_tab": value, "action_trend_open": False})
        model = updated_model(on_tab_change(value) if on_tab_change is not None else None)
        select_row(tab_row, f"data-tab:{value}")
        chart_row.visible = value == "趋势"
        body_holder.controls.clear(); body_holder.controls.append(render_body(model))
        request_update(body_holder, event)
        request_update(tab_row, event)

    def choose_chart(event: Any, value: str) -> None:
        if value == view_state["chart_kind"]:
            return
        view_state.update({"chart_kind": value, "metric_key": None, "selected_trend_date": None, "action_trend_open": False})
        model = updated_model(on_chart_change(value) if on_chart_change is not None else None)
        select_row(chart_row, f"data-chart:{value}")
        body_holder.controls.clear(); body_holder.controls.append(render_body(model))
        request_update(body_holder, event)
        request_update(chart_row, event)

    period_row = ft.Row([
        chip(f"{days}天", cfg.period_days == days, lambda e, value=days: choose_period(e, value), f"data-period:{days}")
        for days in PERIOD_OPTIONS
    ], spacing=6, data="analytics-period-selector")
    tab_row = ft.Row([
        chip(tab, cfg.active_tab == tab, lambda e, value=tab: choose_tab(e, value), f"data-tab:{tab}")
        for tab in VIEW_TABS
    ], spacing=6, data="analytics-tab-selector")
    chart_chips = [
        chip(str(label), cfg.chart_kind == key, lambda e, value=key: choose_chart(e, value), f"data-chart:{key}", horizontal_padding=4)
        for key, label in CHART_OPTIONS
    ]
    chart_row = ft.Row(chart_chips, spacing=6)
    chart_row.visible = cfg.active_tab == "趋势"
    chart_row.data = "analytics-chart-selector"

    def render_raw(model: Mapping[str, Any]) -> ft.Control:
        def toggle(event: Any = None):
            view_state["raw_expanded"] = not bool(view_state["raw_expanded"])
            next_model = updated_model(on_toggle_raw(event) if on_toggle_raw is not None else None)
            raw_holder.controls.clear(); raw_holder.controls.append(render_raw(next_model))
            request_update(raw_holder, event)
        return _render_raw_list(model, toggle)

    model = model_state["value"]
    weekly_holder = ft.Column([_render_weekly_review(model)], data="analytics-weekly-holder")
    body_holder = ft.Column([render_body(model)], data="analytics-body-holder")
    raw_holder = ft.Column([render_raw(model)], data="analytics-raw-holder")
    return ft.Column([
        weekly_holder,
        _card(ft.Column([
            ft.Row([
                _text("数据", size=20, weight="bold"),
                _text("默认7天，可切30/90", size=12, color=SUB, weight="bold"),
            ], alignment="spaceBetween"),
            period_row,
            tab_row,
            chart_row,
        ], spacing=10)),
        body_holder,
        raw_holder,
    ], spacing=8)


def build_main_data_page_hook(
    *,
    state_name: str = "data_page_state",
    records_name: str = "records",
    refresh_name: str = "refresh",
    selected_date_name: str = "selected_date",
) -> str:
    """Return the small ``main.py`` hook body needed to mount this component."""

    return f'''from analytics_views import DataPageConfig, build_data_page_view

{state_name} = {{"period_days": 7, "active_tab": "趋势", "chart_kind": "weight", "metric_key": "weight_kg", "selected_trend_date": None, "body_part_filter": "全部", "selected_date": None, "calendar_month": None, "action_trend_open": False, "selected_exercise": None, "raw_expanded": False, "selector_scroll_offsets": {{}}}}

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

    def remember_selector_scroll(key, offset):
        {state_name}.setdefault("selector_scroll_offsets", {{}})[key] = offset

    return build_data_page_view(
        {records_name},
        end_date={selected_date_name},
        config=DataPageConfig(**{{key: value for key, value in {state_name}.items() if key != "selector_scroll_offsets"}}),
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
        selector_scroll_offsets={state_name}.get("selector_scroll_offsets", {{}}),
        on_selector_scroll_change=remember_selector_scroll,
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
