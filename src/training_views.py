"""Training-page presentation components.

Session mutation and persistence remain in services/main coordination. This
module owns the active-workout visual tree and emits only user intents.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from ui_components import PRIMARY, make_button, small_text, thin_border


@dataclass(frozen=True)
class ActiveTrainingModel:
    completed_sets: int
    planned_sets: int
    progress: float
    elapsed_text: str
    rest_status: str
    rest_seconds: int
    exercise_name: str
    exercise_index: int
    exercise_count: int
    sets_completed: Sequence[bool]
    selected_set_index: int
    weight_text: str
    reps: int
    selected_set_done: bool
    recording_mode: str = "strength"
    duration_seconds: int = 0
    distance_text: str = ""
    distance_enabled: bool = False
    cardio_metrics: Sequence[tuple[str, str, str]] = ()
    group_label: str = ""
    group_position_text: str = ""
    group_members: Sequence[tuple[str, str, bool, bool]] = ()
    next_work_text: str = ""
    confirm_complete: bool = False
    viewport_height: float = 860.0


@dataclass(frozen=True)
class ActiveTrainingActions:
    close: Callable[[Any], None]
    finish: Callable[[Any], None]
    select_set: Callable[[int], None]
    adjust_rest: Callable[[int], None]
    toggle_rest: Callable[[Any], None]
    skip_rest: Callable[[Any], None]
    adjust_weight: Callable[[int], None]
    edit_weight: Callable[[Any], None]
    adjust_reps: Callable[[int], None]
    edit_duration: Callable[[Any], None]
    edit_distance: Callable[[Any], None]
    edit_metric: Callable[[str, str], None]
    complete_or_undo: Callable[[Any], None]
    ask_complete: Callable[[Any], None]
    cancel_complete: Callable[[Any], None]
    move_exercise: Callable[[int], None]


@dataclass(frozen=True)
class ActiveTrainingResult:
    control: ft.Control
    elapsed_control: ft.Text
    rest_control: ft.Text


def _segmented_progress(value: float, planned_work_items: int) -> ft.Container:
    work_items = max(0, int(planned_work_items or 0))
    track = ft.ProgressBar(value=max(0.0, min(1.0, float(value or 0))), color="#21A366", bgcolor="#31413C", height=8)
    overlays: list[ft.Control] = [track]
    if work_items > 1:
        overlays.append(ft.Row([
            ft.Container(
                expand=True,
                height=8,
                border=ft.Border(right=ft.BorderSide(width=1, color="#DCE9E4")) if index < work_items - 1 else None,
            )
            for index in range(work_items)
        ], spacing=0, height=8))
    return ft.Container(
        content=ft.Stack(overlays, height=8, clip_behavior=ft.ClipBehavior.HARD_EDGE),
        height=8,
        border_radius=4,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )


def build_active_training(model: ActiveTrainingModel, actions: ActiveTrainingActions) -> ActiveTrainingResult:
    compact = float(model.viewport_height or 0) < 820
    surface_padding = 8 if compact else 12
    surface_spacing = 8 if compact else 12
    card_padding = 12 if compact else 16
    card_spacing = 8 if compact else 12
    primary_button_height = 52 if compact else 64
    elapsed = ft.Text(model.elapsed_text, size=42 if compact else 50, weight="bold", color="#FFFFFF", text_align="center")
    rest = ft.Text(str(model.rest_seconds), size=56 if compact else 68, weight="bold", color="#FFD166", text_align="center")
    set_chips = []
    for index, done in enumerate(model.sets_completed if model.recording_mode == "strength" else []):
        selected = index == model.selected_set_index
        chip_bgcolor = PRIMARY if done else "#C78B20" if selected else "#27312E"
        set_chips.append(ft.Container(
            content=ft.Container(
                content=ft.Text(str(index + 1), size=12, weight="bold", color="#FFFFFF" if done or selected else "#AAB7B3"),
                width=36,
                height=36,
                border_radius=18,
                alignment=ft.Alignment.CENTER,
                bgcolor=chip_bgcolor,
                border=thin_border("#FFD166") if selected and not done else None,
            ),
            width=48,
            height=48,
            border_radius=24,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e, selected_index=index: actions.select_set(selected_index),
        ))

    end_button = ft.Container(
        content=ft.Text("结束", size=13, weight="bold", color="#F97066", max_lines=1, overflow="ellipsis"),
        width=64,
        height=48,
        bgcolor="#241B1B",
        border=thin_border("#F97066"),
        border_radius=8,
        alignment=ft.Alignment.CENTER,
        on_click=actions.finish,
    )
    controls = [
        ft.Row([
            ft.IconButton(icon=ft.Icons.CLOSE, icon_color="#FFFFFF", tooltip="返回今日", width=48, height=48, on_click=actions.close),
            ft.Text(f"完成 {model.completed_sets}/{model.planned_sets} 组", color="#EAFBF5", size=14, weight="bold", text_align="center", expand=True),
            end_button,
        ], alignment="spaceBetween", spacing=12),
        ft.Column([small_text("训练时长", color="#B9C8C3"), elapsed], horizontal_alignment="center", spacing=0),
        _segmented_progress(model.progress, model.planned_sets),
    ]
    is_resting = model.rest_status in {"running", "paused"}
    next_work_card = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.ARROW_FORWARD, color="#AFC0BA", size=20),
            ft.Column([
                small_text("下一个训练项", color="#AFC0BA"),
                ft.Text(
                    (model.next_work_text or "下一个：暂无").removeprefix("下一个："),
                    size=15,
                    color="#FFFFFF",
                    weight="bold",
                    max_lines=2,
                    overflow="ellipsis",
                ),
            ], spacing=2, expand=True),
        ], spacing=10),
        bgcolor="#252F2C",
        border=thin_border("#3D4A46"),
        border_radius=12,
        padding=12,
    )
    if is_resting:
        controls.append(ft.Container(
            content=ft.Column([
                ft.Text("组间休息" if model.rest_status != "paused" else "组间休息已暂停", size=16, color="#FFFFFF", weight="bold"),
                rest,
                ft.Row([
                    make_button("-10秒", on_click=lambda e: actions.adjust_rest(-10), bgcolor="#4A5652", color="#FFFFFF", expand=True, height=48),
                    make_button("继续" if model.rest_status == "paused" else "暂停", on_click=actions.toggle_rest, bgcolor="#4A5652", color="#FFFFFF", expand=True, height=48),
                    make_button("+10秒", on_click=lambda e: actions.adjust_rest(10), bgcolor="#4A5652", color="#FFFFFF", expand=True, height=48),
                    make_button("跳过", on_click=actions.skip_rest, bgcolor="#4A5652", color="#FFFFFF", expand=True, height=48),
                ], spacing=6),
            ], horizontal_alignment="center", alignment="center", spacing=12 if compact else 18, expand=True),
            bgcolor="#252F2C",
            border_radius=16,
            padding=12 if compact else 20,
            expand=True,
            data="active-rest-card",
        ))

    work_card = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text(model.exercise_name or "当前动作", size=22, weight="bold", color="#FFFFFF"),
                ft.Text(f"动作 {model.exercise_index + 1}/{model.exercise_count}", size=13, color="#D8E2DF", weight="bold"),
            ], alignment="spaceBetween"),
            *([ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(model.group_label, size=14, color="#FFD166", weight="bold"),
                        ft.Text(model.group_position_text, size=13, color="#D8E2DF", weight="bold"),
                    ], alignment="spaceBetween"),
                    ft.Row([
                        ft.Container(
                            content=ft.Text(label, size=12, color="#FFFFFF" if is_current else "#D8E2DF", weight="bold", max_lines=1, overflow="ellipsis"),
                            bgcolor="#21A366" if is_current else "#38433F" if done else "#27312E",
                            border=thin_border("#FFD166" if is_current else "#38433F"),
                            border_radius=18,
                            padding=ft.Padding(left=10, top=6, right=10, bottom=6),
                        )
                        for label, _member_id, is_current, done in model.group_members
                    ], spacing=6, scroll=getattr(getattr(ft, "ScrollMode", object()), "HIDDEN", "hidden")),
                ], spacing=6),
                bgcolor="#252F2C",
                border_radius=12,
                padding=10,
            )] if model.group_label else []),
            *([ft.Row(set_chips, spacing=8, scroll=getattr(getattr(ft, "ScrollMode", object()), "HIDDEN", "hidden"))] if set_chips else []),
            *([ft.Row([
                ft.IconButton(icon=ft.Icons.REMOVE, icon_color="#FFFFFF", bgcolor="#38433F", width=48, height=48, on_click=lambda e: actions.adjust_weight(-1)),
                ft.Container(
                    content=ft.Column([
                        small_text("重量", color="#AFC0BA"),
                        ft.Text(
                            model.weight_text if model.weight_text == "自重" else f"{model.weight_text} kg",
                            size=28,
                            weight="bold",
                            color="#FFFFFF",
                        ),
                    ], horizontal_alignment="center", spacing=0),
                    height=56,
                    alignment=ft.Alignment.CENTER,
                    border_radius=8,
                    ink=True,
                    on_click=actions.edit_weight,
                    expand=True,
                ),
                ft.IconButton(icon=ft.Icons.ADD, icon_color="#FFFFFF", bgcolor="#38433F", width=48, height=48, on_click=lambda e: actions.adjust_weight(1)),
            ]), ft.Row([
                ft.IconButton(icon=ft.Icons.REMOVE, icon_color="#FFFFFF", bgcolor="#38433F", width=48, height=48, on_click=lambda e: actions.adjust_reps(-1)),
                ft.Column([small_text("次数", color="#AFC0BA"), ft.Text(f"{model.reps} 次", size=28, weight="bold", color="#FFFFFF")], horizontal_alignment="center", expand=True, spacing=0),
                ft.IconButton(icon=ft.Icons.ADD, icon_color="#FFFFFF", bgcolor="#38433F", width=48, height=48, on_click=lambda e: actions.adjust_reps(1)),
            ])] if model.recording_mode == "strength" else [
                ft.Container(
                    content=ft.Column([
                        small_text("时长", color="#AFC0BA"),
                        ft.Text(f"{model.duration_seconds // 60}:{model.duration_seconds % 60:02d}", size=32, weight="bold", color="#FFFFFF"),
                    ], horizontal_alignment="center", spacing=0),
                    height=72, alignment=ft.Alignment.CENTER, border_radius=8, ink=True,
                    on_click=actions.edit_duration,
                ),
                *([ft.Container(
                    content=ft.Column([
                        small_text("距离", color="#AFC0BA"),
                        ft.Text(f"{model.distance_text or '未填写'} km", size=28, weight="bold", color="#FFFFFF"),
                    ], horizontal_alignment="center", spacing=0),
                    height=72, alignment=ft.Alignment.CENTER, border_radius=8, ink=True,
                    on_click=actions.edit_distance,
                )] if model.recording_mode == "cardio" and model.distance_enabled else []),
                *([ft.Container(
                    content=ft.Row([
                        ft.Column([small_text(label, color="#AFC0BA"), ft.Text(value, size=24, weight="bold", color="#FFFFFF")], spacing=0, expand=True),
                        ft.Icon(ft.Icons.EDIT, color="#AFC0BA", size=20),
                    ]),
                    height=64, alignment=ft.Alignment.CENTER, border_radius=8, ink=True, padding=8,
                    on_click=lambda e, metric_key=key, metric_label=label: actions.edit_metric(metric_key, metric_label),
                ) for key, label, value in model.cardio_metrics] if model.recording_mode == "cardio" else []),
            ]),
            (
                ft.Row([
                    make_button("取消", on_click=actions.cancel_complete, bgcolor="#4A5652", color="#FFFFFF", expand=True, height=primary_button_height),
                    make_button("确认完成", on_click=actions.complete_or_undo, icon=ft.Icons.CHECK_CIRCLE, bgcolor="#21A366", color="#FFFFFF", expand=True, height=primary_button_height),
                ], spacing=8)
                if model.confirm_complete and not model.selected_set_done else
                make_button(
                    ("撤销本组" if model.selected_set_done else "完成本组") if model.recording_mode == "strength" else ("撤销完成" if model.selected_set_done else "完成动作"),
                    on_click=actions.complete_or_undo if model.selected_set_done else actions.ask_complete,
                    icon=ft.Icons.UNDO if model.selected_set_done else ft.Icons.CHECK_CIRCLE,
                    bgcolor="#56635F" if model.selected_set_done else "#21A366",
                    color="#FFFFFF",
                    expand=True,
                    height=primary_button_height,
                )
            ),
            next_work_card,
            ft.Row([
                make_button("上一个", on_click=lambda e: actions.move_exercise(-1), icon=ft.Icons.CHEVRON_LEFT, bgcolor="#303B37", color="#FFFFFF", expand=True),
                make_button("下一个", on_click=lambda e: actions.move_exercise(1), icon=ft.Icons.CHEVRON_RIGHT, bgcolor="#303B37", color="#FFFFFF", expand=True),
            ], spacing=8),
        ], spacing=card_spacing),
        bgcolor="#1B2320",
        border_radius=16,
        padding=card_padding,
    )
    if is_resting:
        controls.append(next_work_card)
    else:
        controls.append(work_card)
    return ActiveTrainingResult(
        control=ft.Container(
            content=ft.Column(controls, spacing=surface_spacing, expand=True),
            bgcolor="#101513",
            padding=surface_padding,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            expand=True,
            data="active-training-surface",
        ),
        elapsed_control=elapsed,
        rest_control=rest,
    )


__all__ = ["ActiveTrainingActions", "ActiveTrainingModel", "ActiveTrainingResult", "build_active_training"]
