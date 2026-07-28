"""Profile-page presentation components."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import flet as ft

from ui_components import BAR_BG, BORDER, GREEN, PRIMARY, PRIMARY_SOFT, SUB, TEXT, YELLOW, card, make_button, section_title, small_text, thin_border

from goal_challenge_definitions import LANE_LABELS, LANES, level_info


TIER_COLORS = {
    "bronze": "#A76D3B",
    "silver": "#73818A",
    "gold": "#B98518",
    "diamond": "#277EA8",
}


def _challenge_color(item):
    return str(item.get("level_color") or YELLOW)


def _challenge_text(item):
    current = float(item.get("current", 0) or 0)
    target = float(item.get("target", 0) or 0)
    unit = str(item.get("unit") or "")
    percent = float(item.get("progress_percent", 0) or 0)
    return f"{current:g} / {target:g} {unit} · {percent:g}%"


def _challenge_card(item, *, delete_mode=False, selected=False, on_select=None):
    color = _challenge_color(item)
    leading = ft.Container(
        content=ft.Icon(
            ft.Icons.CHECK_CIRCLE_OUTLINE if selected else ft.Icons.RADIO_BUTTON_UNCHECKED,
            color=PRIMARY if selected else SUB,
            size=22,
        ),
        width=28,
        on_click=(lambda event: on_select(item.get("id")) if on_select else None),
    ) if delete_mode else ft.Icon(ft.Icons.FLAG_ROUNDED, size=22, color=color)
    end = ft.Text(str(item.get("level_name") or "自定义"), size=11, color=color, weight="bold")
    content = ft.Column([
        ft.Row([leading, ft.Text(str(item.get("title") or "目标挑战"), size=14, weight="bold", color=TEXT, expand=True, max_lines=1, overflow="ellipsis"), end], spacing=6),
        small_text(f"所属赛道：{LANE_LABELS.get(str(item.get('lane') or ''), '未分类')}", color=GREEN),
        small_text(_challenge_text(item)),
        ft.ProgressBar(value=max(0, min(1, float(item.get("progress_percent", 0) or 0) / 100)), color=color, bgcolor=BAR_BG, height=6),
        small_text(
            f"{item.get('start_date', '')} 至 {item.get('end_date', '')}"
            if item.get("start_date") or item.get("end_date") else "持续记录中",
        ),
    ], spacing=6)
    return ft.Container(content=content, padding=10, margin=ft.Margin(left=0, top=0, right=0, bottom=8), bgcolor="#FFFDF7" if color == YELLOW else "#F9FBFA", border=thin_border(color), border_radius=8)


def build_goal_challenge_panel(
    active,
    *,
    on_new,
    on_completed,
    on_delete_toggle,
    delete_mode=False,
    selected_ids=None,
    on_select=None,
    on_delete_confirm=None,
):
    selected_ids = set(selected_ids or ())
    active_cards = [
        _challenge_card(item, delete_mode=delete_mode, selected=item.get("id") in selected_ids, on_select=on_select)
        for item in active if isinstance(item, Mapping)
    ]
    if not active_cards:
        active_cards = [ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=22, color=PRIMARY),
                small_text("还没有进行中的挑战，点击开始创建"),
            ], horizontal_alignment="center", spacing=6),
            padding=14,
            bgcolor="#F9FBFA",
            border=thin_border(BORDER),
            border_radius=8,
            on_click=on_new,
        )]
    footer = []
    if delete_mode:
        footer = [
            small_text(f"已选择 {len(selected_ids)} 项"),
            make_button(
                f"删除已选（{len(selected_ids)}）",
                on_click=on_delete_confirm,
                bgcolor="#FCECEC" if selected_ids else PRIMARY_SOFT,
                color="#B83A3A" if selected_ids else SUB,
                expand=True,
            ),
        ]
    return card(ft.Column([
        ft.Row([
            ft.Column([section_title("目标挑战"), small_text("设定目标，持续推进")], spacing=2, expand=True),
            ft.IconButton(icon=ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="新建挑战", on_click=on_new),
            ft.IconButton(icon=ft.Icons.HISTORY, tooltip="已完成挑战", on_click=on_completed),
            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE if not delete_mode else ft.Icons.CLOSE, tooltip="删除挑战" if not delete_mode else "退出删除", on_click=on_delete_toggle),
        ], spacing=0, vertical_alignment="center"),
        small_text(f"进行中 {len(active_cards) if active else 0} / 3 项挑战" if active else "开始你的第一项目标挑战", color=GREEN),
        *active_cards,
        *footer,
    ], spacing=8), padding=14)


def build_completed_challenges(items, *, on_close, content_width=304):
    rows = []
    for item in items:
        rows.append(_challenge_card(item))
        rows.append(small_text(f"完成于 {item.get('completed_at', '—')} · 最终进度 {_challenge_text(item)}"))
    if not rows:
        rows = [small_text("还没有已完成挑战，完成后会在这里保留记录。")]
    return ft.AlertDialog(
        title=ft.Row([ft.Text("已完成挑战", size=18, weight="bold", color=TEXT, expand=True), ft.IconButton(icon=ft.Icons.CLOSE, on_click=on_close)]),
        content=ft.Container(
            content=ft.Column(rows, scroll=ft.ScrollMode.HIDDEN, spacing=4),
            width=max(260, min(312, int(content_width or 304))),
            height=520,
        ),
        bgcolor="#FFFFFF",
    )


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


__all__ = [
    "TIER_COLORS", "build_achievement_wall", "build_completed_challenges",
    "build_goal_challenge_panel",
]
