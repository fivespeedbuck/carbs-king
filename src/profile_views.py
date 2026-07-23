"""Profile-page presentation components."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import flet as ft

from ui_components import BAR_BG, BORDER, GREEN, PRIMARY_SOFT, SUB, TEXT, card, make_button, section_title, small_text, thin_border


TIER_COLORS = {
    "bronze": "#A76D3B",
    "silver": "#73818A",
    "gold": "#B98518",
    "diamond": "#277EA8",
}


def build_achievement_wall(
    results: Sequence[Mapping[str, Any]],
    *,
    expanded: bool,
    on_toggle: Callable[[Any], None],
):
    unlocked_count = sum(1 for item in results if item.get("unlocked"))
    visible = list(results) if expanded else list(results)[:8]
    tiles = []
    for item in visible:
        unlocked = bool(item.get("unlocked"))
        progress = max(0.0, min(1.0, float(item.get("progress") or 0)))
        current = float(item.get("current") or 0)
        target = float(item.get("target") or 0)
        color = TIER_COLORS.get(str(item.get("tier")), "#7157A8" if item.get("hidden") else GREEN)
        tiles.append(ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.EMOJI_EVENTS if unlocked else ft.Icons.LOCK_OUTLINE, size=20, color=color if unlocked else "#98A3A0"),
                    ft.Text(item.get("title", "成就"), size=12, weight="bold", color=TEXT if unlocked else SUB, expand=True, max_lines=1, overflow="ellipsis"),
                ], spacing=6),
                ft.Text(item.get("description", ""), size=12, color=SUB, max_lines=2, overflow="ellipsis"),
                ft.ProgressBar(value=progress, color=color, bgcolor=BAR_BG, height=5),
                small_text("已解锁" if unlocked else f"{current:g} / {target:g}"),
            ], spacing=5),
            bgcolor="#F9FBFA" if not unlocked else "#FFF9EB",
            border=thin_border(color if unlocked else BORDER),
            border_radius=8,
            height=116,
            expand=True,
            padding=9,
        ))
    rows = [ft.Row(tiles[index:index + 2], spacing=8) for index in range(0, len(tiles), 2)]
    return card(ft.Column([
        ft.Row([
            section_title("成就系统"),
            ft.Text(f"{unlocked_count} / {len(results)}", size=12, weight="bold", color=GREEN),
        ], alignment="spaceBetween"),
        small_text("48 项阶梯成就 · 8 项隐藏成就 · 真实数据计算"),
        *rows,
        make_button("收起" if expanded else "查看全部成就", on_click=on_toggle, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
    ], spacing=9), padding=14)


__all__ = ["TIER_COLORS", "build_achievement_wall"]
