"""Macro-mode summary controls for the profile feature."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from ui_components import GREEN, PRIMARY, PRIMARY_SOFT, make_button, section_title, small_text


GOAL_OPTIONS = ("减脂", "保持", "增肌")


def build_carb_cycle_goal_section(
    current_goal: str,
    on_change: Callable[[str], None],
    *,
    applied_goal: str | None = None,
    on_apply: Callable[[str], None] | None = None,
) -> ft.Control:
    applied = applied_goal or current_goal
    previewing = current_goal != applied
    controls: list[ft.Control] = [
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
    ]
    if previewing:
        controls.extend([
            small_text(f"正在预览{current_goal}；当前实际目标仍是{applied}"),
            make_button(
                f"应用为当前{current_goal}目标",
                on_click=lambda e: on_apply(current_goal) if on_apply is not None else None,
                bgcolor=PRIMARY_SOFT,
                color=GREEN,
                expand=True,
            ),
        ])
    return ft.Column(controls, spacing=6)


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
    applied_goal: str | None = None,
    on_goal_apply: Callable[[str], None] | None = None,
) -> ft.Control:
    goal_section = (
        build_carb_cycle_goal_section(
            current_goal,
            on_goal_change,
            applied_goal=applied_goal,
            on_apply=on_goal_apply,
        )
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
                "自动目标会根据个人资料与已确认训练生成；自定义模式不会被自动调整。" if auto_selected
                else "当前显示自定义倍率，可点击右上角编辑。"
            ) if profile_ready else ft.Container(height=0),
            small_text("自动目标仅适用于一般健康成人；孕哺期、糖尿病用药、肾病或进食障碍请使用专业医疗方案。")
            if profile_ready and auto_selected else ft.Container(height=0),
        ], spacing=7),
        bgcolor="#F8FAFC",
        border_radius=8,
        padding=12,
    )


__all__ = ["build_carb_cycle_goal_section", "build_macro_panel"]
