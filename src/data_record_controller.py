"""Data page controller for measurement and calendar record intents."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import flet as ft

from analytics_views import DataPageConfig, build_data_page_view
from app_defaults import CIRCUMFERENCE_FIELDS
from app_state import AppState
from controller_runtime import ControllerRuntime
from daily_record_controller import DailyRecordController
from form_views import FormViewContext, build_dialog, build_full_form_sheet
from repositories import AppRepositories
from ui_components import RED, labeled_plain_field, make_button, mobile_dropdown, mobile_text_field, small_text


@dataclass(frozen=True)
class DataRecordControllerDependencies:
    state: AppState
    repositories: AppRepositories
    records: dict[str, Any]
    daily_records: DailyRecordController
    runtime: ControllerRuntime
    iso_now: Callable[[], str]
    keyboard_number: Any
    scroll_hidden: Any
    today: Callable[[], date] = date.today


@dataclass
class DataRecordController:
    render_page: Callable[[], ft.Control]


def create_data_record_controller(deps: DataRecordControllerDependencies) -> DataRecordController:
    state = deps.state
    repositories = deps.repositories
    records = deps.records
    daily_records = deps.daily_records
    runtime = deps.runtime
    refresh = runtime.refresh
    snack = runtime.snack
    set_view = runtime.navigate
    open_control = runtime.open_control
    close_control = runtime.close_control
    responsive_width = runtime.responsive_width
    iso_now = deps.iso_now
    _KEYBOARD_NUMBER = deps.keyboard_number
    _SCROLL_HIDDEN = deps.scroll_hidden

    def dialog_base(title, content, actions=None, on_close=None):
        return build_dialog(title, content, actions=actions, on_close=on_close)

    def full_form_sheet(title, controls, on_save, save_label="保存"):
        return build_full_form_sheet(
            FormViewContext(close_control=close_control, scroll_mode=_SCROLL_HIDDEN),
            title,
            controls,
            on_save,
            save_label,
        )

    def render_data_page():
        data_state = state.setdefault("data_page", {})

        def update_data_page(**changes):
            data_state.update(changes)
            refresh()

        def open_circumference_form():
            circumference_options = list(CIRCUMFERENCE_FIELDS)
            selected_key = str(data_state.get("metric_key") or "waist_cm")
            if selected_key not in {key for key, _ in circumference_options}:
                selected_key = "waist_cm"
            record_date = str(data_state.get("selected_trend_date") or state.get("date") or date.today().isoformat())
            current_record = records.get(record_date, {}) if isinstance(records, dict) else {}
            current_profile = current_record.get("profile", {}) if isinstance(current_record, dict) else {}
            current_circumference = current_profile.get("circumference", {}) if isinstance(current_profile, dict) else {}
            existing = current_circumference.get(selected_key, "") if isinstance(current_circumference, dict) else ""
            has_existing = any(
                current_circumference.get(key) not in (None, "")
                for key, _ in circumference_options
            ) if isinstance(current_circumference, dict) else False
            existing_notes = current_circumference.get("notes", {}) if isinstance(current_circumference, dict) else {}

            date_box, date_field = labeled_plain_field("日期", record_date, width=responsive_width())
            metric_field = mobile_dropdown(
                "围度项目",
                selected_key,
                [ft.dropdown.Option(key=key, text=label) for key, label in circumference_options],
                width=responsive_width(),
            )
            value_box, value_field = labeled_plain_field("数值 cm", existing, keyboard_type=_KEYBOARD_NUMBER, width=responsive_width())
            note_box, note_field = labeled_plain_field(
                "备注（可选）",
                existing_notes.get(selected_key, "") if isinstance(existing_notes, dict) else "",
                width=responsive_width(),
            )
            sheet = None

            def save_circumference(e=None):
                target_date = str(date_field.value or "").strip()
                try:
                    date.fromisoformat(target_date)
                except ValueError:
                    snack("请输入正确日期，例如 2026-07-22")
                    return
                metric_key = str(metric_field.field.value or "waist_cm")
                raw_value = str(value_field.value or "").strip()
                try:
                    metric_value = float(raw_value)
                except ValueError:
                    snack("请输入围度数值")
                    return
                if not 1 <= metric_value <= 300:
                    snack("围度应在 1-300 cm 之间")
                    return
                note = str(note_field.value or "").strip()
                daily_records.update_circumference(
                    target_date,
                    metric_key,
                    metric_value,
                    measured_at=iso_now(),
                    note=note,
                )
                data_state.update({
                    "active_tab": "趋势", "chart_kind": "circumference", "metric_key": metric_key,
                    "selected_trend_date": target_date,
                })
                close_control(sheet)
                refresh()
                snack("围度已记录")

            def delete_circumference(e=None):
                target_date = str(date_field.value or "").strip()
                metric_key = str(metric_field.field.value or "waist_cm")
                if not daily_records.delete_circumference(target_date, metric_key):
                    snack("没有可删除的围度记录")
                    return
                data_state["selected_trend_date"] = None
                close_control(sheet)
                refresh()
                snack("围度记录已删除")

            controls = [date_box, metric_field, value_box, note_box]
            if has_existing:
                controls.append(make_button(
                    "删除这条围度记录",
                    on_click=delete_circumference,
                    bgcolor="#FDECEC",
                    color=RED,
                    expand=True,
                ))
            sheet = full_form_sheet("记录围度", controls, save_circumference)
            open_control(sheet)

        def open_record_surface(kind):
            if kind in {"weight", "bodyfat", "recovery"}:
                set_view("daily_details")
                return
            if kind == "circumference":
                open_circumference_form()
                return
            if kind == "diet":
                set_view("diet")
                return
            set_view("training")

        def save_calendar_event(selected_date, event):
            daily_records.update_calendar_event(selected_date, event)
            data_state["selected_date"] = selected_date
            refresh()

        def edit_calendar_event(selected_date, action):
            if action == "rest":
                save_calendar_event(selected_date, {"type": "rest", "text": "休息"})
                return
            if action == "clear":
                save_calendar_event(selected_date, None)
                return
            current = records.get(selected_date, {})
            current_event = current.get("calendar_event", {}) if isinstance(current, dict) else {}
            note = mobile_text_field("事项内容", str(current_event.get("text", "")) if isinstance(current_event, dict) else "", width=responsive_width())
            dlg = None

            def confirm_custom(e=None):
                text = str(note.value or "").strip()
                if not text:
                    snack("请输入事项内容")
                    return
                close_control(dlg)
                save_calendar_event(selected_date, {"type": "custom", "text": text})

            dlg = dialog_base(
                "自定义事项",
                ft.Column([small_text(selected_date), note], width=responsive_width(), spacing=8),
                [make_button("保存事项", on_click=confirm_custom, expand=True)],
                on_close=lambda e: close_control(dlg),
            )
            open_control(dlg)

        config = DataPageConfig(
            period_days=int(data_state.get("period_days", 7)),
            active_tab=str(data_state.get("active_tab", "趋势")),
            chart_kind=str(data_state.get("chart_kind", "weight")),
            metric_key=data_state.get("metric_key"),
            selected_trend_date=data_state.get("selected_trend_date"),
            body_part_filter=str(data_state.get("body_part_filter", "全部")),
            selected_date=data_state.get("selected_date") or state.get("date"),
            calendar_month=data_state.get("calendar_month"),
            action_trend_open=bool(data_state.get("action_trend_open", False)),
            selected_exercise=data_state.get("selected_exercise"),
            raw_expanded=bool(data_state.get("raw_expanded", False)),
        )
        records_local = repositories.records.load()
        return build_data_page_view(
            records_local if isinstance(records_local, dict) else {},
            end_date=deps.today().isoformat(),
            config=config,
            on_period_change=lambda days: update_data_page(period_days=days, selected_trend_date=None),
            on_tab_change=lambda tab: update_data_page(active_tab=tab, action_trend_open=False),
            on_chart_change=lambda kind: update_data_page(chart_kind=kind, metric_key=None, selected_trend_date=None, action_trend_open=False),
            on_metric_change=lambda metric: update_data_page(metric_key=metric, selected_trend_date=None),
            on_trend_point_select=lambda selected: update_data_page(selected_trend_date=selected),
            on_add_record=open_record_surface,
            on_action_trend_open=lambda e: update_data_page(action_trend_open=True),
            on_action_trend_close=lambda e: update_data_page(action_trend_open=False),
            on_selected_exercise_change=lambda name: update_data_page(selected_exercise=name),
            on_body_part_filter_change=lambda part: update_data_page(body_part_filter=part),
            on_selected_date_change=lambda selected: update_data_page(selected_date=selected),
            on_calendar_month_change=lambda month: update_data_page(calendar_month=month, selected_date=f"{month}-01"),
            on_calendar_event_change=edit_calendar_event,
            on_toggle_raw=lambda e: update_data_page(raw_expanded=not bool(data_state.get("raw_expanded", False))),
        )

    return DataRecordController(render_page=render_data_page)


__all__ = ["DataRecordController", "DataRecordControllerDependencies", "create_data_record_controller"]
