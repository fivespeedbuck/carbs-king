"""Empty and planned training workspace views."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import flet as ft

from app_utils import to_float
from training_experience_service import preview_session_exercise_block_order
from ui_components import GREEN, PRIMARY, PRIMARY_SOFT, RED, SUB, SURFACE, TEXT, card, make_button, section_title, small_text, thin_border


_METRIC_LABELS = {
    "speed_kph": "速度", "incline_percent": "坡度", "resistance_level": "阻力",
    "cadence_rpm": "踏频", "strides_per_minute": "步频", "stroke_rate_spm": "桨频",
    "steps_per_minute": "爬楼步频",
}


@dataclass(frozen=True)
class EmptyTrainingActions:
    reuse_history: Callable[[Any], None]
    create_free: Callable[[Any], None]
    add_first: Callable[[Any], None]


def build_empty_training(actions: EmptyTrainingActions) -> ft.Control:
    return ft.Column([
        ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.FITNESS_CENTER, size=54, color="#FFFFFF"),
                ft.Text("今天练什么？", size=25, weight="bold", color="#FFFFFF"),
                ft.Text("从上次训练继续，或创建一场自由训练", size=14, color="#EAFBF5", weight="bold", text_align="center"),
                ft.Row([
                    make_button("复用历史训练", on_click=actions.reuse_history, bgcolor="#FFFFFF", color=GREEN, expand=True),
                    make_button("自由训练", on_click=actions.create_free, bgcolor="#125F4D", color="#FFFFFF", expand=True),
                ], spacing=8),
            ], horizontal_alignment="center", spacing=14),
            bgcolor="#116E59", border_radius=12, padding=24, margin=8,
        ),
        card(ft.Column([
            section_title("训练准备"),
            small_text("添加动作后即可开始，重量与次数会完整保存。"),
            make_button("添加第一个动作", on_click=actions.add_first, icon=ft.Icons.ADD, expand=True, height=54),
        ], spacing=10), padding=14),
    ], spacing=0)


@dataclass(frozen=True)
class PlannedTrainingActions:
    start: Callable[[Any], None]
    add_exercise: Callable[[Any], None]
    delete_exercise: Callable[[int], None]
    reuse_history: Callable[[Any], None]
    clear: Callable[[Any], None]
    group_exercise: Callable[[str], None]
    show_help: Callable[[str], None]
    edit_exercise: Callable[[str], None]
    drag_start: Callable[[str], None]
    drag_complete: Callable[[Any], None]
    drag_move: Callable[[Any], None]
    drag_accept: Callable[[str], None]


def _exercise_detail(exercise: Mapping[str, Any]) -> str:
    sets = exercise.get("sets", []) if isinstance(exercise, Mapping) else []
    first = sets[0] if sets else {}
    mode = str(exercise.get("recording_mode") or "strength")
    if mode == "cardio":
        duration = max(0, int(to_float(exercise.get("duration_seconds"))))
        detail = f"{exercise.get('body_part', '')} · 有氧 · {duration // 60}:{duration % 60:02d}"
        if exercise.get("distance_km") not in (None, ""):
            detail += f" · {to_float(exercise.get('distance_km')):g} km"
        for metric_key in exercise.get("cardio_metric_fields", []):
            metric_value = exercise.get("cardio_metrics", {}).get(metric_key)
            if metric_value is not None:
                detail += f" · {_METRIC_LABELS.get(metric_key, metric_key)} {to_float(metric_value):g}"
        return detail
    if mode == "timed":
        duration = max(0, int(to_float(exercise.get("duration_seconds"))))
        return f"{exercise.get('body_part', '')} · 计时 · {duration // 60}:{duration % 60:02d}"
    return f"{exercise.get('body_part', '')} · {len(sets)} 组 · {to_float(first.get('weight_kg')):g} kg × {int(to_float(first.get('reps')))}"


def _exercise_detail_lines(exercise: Mapping[str, Any]) -> tuple[str, str]:
    sets = exercise.get("sets", []) if isinstance(exercise, Mapping) else []
    first = sets[0] if sets else {}
    mode = str(exercise.get("recording_mode") or "strength")
    body_part = str(exercise.get("body_part") or "").strip()
    if mode == "cardio":
        duration = max(0, int(to_float(exercise.get("duration_seconds"))))
        summary = "  ".join(part for part in (body_part, "有氧") if part)
        details = [f"{duration // 60}:{duration % 60:02d}"]
        if exercise.get("distance_km") not in (None, ""):
            details.append(f"{to_float(exercise.get('distance_km')):g} km")
        return summary, "  ".join(details)
    if mode == "timed":
        duration = max(0, int(to_float(exercise.get("duration_seconds"))))
        summary = "  ".join(part for part in (body_part, "计时") if part)
        return summary, f"{duration // 60}:{duration % 60:02d}"
    summary = "  ".join(part for part in (body_part, f"{len(sets)}组") if part)
    return summary, f"{to_float(first.get('weight_kg')):g} kg × {int(to_float(first.get('reps')))}"


def _drag_handle(
    exercise_id: str,
    name: str,
    actions: PlannedTrainingActions,
    on_start: Callable[[str], None],
    on_complete: Callable[[Any], None],
    *,
    size: int = 48,
) -> ft.Control:
    handle = ft.Container(
        content=ft.Icon(ft.Icons.DRAG_HANDLE, color=SUB, tooltip="拖动排序"),
        width=size,
        height=size,
        alignment=ft.Alignment.CENTER,
        border_radius=size // 2,
    )

    def start_drag(event):
        on_start(exercise_id)
        actions.drag_start(exercise_id)

    return ft.Draggable(
        content=handle,
        content_when_dragging=ft.Container(
            content=ft.Icon(ft.Icons.DRAG_HANDLE, color=SUB),
            width=size,
            height=size,
            alignment=ft.Alignment.CENTER,
            opacity=0.28,
        ),
        group="session-exercise",
        axis=ft.Axis.VERTICAL,
        affinity=ft.Axis.VERTICAL,
        data=exercise_id,
        content_feedback=ft.Container(
            content=ft.Text(name, size=15, weight="bold", color=TEXT),
            width=300,
            bgcolor="#FFFFFF",
            border=thin_border(PRIMARY),
            border_radius=10,
            padding=16,
            opacity=0.94,
        ),
        on_drag_start=start_drag,
        on_drag_complete=on_complete,
    )


def _fixed_icon_button(
    icon: Any,
    tooltip: str,
    color: str,
    on_click: Callable[[Any], None],
    *,
    size: int = 48,
) -> ft.Control:
    return ft.IconButton(
        icon=icon,
        tooltip=tooltip,
        icon_color=color,
        icon_size=20 if size < 48 else None,
        width=size,
        height=size,
        on_click=on_click,
    )


def build_planned_training(session: Mapping[str, Any], actions: PlannedTrainingActions) -> ft.Control:
    exercises = session.get("exercises", []) if isinstance(session.get("exercises", []), list) else []
    groups = {
        str(group.get("id") or ""): group
        for group in session.get("exercise_groups", [])
        if isinstance(group, Mapping)
    } if isinstance(session.get("exercise_groups"), list) else {}
    by_id = {str(item.get("id") or ""): item for item in exercises if isinstance(item, Mapping)}
    rendered: set[str] = set()
    row_targets: dict[str, ft.DragTarget] = {}
    row_cards: dict[str, ft.Container] = {}
    row_default_borders: dict[str, Any] = {}
    baseline_order: list[str] = []
    exercise_list = ft.Column(spacing=8)
    drag_state = {"id": "", "target": "", "accepted": False}
    preview_animation = ft.Animation(150, ft.AnimationCurve.EASE_OUT_CUBIC)

    def update_preview_visuals(target_id: str = "") -> None:
        dragged_id = drag_state["id"]
        for block_id, row_card in row_cards.items():
            is_target = bool(target_id and block_id == target_id and block_id != dragged_id)
            row_card.bgcolor = PRIMARY_SOFT if is_target else "#FFFFFF"
            row_card.border = thin_border(PRIMARY) if is_target else row_default_borders[block_id]
            row_card.scale = 1.015 if is_target else 1.0
            row_card.opacity = 0.58 if block_id == dragged_id and target_id else 1.0

    def show_drop_preview(target_id: str) -> None:
        dragged_id = drag_state["id"]
        if not dragged_id or not target_id or target_id == dragged_id or target_id == drag_state["target"]:
            return
        preview_order = preview_session_exercise_block_order(
            exercises,
            list(groups.values()),
            dragged_id,
            target_id,
        )
        if set(preview_order) != set(row_targets):
            return
        drag_state["target"] = target_id
        exercise_list.controls = [row_targets[block_id] for block_id in preview_order]
        update_preview_visuals(target_id)
        try:
            exercise_list.update()
        except RuntimeError:
            pass

    def start_drag(exercise_id: str) -> None:
        drag_state.update({"id": exercise_id, "target": "", "accepted": False})
        exercise_list.controls = [row_targets[block_id] for block_id in baseline_order]
        update_preview_visuals()

    def move_over_target(event: Any, target_id: str) -> None:
        actions.drag_move(event)
        show_drop_preview(target_id)

    def accept_preview(target_id: str) -> None:
        committed_target = drag_state["target"] or target_id
        drag_state["accepted"] = True
        update_preview_visuals()
        actions.drag_accept(committed_target)

    def complete_drag(event: Any) -> None:
        if not drag_state["accepted"]:
            exercise_list.controls = [row_targets[block_id] for block_id in baseline_order]
            update_preview_visuals()
            try:
                exercise_list.update()
            except RuntimeError:
                pass
        drag_state.update({"id": "", "target": "", "accepted": False})
        actions.drag_complete(event)

    def register_target(block_id: str, row_card: ft.Container) -> None:
        row_card.animate = preview_animation
        row_card.animate_scale = preview_animation
        row_card.animate_opacity = preview_animation
        target = ft.DragTarget(
            content=row_card,
            group="session-exercise",
            data=block_id,
            on_will_accept=lambda e, value=block_id: show_drop_preview(value),
            on_move=lambda e, value=block_id: move_over_target(e, value),
            on_accept=lambda e, value=block_id: accept_preview(value),
        )
        baseline_order.append(block_id)
        row_cards[block_id] = row_card
        row_default_borders[block_id] = row_card.border
        row_targets[block_id] = target

    for index, exercise in enumerate(exercises):
        exercise_id = str(exercise.get("id") or "")
        if not exercise_id or exercise_id in rendered:
            continue
        group = groups.get(str(exercise.get("group_id") or ""))
        if group:
            member_ids = [str(item) for item in group.get("exercise_ids", []) if str(item) in by_id]
            if exercise_id != (member_ids[0] if member_ids else ""):
                continue
            rendered.update(member_ids)
            title = "超级组" if group.get("group_type") == "superset" else "复合组"
            member_rows = []
            for member_index, member_id in enumerate(member_ids, 1):
                member = by_id[member_id]
                member_rows.append(ft.Container(
                    content=ft.Row([
                        ft.Container(content=ft.Text(str(member_index), color="#FFFFFF", weight="bold"), width=28, height=28, bgcolor=PRIMARY, border_radius=8, alignment=ft.Alignment.CENTER),
                        ft.Column([
                            ft.Text(str(member.get("name", "")), size=15, weight="bold", color=TEXT),
                            small_text(_exercise_detail(member)),
                        ], expand=True, spacing=2),
                        _fixed_icon_button(ft.Icons.HELP_OUTLINE, "动作技巧", GREEN, lambda e, value=member_id: actions.show_help(value)),
                        _fixed_icon_button(ft.Icons.EDIT_OUTLINED, "编辑参数", GREEN, lambda e, value=member_id: actions.edit_exercise(value)),
                    ], spacing=8),
                    bgcolor=SURFACE,
                    border_radius=8,
                    padding=8,
                ))
            row_card = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Column([
                            ft.Text(f"{title} · {len(member_ids)} 个动作", size=16, weight="bold", color=TEXT),
                            small_text("组内动作会绑定在一个大框内排序和训练"),
                        ], spacing=2, expand=True),
                        _drag_handle(exercise_id, title, actions, start_drag, complete_drag),
                        _fixed_icon_button(ft.Icons.ADD, "编辑组合", GREEN, lambda e, value=exercise_id: actions.group_exercise(value)),
                    ], spacing=8),
                    *member_rows,
                ], spacing=8),
                bgcolor="#FFFFFF",
                border=thin_border(PRIMARY),
                border_radius=10,
                padding=12,
            )
            register_target(exercise_id, row_card)
            continue

        rendered.add(exercise_id)
        summary, prescription = _exercise_detail_lines(exercise)
        row_card = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Text(str(index + 1), color="#FFFFFF", weight="bold"),
                    width=36,
                    height=36,
                    bgcolor=PRIMARY,
                    border_radius=10,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column([
                    ft.Text(
                        str(exercise.get("name", "")),
                        size=16,
                        weight="bold",
                        color=TEXT,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(summary, size=13, color=SUB, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(prescription, size=13, color=SUB, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ], expand=True, spacing=1, tight=True),
                ft.Row([
                    _fixed_icon_button(ft.Icons.HELP_OUTLINE, "动作技巧", GREEN, lambda e, value=exercise_id: actions.show_help(value), size=36),
                    _fixed_icon_button(ft.Icons.EDIT_OUTLINED, "编辑参数", GREEN, lambda e, value=exercise_id: actions.edit_exercise(value), size=36),
                    _fixed_icon_button(ft.Icons.ADD, "组成超级组或复合组", GREEN, lambda e, value=exercise_id: actions.group_exercise(value), size=36),
                    _drag_handle(exercise_id, str(exercise.get("name", "")), actions, start_drag, complete_drag, size=36),
                    _fixed_icon_button(ft.Icons.DELETE_OUTLINE, "删除动作", RED, lambda e, value=index: actions.delete_exercise(value), size=36),
                ], spacing=0, tight=True),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#FFFFFF",
            border=thin_border(),
            border_radius=10,
            padding=10,
        )
        register_target(exercise_id, row_card)

    exercise_list.controls = [row_targets[block_id] for block_id in baseline_order]

    return ft.Column([
        ft.Container(content=ft.Column([
            ft.Row([ft.Column([small_text("训练计划", color="#EAFBF5"), ft.Text("当前的训练", size=25, weight="bold", color="#FFFFFF")], spacing=2), ft.Icon(ft.Icons.FITNESS_CENTER, size=42, color="#FFFFFF")], alignment="spaceBetween"),
            ft.Text(f"{len(exercises)} 个动作 · {sum(len(item.get('sets', [])) for item in exercises if item.get('recording_mode', 'strength') == 'strength')} 个力量组", size=14, color="#EAFBF5", weight="bold"),
            make_button("开始训练", on_click=actions.start, icon=ft.Icons.PLAY_ARROW, bgcolor="#FFFFFF", color=GREEN, expand=True, height=58),
        ], spacing=12), bgcolor="#116E59", border_radius=12, padding=20, margin=8),
        card(ft.Column([
            ft.Row([section_title("动作安排"), make_button("添加动作", on_click=actions.add_exercise, icon=ft.Icons.ADD, bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween"),
            small_text("拖动右侧手柄排序；超级组/复合组会作为一个整体移动。"),
            exercise_list if baseline_order else ft.Container(content=small_text("还没有动作，先添加一个动作"), bgcolor=SURFACE, border_radius=12, padding=14),
        ], spacing=8), padding=14),
        card(ft.Row([
            make_button("复用历史训练", on_click=actions.reuse_history, icon=ft.Icons.HISTORY, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
            make_button("清空", on_click=actions.clear, icon=ft.Icons.DELETE_OUTLINE, bgcolor="#FCECEC", color=RED, expand=True),
        ], spacing=8), padding=12),
    ], spacing=0)


__all__ = ["EmptyTrainingActions", "PlannedTrainingActions", "build_empty_training", "build_planned_training"]
