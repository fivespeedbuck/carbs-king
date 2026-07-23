"""Personal profile form composition and calculated metrics."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import flet as ft

from ui_components import (
    GREEN, PRIMARY, PRIMARY_SOFT, TEXT, card, make_button, section_title,
    small_text, two_field_grid,
)


def build_profile_metrics(targets: Mapping[str, Any]) -> ft.Control:
    return ft.Container(
        content=ft.Column([
            ft.Row([small_text("去脂体重"), ft.Text(f"{targets['lean_mass']} kg", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
            ft.Row([small_text("BMR（基础代谢率）"), ft.Text(f"{int(targets['bmr'])} kcal", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
            ft.Row([small_text("TDEE（每日总能量消耗）"), ft.Text(f"≈ {int(targets['tdee'])} kcal", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
            ft.Row([small_text("活动系数"), ft.Text(f"{targets['activity_factor']}", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
            ft.Row([small_text("目标热量"), ft.Text(f"{int(targets['calorie_target'])} kcal", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
        ], spacing=6), bgcolor="#F8FAFC", border_radius=8, padding=12,
    )


def option_button(label: str, current: str, setter: Callable[[str], None]) -> ft.Control:
    selected = current == label
    return make_button(label, on_click=lambda e: setter(label), bgcolor=PRIMARY if selected else PRIMARY_SOFT, color="#FFFFFF" if selected else GREEN, expand=True)


def build_profile_details(
    field_boxes: Sequence[ft.Control],
    *,
    sex: str,
    activity_habit: str,
    on_save: Callable[[Any], None],
    on_record_measurement: Callable[[Any], None],
    on_sex_change: Callable[[str], None],
    on_activity_change: Callable[[str], None],
    metrics: ft.Control,
    macro_panel: ft.Control,
    backup_panel: ft.Control,
    viewport_width: int | float | None = None,
) -> ft.Control:
    weight_box, bodyfat_box, height_box, age_box, *circumference_boxes = field_boxes
    circumference_rows = [
        two_field_grid(*circumference_boxes[index:index + 2], viewport_width=viewport_width)
        for index in range(0, len(circumference_boxes), 2)
    ]
    return card(ft.Column([
        ft.Row([section_title("我"), make_button("保存", on_click=on_save, bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween"),
        two_field_grid(weight_box, bodyfat_box, viewport_width=viewport_width),
        two_field_grid(height_box, age_box, viewport_width=viewport_width),
        section_title("身体围度（可选）"),
        *circumference_rows,
        ft.Row([
            make_button(
                "记录本次测量", on_click=on_record_measurement,
                bgcolor=PRIMARY_SOFT, color=GREEN, expand=True,
            ),
        ]),
        small_text("性别"),
        ft.Row([option_button("男", sex, on_sex_change), option_button("女", sex, on_sex_change)], spacing=8),
        small_text("运动习惯"),
        ft.Row([option_button("久坐少动", activity_habit, on_activity_change), option_button("偶尔运动", activity_habit, on_activity_change)], spacing=8),
        ft.Row([option_button("规律训练", activity_habit, on_activity_change), option_button("高频训练", activity_habit, on_activity_change)], spacing=8),
        metrics,
        macro_panel,
        backup_panel,
        ft.Container(content=small_text("围度只做趋势记录，不参与碳循环公式。保存资料不会新增测量记录。"), bgcolor="#FAFAFA", border_radius=8, padding=10),
    ], spacing=10))


__all__ = ["build_profile_details", "build_profile_metrics", "option_button"]
