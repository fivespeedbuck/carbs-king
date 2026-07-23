"""Shared visual tokens and reusable Flet controls.

This module owns presentation primitives only. Page modules may depend on it;
it must not import application state, storage, or domain services.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import flet as ft


BG = "#F4F7F6"
CARD = "#FFFFFF"
PRIMARY = "#116E59"
PRIMARY_SOFT = "#F1F7F5"
TEXT = "#182420"
SUB = "#4F5D58"
RED = "#B83A3A"
ORANGE = "#B96A18"
GREEN = "#155A43"
SKY_BLUE = "#277EA8"
BAR_BG = "#E4EAE8"
YELLOW = "#B98518"
BORDER = "#CDD9D5"
SURFACE = "#F7FAF9"
INPUT_LABEL_HEIGHT = 36
INPUT_FIELD_HEIGHT = 52
INPUT_LABEL_SPACING = 4
FIELD_GRID_SPACING = 8
FIELD_GRID_COLLAPSE_WIDTH = 300

_input_focused = False


def set_input_focused(value: bool) -> None:
    global _input_focused
    _input_focused = bool(value)


def input_is_focused() -> bool:
    return _input_focused


class LabeledInput(ft.Column):
    """Keep labels above inputs so they never collide with field borders."""

    def __init__(self, label: str, field: Any, width: int | None = None, expand: bool = False):
        self.label_control = ft.Text(label, size=12, color=SUB, weight="bold", max_lines=2, overflow="ellipsis")
        try:
            if getattr(field, "height", None) is None:
                field.height = INPUT_FIELD_HEIGHT
        except Exception:
            pass
        super().__init__(
            controls=[
                ft.Container(content=self.label_control, height=INPUT_LABEL_HEIGHT, alignment=ft.Alignment.BOTTOM_LEFT),
                field,
            ],
            spacing=INPUT_LABEL_SPACING,
            width=width,
            expand=expand,
        )
        self.field = field

    @property
    def label(self):
        return self.label_control.value

    @label.setter
    def label(self, value):
        self.label_control.value = value

    @property
    def label_text(self):
        return self.label_control.value

    @label_text.setter
    def label_text(self, value):
        self.label_control.value = value

    @property
    def value(self):
        return self.field.value

    @value.setter
    def value(self, value):
        self.field.value = value

    @property
    def on_change(self):
        if hasattr(self.field, "on_select"):
            return self.field.on_select
        return self.field.on_change

    @on_change.setter
    def on_change(self, handler):
        if hasattr(self.field, "on_select"):
            self.field.on_select = handler
        else:
            self.field.on_change = handler

    @property
    def on_blur(self):
        return self.field.on_blur

    @on_blur.setter
    def on_blur(self, handler):
        self.field.on_blur = handler

    @property
    def on_submit(self):
        return self.field.on_submit

    @on_submit.setter
    def on_submit(self, handler):
        self.field.on_submit = handler

    @property
    def options(self):
        return self.field.options

    @options.setter
    def options(self, value):
        self.field.options = value


def thin_border(color: str = BORDER) -> ft.Border:
    side = ft.BorderSide(width=1, color=color)
    return ft.Border(top=side, right=side, bottom=side, left=side)


def make_button(text, on_click=None, icon=None, bgcolor=None, color=None, expand=False, height=48):
    """Readable mobile button with a clear touch target and visible boundary."""
    fg = color or "#FFFFFF"
    bg = bgcolor or PRIMARY
    children = []
    if icon is not None:
        children.append(ft.Icon(icon, size=18, color=fg))
    children.append(ft.Text(text, size=14, weight="bold", color=fg, max_lines=1, overflow="ellipsis"))
    button = ft.Container(
        content=ft.Row(children, alignment="center", spacing=4),
        height=max(48, height),
        padding=ft.Padding(left=10, top=0, right=10, bottom=0),
        bgcolor=bg,
        border=thin_border(PRIMARY if bg == PRIMARY else BORDER),
        border_radius=8,
        ink=True,
        on_click=on_click,
    )
    button.expand = expand
    return button


def card(content, padding=12, margin_bottom=8):
    return ft.Container(
        content=content,
        bgcolor=CARD,
        border=thin_border(),
        border_radius=8,
        padding=padding,
        margin=ft.Margin(left=8, top=0, right=8, bottom=margin_bottom),
    )


def section_title(text):
    return ft.Text(text, size=17, weight="bold", color=TEXT)


def small_text(text, color=SUB):
    return ft.Text(text, size=12, color=color)


def plain_number_field(value="", width=None, keyboard_type=None, on_change=None, expand=False, height=46):
    field = ft.TextField(value=value, width=width, height=height, keyboard_type=keyboard_type)
    try:
        field.text_size = 16
        field.dense = True
        field.border_radius = 8
        field.bgcolor = "#FFFFFF"
        field.border_color = BORDER
        field.focused_border_color = PRIMARY
        field.cursor_color = PRIMARY
        field.content_padding = 12
    except Exception:
        pass
    if on_change:
        field.on_change = on_change
    field.on_focus = lambda e: set_input_focused(True)
    field.on_blur = lambda e: set_input_focused(False)
    if expand:
        field.expand = True
    return field


def labeled_plain_field(label, value="", width=None, keyboard_type=None, expand=False, height=INPUT_FIELD_HEIGHT):
    field = plain_number_field(value=value, width=width, keyboard_type=keyboard_type, expand=expand, height=height)
    label_control = ft.Text(label, size=12, color=SUB, weight="bold", max_lines=2, overflow="ellipsis")
    label_box = ft.Container(content=label_control, height=INPUT_LABEL_HEIGHT, alignment=ft.Alignment.BOTTOM_LEFT)
    box = ft.Column([label_box, field], spacing=INPUT_LABEL_SPACING)
    if expand:
        box.expand = True
    return box, field


def mobile_text_field(
    label,
    value="",
    width=None,
    keyboard_type=None,
    on_change=None,
    on_blur=None,
    on_submit=None,
    expand=False,
    height=INPUT_FIELD_HEIGHT,
    multiline=False,
    min_lines=None,
    max_lines=None,
):
    field = ft.TextField(
        value=value,
        height=height,
        keyboard_type=keyboard_type,
        expand=True,
        multiline=multiline,
        min_lines=min_lines,
        max_lines=max_lines,
    )
    try:
        field.text_size = 16
        field.dense = True
        field.border_radius = 8
        field.bgcolor = "#FFFFFF"
        field.border_color = BORDER
        field.focused_border_color = PRIMARY
        field.cursor_color = PRIMARY
        field.content_padding = 12
    except Exception:
        pass
    if on_change:
        field.on_change = on_change
    field.on_focus = lambda e: set_input_focused(True)

    def handle_blur(event):
        set_input_focused(False)
        if on_blur:
            on_blur(event)

    field.on_blur = handle_blur
    if on_submit:
        field.on_submit = on_submit
    return LabeledInput(label, field, width=width, expand=expand)


def mobile_dropdown(label, value, options, width=None, on_change=None, expand=False):
    dropdown = ft.Dropdown(value=value, options=options, height=INPUT_FIELD_HEIGHT, expand=True)
    try:
        dropdown.text_size = 16
        dropdown.dense = True
        dropdown.border_radius = 8
        dropdown.bgcolor = "#FFFFFF"
        dropdown.border_color = BORDER
        dropdown.focused_border_color = PRIMARY
        dropdown.content_padding = 12
    except Exception:
        pass
    if on_change:
        dropdown.on_select = on_change
    dropdown.on_focus = lambda e: set_input_focused(True)
    dropdown.on_blur = lambda e: set_input_focused(False)
    return LabeledInput(label, dropdown, width=width, expand=expand)


def responsive_field_grid(
    controls: Sequence[Any],
    *,
    columns: int = 2,
    viewport_width: int | float | None = None,
    column_spans: Sequence[int] | None = None,
    full_width: Sequence[int] = (),
    spacing: int = FIELD_GRID_SPACING,
) -> ft.ResponsiveRow:
    """Lay out compact fields without allowing label length to shift field baselines."""
    count = max(1, min(3, int(columns)))
    collapsed = viewport_width is not None and float(viewport_width) < FIELD_GRID_COLLAPSE_WIDTH
    default_span = 12 // count
    full_width_indexes = set(full_width)
    spans = list(column_spans or ())
    cells = []
    for index, control in enumerate(controls):
        requested = spans[index] if index < len(spans) else default_span
        span = 12 if collapsed or index in full_width_indexes else max(1, min(12, int(requested)))
        cells.append(ft.Container(content=control, col={"xs": span, "sm": span, "md": span}))
    return ft.ResponsiveRow(
        cells,
        columns=12,
        spacing=spacing,
        run_spacing=spacing,
        vertical_alignment="start",
    )


def three_field_grid(first: Any, second: Any, third: Any, *, viewport_width=None) -> ft.ResponsiveRow:
    """Shared weight/reps/sets-style three-column field group."""
    return responsive_field_grid([first, second, third], columns=3, viewport_width=viewport_width)


def two_field_grid(first: Any, second: Any, *, viewport_width=None) -> ft.ResponsiveRow:
    """Shared duration/distance and paired nutrition field group."""
    return responsive_field_grid([first, second], columns=2, viewport_width=viewport_width)


def quantity_unit_grid(quantity: Any, unit: Any, *, viewport_width=None, unit_first: bool = False) -> ft.ResponsiveRow:
    """Keep quantity and a compact unit control together, with the unit one-third wide."""
    controls = [unit, quantity] if unit_first else [quantity, unit]
    spans = [4, 8] if unit_first else [8, 4]
    return responsive_field_grid(controls, columns=2, viewport_width=viewport_width, column_spans=spans)


def _to_float(value, default=0.0):
    try:
        if value is None or not str(value).strip():
            return default
        return float(str(value).strip())
    except Exception:
        return default


def custom_progress_bar(label, current, target_text, ratio, color, width=420):
    try:
        ratio = max(0, min(float(ratio), 1))
    except Exception:
        ratio = 0
    width = int(width or 420)
    height = 14
    fill_width = max(0, int(width * ratio))
    return ft.Column([
        ft.Container(
            content=ft.Row([
                ft.Text(label, size=14, color=TEXT, weight="bold"),
                ft.Text(target_text, size=14, color=SUB, weight="bold"),
            ], alignment="spaceBetween"),
            width=width,
        ),
        ft.Container(
            content=ft.Row([
                ft.Container(width=fill_width, height=height, bgcolor=color, border_radius=8),
                ft.Container(width=max(0, width - fill_width), height=height),
            ], spacing=0),
            width=width,
            height=height,
            bgcolor=BAR_BG,
            border_radius=8,
        ),
    ], spacing=6)


def macro_progress_bar(label, current, target_value=None, target_min=None, target_max=None, kind="carb", width=300):
    current = _to_float(current)
    if target_min is not None and target_max is not None:
        min_target = _to_float(target_min)
        max_target = _to_float(target_max)
        target_text = f"{current:g} / {min_target:g}-{max_target:g}g"
        ratio = current / min_target if current < min_target and min_target > 0 else 1
        warn_gap = 20 if kind == "carb" else 25 if kind == "protein" else 10
        color = GREEN if current <= max_target else YELLOW if current <= max_target + warn_gap else RED
        return custom_progress_bar(label, current, target_text, ratio, color, width=width)
    target = _to_float(target_value)
    return custom_progress_bar(
        label,
        current,
        f"{current:g} / {target:g}g",
        current / target if target > 0 else 0,
        GREEN if current <= target else YELLOW,
        width=width,
    )


def water_progress_bar(total_ml, target_ml=2000, width=300):
    total_ml = _to_float(total_ml)
    return custom_progress_bar(
        "饮水进度",
        total_ml,
        f"{int(total_ml)} / {target_ml} ml",
        total_ml / target_ml if target_ml > 0 else 0,
        SKY_BLUE if total_ml >= target_ml else GREEN,
        width=width,
    )


def pill(text, color=PRIMARY):
    return ft.Container(
        content=ft.Text(text, size=13, color=color, weight="bold"),
        bgcolor="#FFFFFF",
        border=thin_border(color),
        border_radius=12,
        padding=6,
    )


__all__ = [
    "BG", "CARD", "PRIMARY", "PRIMARY_SOFT", "TEXT", "SUB", "RED", "ORANGE",
    "GREEN", "SKY_BLUE", "BAR_BG", "YELLOW", "BORDER", "SURFACE",
    "INPUT_LABEL_HEIGHT", "INPUT_FIELD_HEIGHT", "INPUT_LABEL_SPACING",
    "FIELD_GRID_SPACING", "FIELD_GRID_COLLAPSE_WIDTH",
    "LabeledInput", "input_is_focused", "make_button", "thin_border", "card",
    "section_title", "small_text", "labeled_plain_field", "mobile_text_field",
    "mobile_dropdown", "plain_number_field", "responsive_field_grid", "three_field_grid",
    "two_field_grid", "quantity_unit_grid", "custom_progress_bar",
    "macro_progress_bar", "water_progress_bar", "pill",
]
