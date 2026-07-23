"""Monthly calendar and selected-day views for analytics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

import flet as ft

from analytics_model import (
    BORDER,
    CALENDAR_KCAL_BAND_BELOW,
    CALENDAR_KCAL_BAND_HIGH,
    CALENDAR_KCAL_BAND_MISSING,
    CALENDAR_KCAL_BAND_OVER,
    CALENDAR_KCAL_BAND_TARGET,
    ORANGE,
    PRIMARY,
    PRIMARY_SOFT,
    RED,
    SUB,
    SURFACE,
    TEXT,
    WHITE,
    _mapping,
    _shift_month,
)
from analytics_ui import _border, _card, _chip, _metric, _text, _value_or_empty


CALENDAR_CELL_HEIGHT = 92

_CARBON_COLORS = {
    "低": PRIMARY,
    "中": "#C58A00",
    "高": "#C33B3B",
}

CALENDAR_KCAL_COLORS = {
    CALENDAR_KCAL_BAND_MISSING: SUB,
    CALENDAR_KCAL_BAND_BELOW: SUB,
    CALENDAR_KCAL_BAND_TARGET: PRIMARY,
    CALENDAR_KCAL_BAND_OVER: "#B78600",
    CALENDAR_KCAL_BAND_HIGH: RED,
}


def _calendar_activity_lines(item: Mapping[str, Any]) -> list[str]:
    model_lines = [str(line).strip() for line in item.get("activity_lines", []) if str(line).strip()]
    if model_lines:
        return model_lines
    activity_type = item.get("activity_type")
    if activity_type == "training":
        parts = [str(part).strip() for part in item.get("body_parts", []) if str(part).strip()]
        if not parts:
            return ["训练"]
        if len(parts) <= 3:
            return parts
        return [parts[0], parts[1], f"{parts[2]} +{len(parts) - 3}"]
    if activity_type == "rest":
        return ["休息"]
    if activity_type == "custom":
        return [str(item.get("activity") or "事项")[:3]]
    return []


def _calendar_activity_label(item: Mapping[str, Any]) -> str:
    return "\n".join(_calendar_activity_lines(item))


def _calendar_kcal_label(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    rounded = round(value)
    return f"{rounded:g}"


def _calendar_kcal_control(item: Mapping[str, Any]) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            _calendar_kcal_label(item.get("kcal")),
            size=12,
            color=CALENDAR_KCAL_COLORS.get(str(item.get("kcal_band")), SUB),
            weight="bold",
            max_lines=1,
            no_wrap=True,
        ),
        height=16,
        alignment=ft.Alignment.BOTTOM_RIGHT,
        data="calendar-kcal-bottom-right",
    )

def _render_calendar_summary(model: Mapping[str, Any]) -> ft.Control:
    summary = _mapping(model.get("calendar_summary"))
    return ft.Column(
        [
            ft.Row([
                _metric("训练天数", _value_or_empty(summary.get("training_days"))),
                _metric("训练时长", _value_or_empty(summary.get("training_duration_min"), "分")),
            ], spacing=8),
            ft.Row([
                _metric("正式组数", _value_or_empty(summary.get("formal_sets"))),
                _metric("月总摄入", _value_or_empty(summary.get("total_kcal"), "kcal")),
            ], spacing=8),
            ft.Row([
                _metric("饮食记录日", _value_or_empty(summary.get("diet_recorded_days"))),
                _metric("记录日均摄入", _value_or_empty(summary.get("avg_kcal_on_diet_days"), "kcal")),
            ], spacing=8),
        ],
        spacing=8,
    )


def _render_selected_day_detail(
    model: Mapping[str, Any],
    on_calendar_event_change: Callable[[str, str], None] | None = None,
) -> ft.Control:
    detail = _mapping(model.get("selected_day"))
    training = _mapping(detail.get("training"))
    diet = _mapping(detail.get("diet"))
    if detail.get("record_state") == "unrecorded":
        lines = [_text("该日无记录", size=14, color=SUB, weight="bold")]
    else:
        lines = [
            _text(f"碳循环：{detail.get('day_type') or '未记录'}", size=13, color=TEXT),
            _text(
                "状态：休息" if detail.get("record_state") == "rest" else "状态：训练" if training else "状态：自定义事项" if detail.get("event_text") else "状态：未记录",
                size=13,
                color=TEXT,
            ),
            _text(
                f"训练：{training.get('body_part_label') or '无'} · {_value_or_empty(training.get('duration_min'), '分')} · {_value_or_empty(training.get('formal_sets'))}组"
                if training else "训练：无",
                size=13,
                color=TEXT,
            ),
            _text(
                f"饮食：{_value_or_empty(diet.get('kcal'), 'kcal')} · 碳 {_value_or_empty(diet.get('carb'))} 蛋 {_value_or_empty(diet.get('protein'))} 脂 {_value_or_empty(diet.get('fat'))}"
                if diet else "饮食：无",
                size=13,
                color=TEXT,
            ),
            _text(f"备注/事项：{detail.get('event_text') or '无'}", size=13, color=TEXT),
        ]
    return ft.Container(
        content=ft.Column([
            ft.Row([_text("选中日期", size=15, weight="bold"), _text(detail.get("date", ""), size=13, color=SUB)], alignment="spaceBetween"),
            *lines,
            ft.Row([
                _chip("标记休息", detail.get("record_state") == "rest", None if on_calendar_event_change is None else lambda e: on_calendar_event_change(str(detail.get("date", "")), "rest")),
                _chip("自定义事项", detail.get("activity_type") == "custom", None if on_calendar_event_change is None else lambda e: on_calendar_event_change(str(detail.get("date", "")), "custom")),
                _chip("清除事项", False, None if on_calendar_event_change is None else lambda e: on_calendar_event_change(str(detail.get("date", "")), "clear")),
            ], spacing=6),
        ], spacing=5),
        bgcolor=SURFACE,
        border_radius=8,
        padding=10,
    )


def _render_calendar(
    model: Mapping[str, Any],
    on_selected_date_change: Callable[[str], None] | None,
    on_calendar_event_change: Callable[[str, str], None] | None = None,
    on_calendar_month_change: Callable[[str], None] | None = None,
) -> ft.Container:
    month_anchor = date.fromisoformat(f"{model.get('calendar_month')}-01")

    def change_month(target: date):
        if on_calendar_month_change is not None:
            on_calendar_month_change(target.strftime("%Y-%m"))

    def open_month_picker(e):
        if on_calendar_month_change is None:
            return
        year = ft.Dropdown(
            value=str(month_anchor.year),
            options=[ft.DropdownOption(str(item)) for item in range(month_anchor.year - 10, month_anchor.year + 11)],
            expand=True,
        )
        month = ft.Dropdown(
            value=str(month_anchor.month),
            options=[ft.DropdownOption(str(item)) for item in range(1, 13)],
            expand=True,
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=_text("选择年月", size=18, weight="bold"),
            content=ft.Container(
                content=ft.Row([
                    ft.Column([_text("年份", size=12, color=SUB, weight="bold"), year], spacing=4, expand=True),
                    ft.Column([_text("月份", size=12, color=SUB, weight="bold"), month], spacing=4, expand=True),
                ], spacing=8, vertical_alignment="start"),
                width=240,
                height=78,
            ),
        )
        page = e.control.page

        def close_dialog(_=None):
            dialog.open = False
            page.update()

        def confirm(_=None):
            change_month(date(int(year.value), int(month.value), 1))
            close_dialog()

        dialog.actions = [
            ft.TextButton("取消", on_click=close_dialog),
            ft.FilledButton("确定", on_click=confirm),
        ]
        if dialog not in page.overlay:
            page.overlay.append(dialog)
        dialog.open = True
        page.update()

    cells: list[ft.Control] = []
    for item in model.get("calendar", []):
        if not item.get("in_month"):
            cells.append(ft.Container(height=CALENDAR_CELL_HEIGHT, bgcolor="#FBFCFB", border_radius=5, expand=True))
            continue
        state = item.get("record_state")
        selected = bool(item.get("selected"))
        state_color = PRIMARY if state == "recorded" else ORANGE if state == "rest" else BORDER
        day = str(item.get("date", ""))[-2:]
        day_type = str(item.get("compact_day_type") or "")
        activity_lines = _calendar_activity_lines(item)
        click = None if on_selected_date_change is None else lambda e, value=item.get("date"): on_selected_date_change(str(value))
        cells.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row([
                            ft.Text(day, size=12, weight="bold", color=TEXT, no_wrap=True),
                            ft.Text(day_type, size=12, weight="bold", color=_CARBON_COLORS.get(day_type, SUB), no_wrap=True),
                        ], alignment="spaceBetween", spacing=1),
                        ft.Column([
                            ft.Text(label, size=12, color=TEXT, weight="bold", max_lines=1, no_wrap=True)
                            for label in activity_lines
                        ], spacing=0, expand=True),
                        _calendar_kcal_control(item),
                    ],
                    spacing=2,
                ),
                height=CALENDAR_CELL_HEIGHT,
                padding=3,
                bgcolor=PRIMARY_SOFT if selected else WHITE,
                border=_border(PRIMARY if selected else state_color if state != "unrecorded" else BORDER, 2 if selected else 1),
                border_radius=6,
                expand=True,
                tooltip=item.get("event_text") or None,
                on_click=click,
            )
        )
    rows = [ft.Row(cells[index:index + 7], spacing=1) for index in range(0, len(cells), 7)]
    weekdays = [
        ft.Container(content=ft.Text(label, size=12, color=SUB, weight="bold", text_align="center"), expand=True, alignment=ft.Alignment.CENTER)
        for label in ("一", "二", "三", "四", "五", "六", "日")
    ]
    return _card(
        ft.Column([
            _render_calendar_summary(model),
            ft.Row([
                ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="上一月", on_click=lambda e: change_month(_shift_month(month_anchor, -1))),
                ft.TextButton(f"{month_anchor.year}年{month_anchor.month:02d}月", on_click=open_month_picker, expand=True),
                ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="下一月", on_click=lambda e: change_month(_shift_month(month_anchor, 1))),
            ], spacing=2, alignment="center"),
            ft.Row(
                [ft.TextButton("回到本月", on_click=lambda e: change_month(date.today().replace(day=1)))],
                alignment="center",
            ) if (month_anchor.year, month_anchor.month) != (date.today().year, date.today().month) else ft.Container(height=0),
            ft.Container(
                content=ft.Column([
                    ft.Row(weekdays, spacing=1),
                    *rows,
                ], spacing=1),
            ),
            _render_selected_day_detail(model, on_calendar_event_change),
        ], spacing=10),
        padding=6,
    )
