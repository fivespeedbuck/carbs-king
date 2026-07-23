"""Full backup controls for the profile feature."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from ui_components import GREEN, PRIMARY_SOFT, RED, make_button, section_title, small_text


def build_backup_panel(
    export_handler: Callable[[str], Callable[[Any], None]],
    import_handler: Callable[[Any], None],
    clear_personal_data: Callable[[Any], None],
) -> ft.Control:
    return ft.Container(
        content=ft.Column([
            section_title("备份与恢复"),
            make_button(
                "全量导出",
                on_click=export_handler("all"),
                icon=ft.Icons.DOWNLOAD,
                expand=True,
            ),
            make_button(
                "全量导入",
                on_click=import_handler,
                icon=ft.Icons.UPLOAD_FILE,
                bgcolor=PRIMARY_SOFT,
                color=GREEN,
                expand=True,
            ),
            small_text("全量备份包含个人资料、每日记录、食物、补剂、训练数据和成就。"),
            make_button(
                "清除个人数据",
                on_click=clear_personal_data,
                icon=ft.Icons.DELETE_OUTLINE,
                bgcolor="#FFFFFF",
                color=RED,
                expand=True,
            ),
            small_text("清除个人记录，但保留食物库、补剂库和动作库。"),
        ], spacing=8),
        bgcolor="#F8FAFC",
        border_radius=8,
        padding=12,
    )


__all__ = ["build_backup_panel"]
