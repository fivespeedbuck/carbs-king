"""Training-page presentation components.

Session mutation and persistence remain in services/main coordination. This
module owns the active-workout visual tree and emits only user intents.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from ui_components import PRIMARY, make_button, single_line_font_size, small_text, thin_border


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
    viewport_width: float = 430.0
    current_work_index: int = 0
    work_completed: Sequence[bool] = ()


@dataclass(frozen=True)
class ActiveTrainingActions:
    close: Callable[[Any], None]
    finish: Callable[[Any], None]
    show_help: Callable[[Any], None]
    select_set: Callable[[int], None]
    adjust_rest: Callable[[int], None]
    toggle_rest: Callable[[Any], None]
    skip_rest: Callable[[Any], None]
    adjust_weight: Callable[[int], None]
    edit_weight: Callable[[Any], None]
    adjust_reps: Callable[[int], None]
    edit_reps: Callable[[Any], None]
    edit_duration: Callable[[Any], None]
    edit_distance: Callable[[Any], None]
    edit_metric: Callable[[str, str], None]
    complete_or_undo: Callable[[Any], None]
    ask_complete: Callable[[Any], None]
    cancel_complete: Callable[[Any], None]
    move_exercise: Callable[[int], None]
    adjust_sets: Callable[[int], None]
    manage_actions: Callable[[Any], None]


@dataclass(frozen=True)
class ActiveTrainingResult:
    control: ft.Control
    elapsed_control: ft.Text
    rest_control: ft.Text


def _segmented_progress(
    value: float,
    planned_work_items: int,
    current_work_index: int = 0,
    work_completed: Sequence[bool] = (),
) -> ft.Container:
    work_items = max(0, int(planned_work_items or 0))
    selected = max(0, min(work_items - 1, int(current_work_index or 0))) if work_items else -1
    if work_completed:
        completion_flags = [
            bool(work_completed[index]) if index < len(work_completed) else False
            for index in range(work_items)
        ]
    else:
        completed_prefix = max(
            0,
            min(work_items, int(round(max(0.0, min(1.0, float(value or 0))) * work_items))),
        )
        completion_flags = [index < completed_prefix for index in range(work_items)]

    segments = ft.Row([
        ft.Container(
            expand=True,
            height=8,
            bgcolor=(
                "#FFD166" if index == selected
                else PRIMARY if completion_flags[index]
                else "#31413C"
            ),
            border=ft.Border(right=ft.BorderSide(width=1, color="#DCE9E4")) if index < work_items - 1 else None,
            data=(
                "active-progress-current" if index == selected
                else "active-progress-completed" if completion_flags[index]
                else "active-progress-pending"
            ),
        )
        for index in range(work_items)
    ], spacing=0, height=8)
    return ft.Container(
        content=segments,
        height=8,
        border_radius=4,
        bgcolor="#31413C",
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )


def _build_cardio_metric_grid(model: ActiveTrainingModel, actions: ActiveTrainingActions) -> ft.Control:
    """Render cardio inputs compactly so an active workout remains one screen."""
    entries: list[tuple[str, str, Callable[[Any], None]]] = [
        (
            "时长",
            f"{model.duration_seconds // 60}:{model.duration_seconds % 60:02d}",
            actions.edit_duration,
        ),
    ]
    if model.distance_enabled:
        entries.append(("距离", f"{model.distance_text or '未填写'} km", actions.edit_distance))
    entries.extend(
        (label, value, lambda e, metric_key=key, metric_label=label: actions.edit_metric(metric_key, metric_label))
        for key, label, value in model.cardio_metrics
    )

    def metric_card(label: str, value: str, on_click: Callable[[Any], None]) -> ft.Container:
        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(label, size=12, color="#AFC0BA", text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(value, size=20, weight="bold", color="#FFFFFF", text_align="center", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=0, expand=True),
                ft.Icon(ft.Icons.EDIT, color="#AFC0BA", size=15),
            ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=52,
            bgcolor="#252F2C",
            border_radius=8,
            padding=6,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=on_click,
            expand=True,
            data="active-cardio-metric",
        )

    total = len(entries)
    if total <= 3:
        rows = [entries]
    elif total == 4:
        rows = [entries[:2], entries[2:]]
    elif total == 5:
        rows = [entries[:2], entries[2:]]
    else:
        rows = [entries[:3], entries[3:6]]
        if total > 6:
            rows.extend([entries[index:index + 3] for index in range(6, total, 3)])
    return ft.Column(
        [ft.Row([metric_card(*entry) for entry in row], spacing=6) for row in rows],
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        data="active-cardio-metric-grid",
    )


def build_active_training(model: ActiveTrainingModel, actions: ActiveTrainingActions) -> ActiveTrainingResult:
    compact = float(model.viewport_height or 0) < 820
    grouped_compact = compact or bool(model.group_label)
    is_cardio = model.recording_mode == "cardio"
    surface_padding = 8 if compact else 12
    surface_spacing = 8 if compact else 12
    card_padding = 10 if model.group_label else 14 if compact else 20
    card_spacing = 4 if model.group_label else 10 if compact else 14
    primary_button_height = 48 if model.group_label else 52 if compact else 64
    elapsed = ft.Text(model.elapsed_text, size=42 if compact else 50, weight="bold", color="#FFFFFF", text_align="center")
    rest = ft.Text(str(model.rest_seconds), size=88 if compact else 104, weight="bold", color="#FFD166", text_align="center")
    set_chips = []
    for index, done in enumerate(model.sets_completed if model.recording_mode == "strength" else []):
        selected = index == model.selected_set_index
        # Keep the cursor visible when navigating back to a completed set:
        # current selection takes precedence over the completed colour.
        chip_bgcolor = "#C78B20" if selected else PRIMARY if done else "#27312E"
        set_chips.append(ft.Container(
            content=ft.Container(
                content=ft.Text(str(index + 1), size=12, weight="bold", color="#FFFFFF" if done or selected else "#AAB7B3"),
                width=36,
                height=36,
                border_radius=18,
                alignment=ft.Alignment.CENTER,
                bgcolor=chip_bgcolor,
                border=thin_border("#FFD166") if selected else None,
                data="active-set-chip-current" if selected else "active-set-chip-completed" if done else "active-set-chip-pending",
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
        ft.Column(
            [elapsed],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=0,
        ),
        _segmented_progress(
            model.progress,
            model.planned_sets,
            model.current_work_index,
            model.work_completed,
        ),
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
        padding=6 if model.group_label else 12,
    )
    rest_card = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Text("组间休息" if model.rest_status != "paused" else "组间休息已暂停", size=32, color="#FFFFFF", weight="bold"),
                        rest,
                    ], horizontal_alignment="center", alignment=ft.MainAxisAlignment.CENTER, spacing=16 if compact else 22),
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                ),
                ft.Column([
                        ft.Row([
                        make_button("-10秒", on_click=lambda e: actions.adjust_rest(-10), bgcolor="#303B37", color="#FFFFFF", expand=True, height=56),
                        make_button("继续" if model.rest_status == "paused" else "暂停", on_click=actions.toggle_rest, bgcolor="#303B37", color="#FFFFFF", expand=True, height=56),
                        make_button("+10秒", on_click=lambda e: actions.adjust_rest(10), bgcolor="#303B37", color="#FFFFFF", expand=True, height=56),
                        make_button("跳过", on_click=actions.skip_rest, bgcolor="#303B37", color="#FFFFFF", expand=True, height=56),
                        ], spacing=8),
                        ft.Row([
                            make_button(
                                "调整训练顺序",
                                on_click=actions.manage_actions,
                                bgcolor="#303B37",
                                color="#FFFFFF",
                                expand=True,
                                height=48,
                            ),
                        ], data="active-rest-order-action"),
                        next_work_card,
                ], spacing=8),
            ], spacing=4),
            bgcolor="#252F2C",
            border_radius=16,
            padding=12 if compact else 20,
            left=None if model.group_label else 0,
            top=None if model.group_label else 0,
            right=None if model.group_label else 0,
            bottom=None if model.group_label else 0,
            data="active-rest-card",
        )

    title_available_width = (
        float(model.viewport_width or 430)
        - (surface_padding * 2)
        - (card_padding * 2)
        - 52  # help icon + action position column
        - 10  # Row's default gap between title and action column
    )
    title_size = single_line_font_size(
        model.exercise_name or "当前动作",
        title_available_width,
        maximum=32 if compact else 36,
        minimum=20,
    )
    normal_action_header = ft.Row([
        ft.Text(
            model.exercise_name or "当前动作",
            size=title_size,
            weight="bold",
            color="#FFFFFF",
            expand=True,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            data="active-exercise-title",
        ),
        ft.Column([
            ft.IconButton(
                icon=ft.Icons.HELP_OUTLINE,
                icon_color="#CDE9DF",
                tooltip="动作技巧",
                width=42,
                height=42,
                on_click=actions.show_help,
            ),
            ft.Text(
                f"动作 {model.exercise_index + 1}/{model.exercise_count}",
                size=12,
                color="#D8E2DF",
                weight="bold",
                text_align="center",
            ),
        ], horizontal_alignment="center", spacing=0),
    ], alignment="spaceBetween", vertical_alignment="start")
    group_action_card = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text(model.group_label, size=18, color="#FFD166", weight="bold"),
                ft.Row([
                    ft.Text(model.group_position_text, size=15, color="#D8E2DF", weight="bold"),
                    ft.IconButton(
                        icon=ft.Icons.HELP_OUTLINE,
                        icon_color="#CDE9DF",
                        tooltip="动作技巧",
                        width=32,
                        height=32,
                        on_click=actions.show_help,
                    ),
                ], spacing=2),
            ], alignment="spaceBetween", vertical_alignment="center"),
            ft.Row([
                ft.Container(
                    content=ft.Text(
                        label,
                        size=15,
                        color="#FFFFFF" if is_current else "#D8E2DF",
                        weight="bold",
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    bgcolor=PRIMARY if is_current else "#38433F" if done else "#27312E",
                    border=thin_border("#FFD166" if is_current else "#38433F"),
                    border_radius=20,
                    padding=ft.Padding(left=12, top=4, right=12, bottom=4),
                    data="active-group-member-current" if is_current else "active-group-member",
                )
                for label, _member_id, is_current, done in model.group_members
            ], spacing=6, scroll=getattr(getattr(ft, "ScrollMode", object()), "HIDDEN", "hidden")),
        ], spacing=2),
        bgcolor="#252F2C",
        border_radius=12,
        padding=4,
        data="active-group-action-card",
    )

    work_card = ft.Container(
        content=ft.Column([
            group_action_card if model.group_label else normal_action_header,
            *([ft.Row(set_chips, spacing=8, scroll=getattr(getattr(ft, "ScrollMode", object()), "HIDDEN", "hidden"))] if set_chips else []),

            *([ft.Row([
                ft.IconButton(icon=ft.Icons.REMOVE, icon_color="#FFFFFF", bgcolor="#38433F", width=48, height=48, on_click=lambda e: actions.adjust_weight(-1)),
                ft.Container(
                    content=ft.Column([
                        small_text("重量", color="#AFC0BA"),
                        ft.Text(
                            model.weight_text if model.weight_text == "自重" else f"{model.weight_text} kg",
                            size=28 if compact else 32,
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
                ft.Container(
                    content=ft.Column([
                        small_text("次数", color="#AFC0BA"),
                        ft.Text(f"{model.reps} 次", size=28 if compact else 32, weight="bold", color="#FFFFFF", text_align="center"),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=0),
                    height=56,
                    alignment=ft.Alignment.CENTER,
                    border_radius=8,
                    ink=True,
                    on_click=actions.edit_reps,
                    expand=True,
                ),
                ft.IconButton(icon=ft.Icons.ADD, icon_color="#FFFFFF", bgcolor="#38433F", width=48, height=48, on_click=lambda e: actions.adjust_reps(1)),
            ])] if model.recording_mode == "strength" else [
                _build_cardio_metric_grid(model, actions),
            ]),
            (
                ft.Row([
                    make_button("取消", on_click=actions.cancel_complete, bgcolor="#4A5652", color="#FFFFFF", expand=True, height=primary_button_height),
                    make_button("确认完成", on_click=actions.complete_or_undo, icon=ft.Icons.CHECK_CIRCLE, bgcolor=PRIMARY, color="#FFFFFF", expand=True, height=primary_button_height),
                ], spacing=8)
                if model.confirm_complete and not model.selected_set_done else
                ft.Row([make_button(
                    ("撤销本组" if model.selected_set_done else "完成本组") if model.recording_mode == "strength" else ("撤销完成" if model.selected_set_done else "完成动作"),
                    on_click=actions.complete_or_undo if model.selected_set_done else actions.ask_complete,
                    icon=ft.Icons.UNDO if model.selected_set_done else ft.Icons.CHECK_CIRCLE,
                    bgcolor="#56635F" if model.selected_set_done else PRIMARY,
                    color="#FFFFFF",
                    expand=True,
                    height=primary_button_height,
                )])
            ),
            ft.Row([
                make_button("上一组", on_click=lambda e: actions.move_exercise(-1), icon=ft.Icons.CHEVRON_LEFT, bgcolor="#303B37", color="#FFFFFF", expand=True),
                make_button("下一组", on_click=lambda e: actions.move_exercise(1), icon=ft.Icons.CHEVRON_RIGHT, bgcolor="#303B37", color="#FFFFFF", expand=True),
            ], spacing=8),
            *([ft.Row([
                make_button("减一组", on_click=lambda e: actions.adjust_sets(-1), bgcolor="#303B37", color="#FFFFFF", expand=True),
                make_button("加一组", on_click=lambda e: actions.adjust_sets(1), bgcolor="#303B37", color="#FFFFFF", expand=True),
            ], spacing=8, data="active-training-set-actions")] if model.recording_mode == "strength" else []),
            ft.Row([
                make_button("调整训练顺序", on_click=actions.manage_actions, bgcolor="#303B37", color="#FFFFFF", expand=True),
            ], data="active-training-order-action"),
            next_work_card,
        ], spacing=6 if is_cardio else card_spacing),
        bgcolor="#1B2320",
        border_radius=16,
        padding=12 if is_cardio else card_padding,
    )
    if is_resting and model.group_label:
        rest_card.expand = True
        controls.append(rest_card)
    elif is_resting:
        controls.append(ft.Stack([
            ft.Container(
                content=work_card,
                opacity=0,
                ignore_interactions=True,
                data="active-rest-size-reference",
            ),
            rest_card,
        ], data="active-rest-size-match"))
    else:
        controls.append(work_card)
    return ActiveTrainingResult(
        control=ft.Container(
            content=ft.Column(
                controls,
                spacing=surface_spacing,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
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
