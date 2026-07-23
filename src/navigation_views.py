"""Bottom navigation and horizontal page-swipe coordination."""

from __future__ import annotations

from collections.abc import Callable
import flet as ft

from ui_components import BORDER, PRIMARY, SUB


NAV_ITEMS = (
    ("today", "今日", ft.Icons.TODAY),
    ("training", "训练", ft.Icons.FITNESS_CENTER),
    ("diet", "饮食", ft.Icons.RESTAURANT_MENU),
    ("data", "数据", ft.Icons.INSERT_CHART_OUTLINED),
    ("me", "我", ft.Icons.PERSON_OUTLINE),
)


def build_bottom_navigation(current_view: str, on_select: Callable[[str], None], hide: bool = False):
    if hide:
        return ft.Container(height=0)
    tabs = []
    for key, label, icon in NAV_ITEMS:
        selected = (
            current_view == key
            or (key == "today" and current_view == "daily_details")
            or (key == "diet" and current_view in {"foods", "supplements"})
        )
        tabs.append(ft.Container(
            content=ft.Column([
                ft.Icon(icon, size=22, color=PRIMARY if selected else SUB),
                ft.Text(label, size=12, color=PRIMARY if selected else SUB, weight="bold" if selected else "normal"),
            ], horizontal_alignment="center", spacing=2),
            on_click=lambda e, target=key: on_select(target),
            expand=True,
            padding=6,
            bgcolor="#F7FFFFFF",
        ))
    return ft.Container(
        content=ft.Row(tabs, spacing=0, alignment="spaceAround"),
        padding=6,
        bgcolor="#F7FFFFFF",
        border=ft.Border(top=ft.BorderSide(width=1, color=BORDER)),
    )

__all__ = ["NAV_ITEMS", "build_bottom_navigation"]
