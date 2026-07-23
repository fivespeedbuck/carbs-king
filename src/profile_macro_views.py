"""Macro-mode summary controls for the profile feature."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from ui_components import GREEN, PRIMARY, PRIMARY_SOFT, make_button, section_title, small_text


def build_macro_panel(
    rows: Sequence[ft.Control],
    *,
    auto_selected: bool,
    on_edit: Callable[[Any], None],
    on_mode_change: Callable[[str], None],
) -> ft.Control:
    return ft.Container(
        content=ft.Column([
            ft.Row([
                section_title("宏量目标计算"),
                make_button("编辑自定义倍数", on_click=on_edit, bgcolor=PRIMARY_SOFT, color=GREEN)
                if not auto_selected else ft.Container(width=0),
            ], alignment="spaceBetween"),
            ft.Row([
                make_button("自动计算", on_click=lambda e: on_mode_change("auto"), bgcolor=PRIMARY if auto_selected else PRIMARY_SOFT, color="#FFFFFF" if auto_selected else GREEN, expand=True),
                make_button("自定义", on_click=lambda e: on_mode_change("custom"), bgcolor=PRIMARY if not auto_selected else PRIMARY_SOFT, color="#FFFFFF" if not auto_selected else GREEN, expand=True),
            ], spacing=8),
            *rows,
            small_text(
                "当前显示自动计算倍率，仅供查看。" if auto_selected
                else "当前显示自定义倍率，可点击右上角编辑。"
            ),
        ], spacing=7),
        bgcolor="#F8FAFC",
        border_radius=8,
        padding=12,
    )


__all__ = ["build_macro_panel"]
