"""Macro-mode summary controls for the profile feature."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from ui_components import GREEN, PRIMARY, PRIMARY_SOFT, make_button, section_title, small_text


GOAL_OPTIONS = ("减脂", "保持", "增肌")


def build_carb_cycle_goal_section(current_goal: str, on_change: Callable[[str], None]) -> ft.Control:
    return ft.Column([
        section_title("碳循环目标"),
        ft.Row([
            make_button(
                "减脂",
                on_click=lambda e: on_change("减脂"),
                bgcolor=PRIMARY if current_goal == "减脂" else PRIMARY_SOFT,
                color="#FFFFFF" if current_goal == "减脂" else GREEN,
                expand=True,
            ),
            make_button(
                "保持",
                on_click=lambda e: on_change("保持"),
                bgcolor=PRIMARY if current_goal == "保持" else PRIMARY_SOFT,
                color="#FFFFFF" if current_goal == "保持" else GREEN,
                expand=True,
            ),
            make_button(
                "增肌",
                on_click=lambda e: on_change("增肌"),
                bgcolor=PRIMARY if current_goal == "增肌" else PRIMARY_SOFT,
                color="#FFFFFF" if current_goal == "增肌" else GREEN,
                expand=True,
            ),
        ], spacing=8),
    ], spacing=6)


def build_macro_panel(
    rows: Sequence[ft.Control],
    *,
    auto_selected: bool,
    on_edit: Callable[[Any], None],
    on_mode_change: Callable[[str], None],
    profile_ready: bool = True,
    profile_message: str = "",
    current_goal: str = "减脂",
    on_goal_change: Callable[[str], None] | None = None,
) -> ft.Control:
    goal_section = (
        build_carb_cycle_goal_section(current_goal, on_goal_change)
        if auto_selected and on_goal_change is not None
        else ft.Container(height=0)
    )
    return ft.Container(
        content=ft.Column([
            ft.Row([
                section_title("宏量目标计算"),
                make_button("编辑自定义倍率", on_click=on_edit, bgcolor=PRIMARY_SOFT, color=GREEN)
                if not auto_selected else ft.Container(width=0),
            ], alignment="spaceBetween"),
            ft.Row([
                make_button("自动计算", on_click=lambda e: on_mode_change("auto"), bgcolor=PRIMARY if auto_selected else PRIMARY_SOFT, color="#FFFFFF" if auto_selected else GREEN, expand=True),
                make_button("自定义", on_click=lambda e: on_mode_change("custom"), bgcolor=PRIMARY if not auto_selected else PRIMARY_SOFT, color="#FFFFFF" if not auto_selected else GREEN, expand=True),
            ], spacing=8),
            goal_section,
            small_text(profile_message) if not profile_ready else ft.Container(height=0),
            *rows,
            small_text(
                "当前显示自动计算倍率，仅供查看。" if auto_selected
                else "当前显示自定义倍率，可点击右上角编辑。"
            ) if profile_ready else ft.Container(height=0),
        ], spacing=7),
        bgcolor="#F8FAFC",
        border_radius=8,
        padding=12,
    )


__all__ = ["build_carb_cycle_goal_section", "build_macro_panel"]
