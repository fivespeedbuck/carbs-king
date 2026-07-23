"""Pure presentation helpers for achievement results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import flet as ft

from ui_components import BORDER, GREEN, PRIMARY, PRIMARY_SOFT, SUB, TEXT, make_button, thin_border


HIDDEN_LOCKED_TITLE = "隐藏成就"
HIDDEN_LOCKED_DESCRIPTION = "达成条件后揭晓"


def achievement_view_model(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a UI-safe achievement payload, masking locked hidden entries."""
    item = dict(result)
    locked_hidden = bool(item.get("hidden")) and not bool(item.get("unlocked"))
    item["revealed"] = not locked_hidden
    if locked_hidden:
        item["title"] = HIDDEN_LOCKED_TITLE
        item["description"] = HIDDEN_LOCKED_DESCRIPTION
    return item


def achievement_view_models(results: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
    return [achievement_view_model(item) for item in results]


def sort_achievement_views(
    results: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    unlock_times: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Sort by attention while preserving stable definition order for ties."""
    times = unlock_times if isinstance(unlock_times, Mapping) else {}
    indexed = list(enumerate(results))

    def key(entry: tuple[int, Mapping[str, Any]]) -> tuple[Any, ...]:
        index, item = entry
        current = max(0.0, float(item.get("current") or 0))
        target = max(0.0, float(item.get("target") or 0))
        unlocked = bool(item.get("unlocked")) or (target > 0 and current >= target)
        if not unlocked and current > 0 and target > 0:
            return (0, -(current / target), target - current, index)
        if unlocked:
            unlocked_at = str(item.get("unlocked_at") or times.get(str(item.get("id") or "")) or "")
            return (1, 0 if unlocked_at else 1, "".join(chr(0x10FFFF - ord(ch)) for ch in unlocked_at), index)
        return (2, index)

    return [achievement_view_model(item) for _, item in sorted(indexed, key=key)]


def build_achievement_celebration(
    achievement: Mapping[str, Any],
    *,
    on_confirm,
    on_dismiss=None,
) -> ft.AlertDialog:
    """Build a compact mobile celebration card for one newly unlocked achievement."""
    title = str(achievement.get("title") or "新成就")
    description = str(achievement.get("description") or "完成了一项新的挑战。")
    content = ft.Container(
        width=286,
        content=ft.Column([
            ft.Container(
                content=ft.Icon(ft.Icons.EMOJI_EVENTS_ROUNDED, size=42, color="#FFFFFF"),
                width=68,
                height=68,
                alignment=ft.Alignment.CENTER,
                bgcolor=PRIMARY,
                border_radius=8,
                border=thin_border(PRIMARY),
            ),
            ft.Text("成就达成", size=14, weight="bold", color=GREEN),
            ft.Text(title, size=24, weight="bold", color=TEXT, text_align="center"),
            ft.Container(
                content=ft.Column([
                    ft.Text("达成条件", size=12, weight="bold", color=SUB),
                    ft.Text(description, size=14, color=TEXT, text_align="center"),
                ], spacing=5, horizontal_alignment="center"),
                bgcolor=PRIMARY_SOFT,
                border=thin_border(BORDER),
                border_radius=8,
                padding=12,
            ),
            ft.Text(
                "这是你认真训练和持续记录换来的成果。继续保持，下一枚也不远了。",
                size=13,
                color=SUB,
                text_align="center",
            ),
            ft.Container(
                content=make_button(
                    "收下成就",
                    on_click=on_confirm,
                    icon=ft.Icons.CHECK_CIRCLE_ROUNDED,
                ),
                width=286,
            ),
        ], spacing=10, horizontal_alignment="center", tight=True),
    )
    return ft.AlertDialog(
        modal=True,
        content=content,
        bgcolor="#FFFFFF",
        barrier_color="#660F1F1A",
        inset_padding=18,
        on_dismiss=on_dismiss,
    )


__all__ = [
    "HIDDEN_LOCKED_DESCRIPTION",
    "HIDDEN_LOCKED_TITLE",
    "achievement_view_model",
    "achievement_view_models",
    "build_achievement_celebration",
    "sort_achievement_views",
]
