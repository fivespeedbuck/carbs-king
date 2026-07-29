"""Compact theme selector used in the profile surfaces."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from theme_service import THEME_OPTIONS, normalize_theme
from ui_components import BORDER, SURFACE, page_card, section_title


def build_theme_panel(current: str, on_change: Callable[[str], None]) -> ft.Control:
    selected = normalize_theme(current)
    swatches = []
    for key, option in THEME_OPTIONS.items():
        active = key == selected
        swatches.append(ft.Container(
            width=52,
            height=44,
            bgcolor=option["primary"],
            border=ft.Border.all(3 if active else 1, option["primary"] if active else BORDER),
            border_radius=10,
            ink=True,
            on_click=lambda e, value=key: on_change(value),
        ))
    return page_card(
        ft.Column([
            section_title("主题色"),
            ft.Row(swatches, spacing=8, alignment="spaceBetween"),
        ], spacing=8),
        padding=12,
        margin_bottom=8,
    )


__all__ = ["build_theme_panel"]
