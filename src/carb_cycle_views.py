"""Shared intake detail for Today and Diet entry points."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import flet as ft

from ui_components import TEXT, page_card, section_title, small_text


def build_intake_detail_content(
    total: Mapping[str, Any], targets: Mapping[str, Any], snapshot: Mapping[str, Any] | None = None
) -> ft.Control:
    ready = bool(targets.get("is_ready", True))
    target_line = (
        f"碳水 {targets.get('carb_min'):g}–{targets.get('carb_max'):g}g · "
        f"蛋白 {targets.get('protein_min'):g}–{targets.get('protein_max'):g}g · "
        f"脂肪 {targets.get('fat_min'):g}–{targets.get('fat_max'):g}g"
        if ready else str(targets.get("profile_message") or "请先完善个人资料")
    )
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    projection = snapshot.get("ui_projection") if isinstance(snapshot.get("ui_projection"), Mapping) else {}
    status = str(projection.get("status") or "")
    difference = projection.get("recommended_difference")
    if targets.get("macro_mode") == "custom":
        reminder = "当前使用自定义宏量目标，自动碳循环不会修改你的设置。"
    elif status == "manual" and difference:
        reminder = f"当前使用手动目标；根据已确认的训练计划，系统建议{difference}。"
    elif status == "manual":
        reminder = "当前使用手动目标，系统不会自动覆盖。"
    elif status == "provisional":
        reminder = "动作、组数和负重确认后，今日目标会自动更新。"
    else:
        reminder = "今日目标已根据已确认的训练内容更新。"
    return ft.Column([
        page_card(ft.Column([
            section_title("今日摄入"),
            ft.Text(f"{float(total.get('kcal') or 0):g} kcal", size=32, weight="bold", color=TEXT),
            small_text(target_line),
            small_text(
                f"已摄入：碳 {float(total.get('carb') or 0):g}g · "
                f"蛋白 {float(total.get('protein') or 0):g}g · 脂肪 {float(total.get('fat') or 0):g}g"
            ),
        ], spacing=7), padding=14),
        small_text(reminder),
    ], spacing=8, scroll=ft.ScrollMode.HIDDEN)


__all__ = ["build_intake_detail_content"]
