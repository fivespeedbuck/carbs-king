"""Compact application update panel for profile settings."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from ui_components import GREEN, PRIMARY_SOFT, SURFACE, make_button, section_title, small_text


def build_update_panel(
    *,
    current_version: str,
    current_build: int,
    status: str,
    latest: dict[str, Any] | None,
    error: str = "",
    on_check: Callable[[Any], None],
    on_download: Callable[[Any], None],
    on_install: Callable[[Any], None] | None = None,
    downloaded_bytes: int = 0,
    total_bytes: int = 0,
) -> ft.Control:
    release = latest if isinstance(latest, dict) else {}
    latest_build = release.get("build")
    if status == "checking":
        message = "正在检查 GitHub Release…"
    elif status == "available":
        message = f"发现 Build {latest_build}，可下载安装"
    elif status == "downloading":
        percent = int(downloaded_bytes * 100 / total_bytes) if total_bytes else 0
        message = f"正在下载 {downloaded_bytes / 1024 / 1024:.1f} MB / {total_bytes / 1024 / 1024:.1f} MB（{percent}%）" if total_bytes else f"正在下载 {downloaded_bytes / 1024 / 1024:.1f} MB"
    elif status == "downloaded":
        message = "下载完成，等待打开系统安装界面"
    elif status == "installing":
        message = "已打开系统安装界面，请确认手动更新"
    elif status == "install_permission":
        message = "请先允许本应用安装未知来源应用，再点“打开安装界面”"
    elif status == "current":
        message = "当前已是最新版本"
    elif status == "error":
        message = error or "暂时无法连接 GitHub，请稍后重试"
    else:
        message = "进入此页面时自动检查，也可以手动重试"

    buttons = [
        make_button(
            "重新检查" if status in {"current", "available", "error"} else "检查更新",
            on_click=on_check,
            bgcolor=PRIMARY_SOFT,
            color=GREEN,
            expand=True,
        )
    ]
    if status == "available" and release.get("apk_url"):
        buttons.append(make_button(f"下载 Build {latest_build}", on_click=on_download, expand=True))
    elif status == "downloading":
        buttons.append(make_button("正在下载…", bgcolor=PRIMARY_SOFT, color=GREEN, expand=True))
    elif status in {"downloaded", "install_permission"} and on_install is not None:
        buttons.append(make_button("打开安装界面", on_click=on_install, expand=True))

    content = [
        section_title("应用更新"),
        small_text(f"当前版本 {current_version} · Build {current_build}"),
        small_text(message),
    ]
    if status == "downloading":
        content.append(ft.ProgressBar(
            value=(downloaded_bytes / total_bytes) if total_bytes else None,
            color=GREEN,
            bgcolor=PRIMARY_SOFT,
        ))
    content.append(ft.Row(buttons, spacing=8))

    return ft.Container(
        content=ft.Column(content, spacing=8),
        bgcolor=SURFACE,
        border=None,
        border_radius=8,
        padding=12,
    )


__all__ = ["build_update_panel"]
