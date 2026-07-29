"""User-selectable semantic theme colors."""

from __future__ import annotations

from collections.abc import Mapping

import flet as ft


THEME_OPTIONS: Mapping[str, Mapping[str, str]] = {
    # Green is the original application palette. The other themes keep the
    # same dark-primary / pale-container / dark-container-text relationship.
    "green": {"primary": "#2A806B", "soft": "#F1F7F5", "soft_text": "#19634F"},
    "purple": {"primary": "#8464C2", "soft": "#F5F1FA", "soft_text": "#664A9A"},
    "blue": {"primary": "#438BD1", "soft": "#EEF5FC", "soft_text": "#2E6FA9"},
    "yellow": {"primary": "#C4932E", "soft": "#FBF5E9", "soft_text": "#8A671C"},
}
DEFAULT_THEME = "green"


def normalize_theme(value: object) -> str:
    key = str(value or "").strip().lower()
    return key if key in THEME_OPTIONS else DEFAULT_THEME


def apply_theme(page: ft.Page, value: object) -> str:
    key = normalize_theme(value)
    palette = THEME_OPTIONS[key]
    theme = getattr(page, "theme", None)
    if theme is None:
        theme = ft.Theme()
    theme.color_scheme_seed = None
    theme.color_scheme = ft.ColorScheme(
        primary=palette["primary"],
        on_primary="#FFFFFF",
        primary_container=palette["soft"],
        on_primary_container=palette["soft_text"],
        surface="#FFFFFF",
        on_surface="#182420",
        on_surface_variant="#4F5D58",
        outline="#CDD9D5",
        outline_variant="#CDD9D5",
        surface_tint="#FFFFFF",
        surface_container="#FFFFFF",
        surface_container_low="#F7F8F8",
        surface_container_lowest="#F4F7F6",
    )
    page.theme = theme
    return key


__all__ = ["DEFAULT_THEME", "THEME_OPTIONS", "apply_theme", "normalize_theme"]
