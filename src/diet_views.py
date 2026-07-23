"""Reusable Flet controls for the diet information architecture."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from diet_service import DIET_VIEW_LABELS, DIET_VIEWS, DietView, DietViewState, normalize_diet_view
from ui_components import INPUT_FIELD_HEIGHT, INPUT_LABEL_HEIGHT, INPUT_LABEL_SPACING, LabeledInput


DIET_TAB_HEIGHT = 48
DIET_INPUT_LABEL_HEIGHT = INPUT_LABEL_HEIGHT
DIET_INPUT_FIELD_HEIGHT = INPUT_FIELD_HEIGHT
DIET_INPUT_SPACING = INPUT_LABEL_SPACING

PRIMARY = "#116E59"
PRIMARY_SOFT = "#F1F7F5"
BORDER = "#CDD9D5"
TEXT = "#182420"
SUB = "#4F5D58"


@dataclass(frozen=True, slots=True)
class DietShellRenderers:
    today_diet: Callable[[], Any]
    food_library: Callable[[], Any]

    def render(self, view: DietView) -> Any:
        return {
            "today_diet": self.today_diet,
            "food_library": self.food_library,
        }[view]()


def _thin_border(color: str) -> ft.Border:
    side = ft.BorderSide(width=1, color=color)
    return ft.Border(top=side, right=side, bottom=side, left=side)


def diet_tab_button(
    view: DietView,
    state: DietViewState,
    on_select: Callable[[DietView], Any],
) -> ft.Container:
    selected = state.active_view == view
    return ft.Container(
        content=ft.Text(
            DIET_VIEW_LABELS[view],
            size=14,
            weight="bold",
            color="#FFFFFF" if selected else PRIMARY,
            text_align="center",
            max_lines=1,
            overflow="ellipsis",
        ),
        height=DIET_TAB_HEIGHT,
        alignment=ft.Alignment.CENTER,
        padding=6,
        border_radius=8,
        border=_thin_border(PRIMARY if selected else BORDER),
        bgcolor=PRIMARY if selected else PRIMARY_SOFT,
        expand=True,
        on_click=lambda event, target=view: on_select(target),
    )


def diet_tabs(state: DietViewState, on_select: Callable[[DietView], Any]) -> ft.Row:
    return ft.Row(
        [diet_tab_button(view, state, on_select) for view in DIET_VIEWS],
        spacing=6,
        vertical_alignment="center",
    )


def fixed_labeled_input(label: str, field: Any, *, width: int | None = None, expand: bool = False) -> ft.Column:
    """Keep labels outside fields; callers should pass bare TextField/Dropdown controls."""

    try:
        field.height = getattr(field, "height", None) or DIET_INPUT_FIELD_HEIGHT
        field.expand = getattr(field, "expand", False) or expand
    except Exception:
        pass

    return LabeledInput(label, field, width=width, expand=expand)


def aligned_input_row(controls: list[Any], *, spacing: int = 8) -> ft.Row:
    return ft.Row(controls, spacing=spacing, vertical_alignment="start")


def diet_shortcut_panel(tabs: Any, shortcut_list: Any) -> ft.Column:
    """Keep shortcut navigation and its results together at the top of food entry."""
    return ft.Column(
        [tabs, shortcut_list],
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        tight=True,
    )


def build_diet_shell(
    state: DietViewState,
    renderers: DietShellRenderers,
    on_select: Callable[[DietView], Any],
) -> ft.Column:
    active_view = normalize_diet_view(state.active_view)
    normalized_state = DietViewState(active_view)
    return ft.Column(
        [
            diet_tabs(normalized_state, on_select),
            renderers.render(active_view),
        ],
        spacing=10,
    )
