"""Today dashboard presentation.

The module accepts prepared view data and action callbacks. It does not read
files, mutate application state, or calculate domain metrics.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from ui_components import (
    BORDER,
    ORANGE,
    PRIMARY,
    SKY_BLUE,
    SUB,
    TEXT,
    macro_progress_bar,
    pill,
    section_title,
    small_text,
    thin_border,
)


TODAY_SECTION_SPACING = 8


@dataclass(frozen=True)
class TodayDashboardModel:
    kcal: float
    kcal_target: float
    day_type: str
    macros: Mapping[str, float]
    targets: Mapping[str, float]
    training_title: str
    training_subtitle: str
    training_icon: Any
    training_clock_active: bool
    meal_counts: Mapping[str, int]
    water_ml: int
    supplement_count: int
    sleep_text: str


@dataclass(frozen=True)
class TodayDashboardActions:
    open_training: Callable[[Any], None]
    open_meal: Callable[[str], None]
    open_recovery: Callable[[Any], None]


@dataclass(frozen=True)
class TodayDashboardResult:
    control: ft.Control
    training_clock: ft.Text | None


def build_date_toolbar(
    date_label: str,
    on_previous: Callable[[Any], None],
    on_calendar: Callable[[Any], None],
    on_next: Callable[[Any], None],
    on_today: Callable[[Any], None],
    on_save: Callable[[Any], None],
):
    from ui_components import GREEN, PRIMARY_SOFT, card, make_button

    return card(ft.Column([
        ft.Row([
            ft.IconButton(icon=ft.Icons.ARROW_BACK_IOS_NEW_ROUNDED, icon_size=17, on_click=on_previous),
            ft.Container(
                content=ft.Row([
                    ft.Text(date_label, size=17, weight="bold", color=TEXT),
                    ft.Container(),
                ], alignment="center", spacing=6),
                expand=True,
            ),
            ft.IconButton(icon=ft.Icons.CALENDAR_MONTH_OUTLINED, icon_size=19, icon_color=PRIMARY, on_click=on_calendar),
            ft.IconButton(icon=ft.Icons.ARROW_FORWARD_IOS_ROUNDED, icon_size=17, on_click=on_next),
        ], alignment="spaceBetween", vertical_alignment="center"),
        ft.Row([
            make_button("今日", on_click=on_today, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
            make_button("保存", on_click=on_save, expand=True),
        ], spacing=8),
    ], spacing=8), padding=12, margin_bottom=8)


def build_today_dashboard(
    model: TodayDashboardModel,
    actions: TodayDashboardActions,
    meals: Sequence[str],
    bar_width: int,
) -> TodayDashboardResult:
    macro_card = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Column([
                    small_text("今日摄入"),
                    ft.Text(f"{model.kcal:g}", size=40, weight="bold", color=TEXT),
                    small_text(f"目标约 {model.kcal_target:g} kcal"),
                ], spacing=2),
                pill(model.day_type, ORANGE if model.day_type == "高碳日" else SKY_BLUE if model.day_type == "中碳日" else "#7C5CC4"),
            ], alignment="spaceBetween", vertical_alignment="start"),
            macro_progress_bar("碳水", model.macros["carb"], target_min=model.targets["carb_min"], target_max=model.targets["carb_max"], kind="carb", width=bar_width),
            macro_progress_bar("蛋白", model.macros["protein"], target_min=model.targets["protein_min"], target_max=model.targets["protein_max"], kind="protein", width=bar_width),
            macro_progress_bar("脂肪", model.macros["fat"], target_min=model.targets["fat_min"], target_max=model.targets["fat_max"], kind="fat", width=bar_width),
        ], spacing=8),
        bgcolor="#FFFFFF",
        border=thin_border(),
        border_radius=12,
        padding=18,
        margin=ft.Margin(left=8, top=0, right=8, bottom=0),
    )

    training_subtitle = ft.Text(model.training_subtitle, size=14, color="#EAFBF5", weight="bold")
    training_card = ft.Container(
        content=ft.Row([
            ft.Container(content=ft.Icon(model.training_icon, size=32, color="#FFFFFF"), width=56, height=56, bgcolor="#0E604E", border_radius=14, alignment=ft.Alignment.CENTER),
            ft.Column([ft.Text(model.training_title, size=20, weight="bold", color="#FFFFFF"), training_subtitle], expand=True, spacing=4),
            ft.Icon(ft.Icons.CHEVRON_RIGHT, color="#FFFFFF"),
        ], spacing=12, vertical_alignment="center"),
        bgcolor="#116E59",
        border_radius=12,
        padding=18,
        margin=ft.Margin(left=8, top=0, right=8, bottom=0),
        on_click=actions.open_training,
    )

    def meal_tile(meal: str):
        count = int(model.meal_counts.get(meal, 0))
        return ft.Container(
            content=ft.Column([
                ft.Text(meal, size=13, weight="bold", color=TEXT),
                ft.Text(f"已记 {count} 项" if count else "未记录 +", size=14, color=PRIMARY if count else SUB, weight="bold", max_lines=1, overflow="ellipsis"),
            ], horizontal_alignment="center", alignment="center", spacing=3),
            height=66,
            bgcolor="#FFFFFF",
            border=thin_border(PRIMARY if count else BORDER),
            border_radius=10,
            expand=True,
            ink=True,
            on_click=lambda e, selected=meal: actions.open_meal(selected),
        )

    meals_card = ft.Container(
        content=ft.Column([
            ft.Row([section_title("六餐记录"), small_text("点击进入对应餐次")], alignment="spaceBetween"),
            ft.Row([meal_tile(meal) for meal in meals[:3]], spacing=8),
            ft.Row([meal_tile(meal) for meal in meals[3:]], spacing=8),
        ], spacing=10),
        bgcolor="#FFFFFF",
        border=thin_border(),
        border_radius=12,
        padding=16,
        margin=ft.Margin(left=8, top=0, right=8, bottom=0),
    )

    recovery_card = ft.Container(
        content=ft.Column([
            ft.Row([section_title("身体与恢复"), ft.Icon(ft.Icons.CHEVRON_RIGHT, color=SUB)], alignment="spaceBetween"),
            ft.Row([
                ft.Column([small_text("饮水"), ft.Text(f"{model.water_ml} ml", size=15, weight="bold", color=TEXT)], expand=True),
                ft.Column([small_text("补剂"), ft.Text(f"{model.supplement_count} 项", size=15, weight="bold", color=TEXT)], expand=True),
                ft.Column([small_text("睡眠"), ft.Text(model.sleep_text, size=15, weight="bold", color=TEXT)], expand=True),
            ], spacing=8),
        ], spacing=12),
        bgcolor="#FFFFFF",
        border=thin_border(),
        border_radius=12,
        padding=16,
        margin=ft.Margin(left=8, top=0, right=8, bottom=0),
        on_click=actions.open_recovery,
    )
    return TodayDashboardResult(
        control=ft.Column([macro_card, training_card, meals_card, recovery_card], spacing=TODAY_SECTION_SPACING),
        training_clock=training_subtitle if model.training_clock_active else None,
    )


__all__ = [
    "TodayDashboardActions",
    "TodayDashboardModel",
    "TodayDashboardResult",
    "TODAY_SECTION_SPACING",
    "build_date_toolbar",
    "build_today_dashboard",
]
