"""Android rest-permission and training recycle-bin setting panels."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import flet as ft

from ui_components import GREEN, PRIMARY_SOFT, SURFACE, make_button, section_title, small_text


def build_background_rest_panel(
    status: Mapping[str, bool],
    *,
    on_notification: Callable[[Any], None],
    on_exact_alarm: Callable[[Any], None],
    on_overlay: Callable[[Any], None],
) -> ft.Control:
    def marker(key: str) -> str:
        return "已开启" if status.get(key) else "未开启"

    return ft.Container(
        content=ft.Column([
            section_title("后台休息提醒"),
            small_text(
                f"通知：{marker('notification')} · 精确闹钟：{marker('exact_alarm')} · 悬浮窗：{marker('overlay')}"
            ),
            ft.Row([
                make_button("通知", on_click=on_notification, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                make_button("精确闹钟", on_click=on_exact_alarm, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                make_button("悬浮窗", on_click=on_overlay, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
            ], spacing=6),
            small_text("休息时间修改、暂停、继续或跳过时，系统闹钟和悬浮倒计时会同步重排。"),
        ], spacing=8),
        bgcolor=SURFACE,
        border_radius=8,
        padding=12,
    )


def build_training_recycle_panel(
    count: int, on_open: Callable[[Any], None]
) -> ft.Control:
    return ft.Container(
        content=ft.Column([
            section_title("训练回收站"),
            small_text("删除的训练保留 15 天，可恢复到原日期的“当日已练”。"),
            make_button(
                f"打开回收站（{count}）",
                on_click=on_open,
                bgcolor=PRIMARY_SOFT,
                color=GREEN,
                expand=True,
            ),
        ], spacing=8),
        bgcolor=SURFACE,
        border_radius=8,
        padding=12,
    )


__all__ = ["build_background_rest_panel", "build_training_recycle_panel"]
