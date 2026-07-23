"""Backup feature controller for full export and full restore."""

from __future__ import annotations

import datetime
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import flet as ft

from backup_service import BackupService
from controller_runtime import ControllerRuntime
from form_views import build_dialog
from repositories import AppRepositories
from ui_components import RED, SUB, TEXT, make_button, small_text


@dataclass(frozen=True)
class BackupControllerDependencies:
    service: BackupService
    repositories: AppRepositories
    runtime: ControllerRuntime
    file_picker: Any
    app_version: str
    page_is_mobile: Callable[[], bool]
    load_profile: Callable[[], dict[str, Any]]


@dataclass
class BackupController:
    import_backup: Callable[..., Any]
    export_handler: Callable[[str], Callable[..., Any]]
    clear_personal_data: Callable[..., Any]


def create_backup_controller(deps: BackupControllerDependencies) -> BackupController:
    service = deps.service
    runtime = deps.runtime
    page = runtime.page
    snack = runtime.snack
    open_control = runtime.open_control
    close_control = runtime.close_control
    responsive_width = runtime.responsive_width
    file_picker = deps.file_picker

    def open_import_confirmation(file_name: str, import_data: dict[str, Any]) -> None:
        dlg = None
        summary = service.summarize(import_data)

        def confirm(event=None):
            try:
                close_control(dlg)
                service.apply(import_data, "replace")
                snack(f"全量导入完成：{summary}")
            except Exception as ex:
                snack(str(ex)[:80])

        dialog_width = responsive_width()
        content = ft.Column([
            ft.Text(file_name, size=13, weight="bold", color=TEXT),
            small_text(summary),
            ft.Container(
                content=small_text(
                    "导入会完整替换当前数据。系统会先自动保存安全快照；若导入失败，将恢复导入前的数据。"
                ),
                bgcolor="#FFF7ED",
                border_radius=8,
                padding=10,
            ),
        ], width=dialog_width, spacing=10, tight=True)
        actions = ft.Row([
            make_button(
                "取消", on_click=lambda event: close_control(dlg),
                bgcolor="#F1F1F1", color=SUB, expand=True,
            ),
            make_button("全量导入", on_click=confirm, expand=True),
        ], spacing=8)
        dlg = build_dialog(
            "确认全量导入",
            content,
            [ft.Container(content=actions, width=dialog_width)],
            on_close=lambda event: close_control(dlg),
        )
        open_control(dlg)

    async def import_backup_handler(event=None):
        try:
            selected_files = await file_picker.pick_files(
                dialog_title="选择碳水大王全量备份",
                allow_multiple=False,
                with_data=True,
            )
            if not selected_files:
                return
            selected = selected_files[0]
            raw = getattr(selected, "bytes", None)
            if not raw:
                selected_path = getattr(selected, "path", None)
                if selected_path and "://" not in str(selected_path):
                    raw = Path(str(selected_path)).read_bytes()
            if not raw:
                raise ValueError("无法读取所选文件")
            payload = json.loads(raw.decode("utf-8-sig"))
            import_data = service.normalize_payload(payload)
            service.validate_full(import_data)
            open_import_confirmation(getattr(selected, "name", "全量备份"), import_data)
        except json.JSONDecodeError:
            snack("导入失败：所选文件不是有效的 JSON 备份")
        except Exception as ex:
            snack(f"导入失败：{str(ex)[:60]}")

    def export_handler(export_kind: str = "all"):
        async def handler(event=None):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            payload = service.build_payload()
            raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8-sig")
            try:
                selected_path = await file_picker.save_file(
                    dialog_title="导出全量备份",
                    file_name=f"carbs_king_full_backup_{timestamp}.json",
                    src_bytes=raw,
                )
                # Desktop returns a path; mobile saves src_bytes through the picker.
                if selected_path and not deps.page_is_mobile() and not getattr(page, "web", False):
                    output_path = Path(str(selected_path))
                    if not output_path.exists() or output_path.stat().st_size == 0:
                        output_path.write_bytes(raw)
                if selected_path:
                    snack("全量备份已导出")
            except Exception as ex:
                snack(f"导出失败：{str(ex)[:60]}")

        return handler

    def clear_personal_data_handler(event=None):
        first_dlg = None

        def open_final_confirmation(event=None):
            close_control(first_dlg)
            final_dlg = None

            def confirm_clear(event=None):
                try:
                    close_control(final_dlg)
                    result = service.clear_personal_data()
                    snack(f"个人数据已清除，共删除 {result['record_days']} 天记录")
                    runtime.refresh()
                except Exception as ex:
                    snack(str(ex)[:80])

            dialog_width = responsive_width()
            final_actions = ft.Row([
                make_button(
                    "取消",
                    on_click=lambda event: close_control(final_dlg),
                    bgcolor="#F1F1F1",
                    color=SUB,
                    expand=True,
                ),
                make_button("确认清除", on_click=confirm_clear, bgcolor=RED, expand=True),
            ], spacing=8)
            final_dlg = build_dialog(
                "再次确认清除",
                ft.Column([
                    ft.Text("此操作不可撤销", size=15, weight="bold", color=RED),
                    small_text("个人资料、饮食记录、身体记录、训练记录和成就将永久删除。"),
                    small_text("食物库、补剂库和动作库仍会保留。"),
                ], width=dialog_width, spacing=8, tight=True),
                [ft.Container(content=final_actions, width=dialog_width)],
                on_close=lambda event: close_control(final_dlg),
            )
            open_control(final_dlg)

        dialog_width = responsive_width()
        first_actions = ft.Row([
            make_button(
                "取消",
                on_click=lambda event: close_control(first_dlg),
                bgcolor="#F1F1F1",
                color=SUB,
                expand=True,
            ),
            make_button("继续", on_click=open_final_confirmation, bgcolor=RED, expand=True),
        ], spacing=8)
        first_dlg = build_dialog(
            "清除个人数据",
            ft.Column([
                small_text("将清除当前训练信息、饮食记录、围度与身体记录、个人资料和其他个人记录。"),
                small_text("食物库、补剂库和动作库不受影响。"),
            ], width=dialog_width, spacing=8, tight=True),
            [ft.Container(content=first_actions, width=dialog_width)],
            on_close=lambda event: close_control(first_dlg),
        )
        open_control(first_dlg)

    return BackupController(
        import_backup=import_backup_handler,
        export_handler=export_handler,
        clear_personal_data=clear_personal_data_handler,
    )


__all__ = ["BackupController", "BackupControllerDependencies", "create_backup_controller"]
