"""Shared visual primitives for analytics feature views."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from analytics_model import BORDER, PRIMARY, PRIMARY_SOFT, SUB, SURFACE, TEXT, WHITE

def _text(value: Any, *, size: int = 13, color: str = TEXT, weight: str | None = None) -> ft.Text:
    return ft.Text(str(value), size=size, color=color, weight=weight)


def _card(content: ft.Control, *, padding: int = 12) -> ft.Container:
    return ft.Container(content=content, bgcolor=WHITE, border=_border(BORDER), border_radius=8, padding=padding)


def _border(color: str, width: int = 1) -> ft.Border:
    side = ft.BorderSide(width=width, color=color)
    return ft.Border(top=side, right=side, bottom=side, left=side)


def _chip(label: str, selected: bool, on_click: Callable[[Any], None] | None = None) -> ft.Container:
    return ft.Container(
        content=ft.Text(label, size=14, weight="bold", color=WHITE if selected else PRIMARY, text_align="center", max_lines=1, overflow="ellipsis"),
        height=48,
        padding=ft.Padding(left=10, top=0, right=10, bottom=0),
        bgcolor=PRIMARY if selected else PRIMARY_SOFT,
        border=_border(PRIMARY if selected else BORDER),
        border_radius=8,
        alignment=ft.Alignment.CENTER,
        expand=True,
        ink=True,
        on_click=on_click,
    )


def _metric(label: str, value: Any, *, color: str = TEXT) -> ft.Container:
    return ft.Container(
        content=ft.Column([_text(label, size=12, color=SUB, weight="bold"), _text(value, size=18, color=color, weight="bold")], spacing=3),
        bgcolor=SURFACE,
        border=_border(BORDER),
        border_radius=8,
        padding=12,
        expand=True,
    )


def _value_or_empty(value: Any, suffix: str = "") -> str:
    return "无数据" if value is None else f"{value:g}{suffix}" if isinstance(value, (int, float)) else str(value)
