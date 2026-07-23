"""Reusable dialog and full-screen form surfaces."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from ui_components import BORDER, GREEN, PRIMARY_SOFT, TEXT, make_button


FORM_HORIZONTAL_PADDING = 16
FORM_BODY_SPACING = 12
FORM_FOOTER_SPACING = 8
FORM_SHEET_CORNER_RADIUS = 22


@dataclass(frozen=True)
class FormViewContext:
    close_control: Callable[[Any], None]
    scroll_mode: Any


def build_dialog(title, content, actions=None, on_close=None):
    """Build the app's compact confirmation/detail dialog."""
    title_row = ft.Row([
        ft.Text(title, size=18, weight="bold", color=TEXT, expand=True),
        ft.IconButton(icon=ft.Icons.CLOSE_ROUNDED, icon_size=20, tooltip="关闭", on_click=on_close),
    ], spacing=6, vertical_alignment="center")
    return ft.AlertDialog(
        title=title_row,
        content=content,
        actions=actions or [],
        actions_alignment=ft.MainAxisAlignment.CENTER,
        bgcolor="#F7FFFFFF",
        barrier_color="#520F1F1A",
    )


def build_full_form_sheet(
    context: FormViewContext,
    title: str,
    controls: Sequence[Any],
    on_save: Callable[[Any], None],
    save_label: str = "保存",
):
    """Build a keyboard-safe, full-height mobile editing surface."""
    sheet = None

    def close_sheet(event=None):
        context.close_control(sheet)

    sheet = ft.BottomSheet(
        content=ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.IconButton(ft.Icons.ARROW_BACK, tooltip="返回", width=48, height=48, on_click=close_sheet),
                        ft.Text(title, size=19, weight="bold", color=TEXT, expand=True),
                        ft.IconButton(ft.Icons.CLOSE, tooltip="关闭", width=48, height=48, on_click=close_sheet),
                    ], spacing=4, vertical_alignment="center"),
                    padding=ft.Padding(left=4, top=4, right=4, bottom=4),
                    border=ft.Border(bottom=ft.BorderSide(width=1, color=BORDER)),
                ),
                ft.Container(
                    content=ft.Column(
                        list(controls),
                        spacing=FORM_BODY_SPACING,
                        scroll=context.scroll_mode,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        expand=True,
                    ),
                    padding=ft.Padding(
                        left=FORM_HORIZONTAL_PADDING,
                        top=14,
                        right=FORM_HORIZONTAL_PADDING,
                        bottom=14,
                    ),
                    expand=True,
                ),
                ft.Container(
                    content=ft.Row([
                        make_button("取消", on_click=close_sheet, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                        make_button(save_label, on_click=on_save, expand=True),
                    ], spacing=FORM_FOOTER_SPACING),
                    padding=ft.Padding(
                        left=FORM_HORIZONTAL_PADDING,
                        top=10,
                        right=FORM_HORIZONTAL_PADDING,
                        bottom=12,
                    ),
                    bgcolor="#FFFFFF",
                    border=ft.Border(top=ft.BorderSide(width=1, color=BORDER)),
                ),
            ], spacing=0, expand=True),
            bgcolor="#FFFFFF",
            border_radius=ft.BorderRadius(
                top_left=FORM_SHEET_CORNER_RADIUS,
                top_right=FORM_SHEET_CORNER_RADIUS,
                bottom_left=0,
                bottom_right=0,
            ),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            expand=True,
        ),
        fullscreen=True,
        use_safe_area=True,
        maintain_bottom_view_insets_padding=True,
        dismissible=False,
        draggable=False,
    )
    return sheet


__all__ = [
    "FORM_BODY_SPACING",
    "FORM_FOOTER_SPACING",
    "FORM_HORIZONTAL_PADDING",
    "FORM_SHEET_CORNER_RADIUS",
    "FormViewContext",
    "build_dialog",
    "build_full_form_sheet",
]
