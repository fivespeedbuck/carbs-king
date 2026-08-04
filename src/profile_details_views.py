"""Personal profile form composition and calculated metrics."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import flet as ft

from ui_components import (
    GREEN, PRIMARY, PRIMARY_SOFT, TEXT, page_card, make_button, section_title,
    small_text, two_field_grid, SUB,
)
from ui_components import YELLOW


def build_profile_metrics(targets: Mapping[str, Any]) -> ft.Control:
    if not targets.get("is_ready", True):
        return ft.Container(height=0)
    lean_mass = targets.get("lean_mass")
    rows = []
    if lean_mass is not None:
        rows.append(ft.Row([small_text("去脂体重"), ft.Text(f"{lean_mass} kg", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"))
    rows.extend([
        ft.Row([small_text("BMR（基础代谢率）"), ft.Text(f"{int(targets['bmr'])} kcal", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
        ft.Row([small_text("TDEE（每日总能量消耗）"), ft.Text(f"≈ {int(targets['tdee'])} kcal", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
        ft.Row([small_text("目标热量"), ft.Text(f"{int(targets['calorie_target'])} kcal", size=14, weight="bold", color=TEXT)], alignment="spaceBetween"),
    ])
    return ft.Container(
        content=ft.Column(rows, spacing=6), bgcolor="#F8FAFC", border_radius=8, padding=12,
    )


def option_button(label: str, current: str, setter: Callable[[str], None]) -> ft.Control:
    selected = current == label
    return make_button(label, on_click=lambda e: setter(label), bgcolor=PRIMARY if selected else PRIMARY_SOFT, color="#FFFFFF" if selected else GREEN, expand=True)


def build_profile_details(
    field_boxes: Sequence[ft.Control],
    *,
    sex: str,
    activity_habit: str,
    circumference_values: Mapping[str, Any],
    circumference_status: Mapping[str, Mapping[str, Any]] | None = None,
    stale_profile_fields: Mapping[str, bool] | None = None,
    circumference_expanded: bool,
    on_toggle_circumference: Callable[[Any], None],
    on_sex_change: Callable[[str], None],
    on_activity_change: Callable[[str], None],
    metrics: ft.Control,
    macro_panel: ft.Control,
    backup_panel: ft.Control,
    feature_panels: Sequence[ft.Control] = (),
    theme_panel: ft.Control | None = None,
    update_panel: ft.Control | None = None,
    viewport_width: int | float | None = None,
) -> ft.Control:
    weight_box, bodyfat_box, height_box, age_box = field_boxes
    stale_profile_fields = stale_profile_fields or {}
    circumference_status = circumference_status or {}
    for field_key, field_box in (("weight", weight_box), ("bodyfat", bodyfat_box)):
        if not stale_profile_fields.get(field_key):
            continue
        controls = getattr(field_box, "controls", [])
        if controls and getattr(controls[0], "content", None) is not None:
            controls[0].content.color = YELLOW
    circumference_labels = (
        ("chest_cm", "胸围"), ("waist_cm", "腰围"), ("hip_cm", "臀围"),
        ("arm_cm", "上臂围"), ("thigh_cm", "大腿围"), ("calf_cm", "小腿围"),
    )
    circumference_rows = []
    if circumference_expanded:
        values = []
        for key, label in circumference_labels:
            raw = circumference_values.get(key, "")
            value = f"{raw} cm" if raw not in (None, "") else "未记录"
            stale = bool(circumference_status.get(key, {}).get("stale"))
            values.append(ft.Container(
                content=ft.Column([
                    small_text(label, color=YELLOW if stale else SUB),
                    ft.Text(value, size=14, weight="bold", color=YELLOW if stale else TEXT),
                    small_text("建议更新" if stale else " ", color=YELLOW),
                ], spacing=3),
                bgcolor="#FFF8D6" if stale else "#F8FAFC", border_radius=8, padding=10, expand=True,
            ))
        circumference_rows = [
            two_field_grid(*values[index:index + 2], viewport_width=viewport_width)
            for index in range(0, len(values), 2)
        ]
    profile_card = page_card(ft.Column([
        section_title("我"),
        two_field_grid(weight_box, bodyfat_box, viewport_width=viewport_width),
        two_field_grid(height_box, age_box, viewport_width=viewport_width),
        make_button(
            "收起身体围度" if circumference_expanded else "查看身体围度",
            on_click=on_toggle_circumference,
            bgcolor=PRIMARY_SOFT,
            color=GREEN,
            expand=True,
        ),
        *circumference_rows,
        small_text("性别"),
        ft.Row([option_button("男", sex, on_sex_change), option_button("女", sex, on_sex_change)], spacing=8),
        small_text("运动习惯"),
        ft.Row([option_button("久坐少动", activity_habit, on_activity_change), option_button("偶尔运动", activity_habit, on_activity_change)], spacing=8),
        ft.Row([option_button("规律训练", activity_habit, on_activity_change), option_button("高频训练", activity_habit, on_activity_change)], spacing=8),
        metrics,
        macro_panel,
    ], spacing=10))
    settings_sections = [section_title("功能设置")]
    if theme_panel is not None:
        settings_sections.append(theme_panel)
    settings_sections.extend(feature_panels)
    settings_sections.append(backup_panel)
    if update_panel is not None:
        settings_sections.append(update_panel)
    settings_card = page_card(ft.Column(settings_sections, spacing=10))
    return ft.Column([profile_card, settings_card], spacing=0)


__all__ = ["build_profile_details", "build_profile_metrics", "option_button"]
