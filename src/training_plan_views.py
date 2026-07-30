"""Empty and planned training workspace views."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import flet as ft

from app_utils import to_float
from ui_components import CARD, GREEN, ON_PRIMARY, PRIMARY, PRIMARY_SOFT, RED, SUB, SURFACE, TEXT, page_card, make_button, section_title, small_text, thin_border


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
                ft.Container(
                    content=ft.Icon(ft.Icons.FITNESS_CENTER, size=42, color=PRIMARY),
                    width=72,
                    height=72,
                    bgcolor=CARD,
                    border_radius=20,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Text("今天练什么？", size=25, weight="bold", color=ON_PRIMARY),
                ft.Text("从上次训练继续，或创建一场自由训练", size=14, color=ON_PRIMARY, weight="bold", text_align="center"),
                ft.Row([
                    make_button("复用历史训练", on_click=actions.reuse_history, bgcolor=CARD, color=GREEN, expand=True),
                    make_button("自由训练", on_click=actions.create_free, bgcolor=CARD, color=GREEN, expand=True),
                ], spacing=8),
            ], horizontal_alignment="center", spacing=14),
            bgcolor=PRIMARY, border_radius=12, padding=24,
            margin=ft.Margin(left=0, top=8, right=0, bottom=8),
        ),
        page_card(ft.Column([
            section_title("训练准备"),
            small_text("添加动作后即可开始，重量与次数会完整保存。"),
            make_button("添加第一个动作", on_click=actions.add_first, icon=ft.Icons.ADD, expand=True, height=54),
        ], spacing=10), padding=14),
    ], spacing=0)


@dataclass(frozen=True)
class PlannedTrainingActions:
    start: Callable[[Any], None]
    add_exercise: Callable[[Any], None]
    delete_exercise: Callable[[str], None]
    reuse_history: Callable[[Any], None]
    clear: Callable[[Any], None]
    group_exercise: Callable[[str], None]
    delete_group: Callable[[str], None]
    show_help: Callable[[str], None]
    edit_exercise: Callable[[str], None]
    reorder_exercise: Callable[[str, str], None]
    reorder_group_member: Callable[[str, str], None] | None = None
    remove_group_member: Callable[[str], None] | None = None


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


def _drag_handle(*, size: int = 32) -> ft.Control:
    """Visible handle inside a native reorderable item.

    The list itself owns the drag gesture. On Android the whole card can be
    long-pressed; this nested handle also remains an explicit drag affordance.
    """
    return ft.ReorderableDragHandle(content=ft.Container(
        content=ft.Icon(ft.Icons.DRAG_HANDLE, color=SUB, tooltip="拖动排序"),
        width=size,
        height=size,
        alignment=ft.Alignment.CENTER,
        border_radius=size // 2,
    ))


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


def build_action_arrangement_card(
    exercise: Mapping[str, Any],
    position: int,
    *,
    edit_exercise: Callable[[str], None],
    group_exercise: Callable[[str], None],
    delete_exercise: Callable[[str], None],
    completed_count: int | None = None,
) -> ft.Container:
    """Build the one shared normal action card used before and during training."""
    exercise_id = str(exercise.get("id") or "")
    summary, prescription = _exercise_detail_lines(exercise)
    detail_controls: list[ft.Control] = [
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
    ]
    if completed_count is not None:
        detail_controls.append(small_text(f"已完成 {completed_count} 组"))
    return ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Text(str(position), color="#FFFFFF", weight="bold"),
                width=36,
                height=36,
                bgcolor=PRIMARY,
                border_radius=10,
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column(detail_controls, expand=True, spacing=1, tight=True),
            ft.Column([
                ft.Row([
                    _fixed_icon_button(
                        ft.Icons.EDIT_OUTLINED,
                        "编辑参数",
                        GREEN,
                        lambda e, value=exercise_id: edit_exercise(value),
                        size=32,
                    ),
                    _fixed_icon_button(
                        ft.Icons.ADD,
                        "组成超级组或复合组",
                        GREEN,
                        lambda e, value=exercise_id: group_exercise(value),
                        size=32,
                    ),
                ], spacing=0, tight=True),
                ft.Row([
                    _drag_handle(size=32),
                    _fixed_icon_button(
                        ft.Icons.DELETE_OUTLINE,
                        "删除动作",
                        RED,
                        lambda e, value=exercise_id: delete_exercise(value),
                        size=32,
                    ),
                ], spacing=0, tight=True),
            ], spacing=0, tight=True),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor="#FFFFFF",
        border=thin_border(),
        border_radius=10,
        padding=10,
        data="action-arrangement-card",
        key=f"action-{exercise_id}",
    )


def build_action_arrangement_list(
    session: Mapping[str, Any],
    *,
    edit_exercise: Callable[[str], None],
    group_exercise: Callable[[str], None],
    delete_exercise: Callable[[str], None],
    delete_group: Callable[[str], None],
    reorder_exercise: Callable[[str, str], None],
    reorder_group_member: Callable[[str, str], None] | None = None,
    remove_group_member: Callable[[str], None] | None = None,
    completed_counts: Mapping[str, int] | None = None,
    max_height: int = 540,
    data: str = "action-arrangement-reorder-list",
) -> ft.ReorderableListView:
    """Build the shared reorderable action list, including visible group blocks."""
    exercises = session.get("exercises", []) if isinstance(session.get("exercises", []), list) else []
    groups = {
        str(group.get("id") or ""): group
        for group in session.get("exercise_groups", [])
        if isinstance(group, Mapping)
    } if isinstance(session.get("exercise_groups"), list) else {}
    group_id_by_member = {
        str(member_id): group_id
        for group_id, group in groups.items()
        for member_id in group.get("exercise_ids", [])
        if str(member_id)
    }
    by_id = {str(item.get("id") or ""): item for item in exercises if isinstance(item, Mapping)}
    rendered: set[str] = set()
    baseline_order: list[str] = []
    block_controls: list[ft.Control] = []
    estimated_height = 0
    member_card_height = 80 if completed_counts is not None else 66
    member_gap = 8

    def register_block(block_id: str, row_card: ft.Control, height: int, *, full_card_drag: bool = True) -> None:
        nonlocal estimated_height
        baseline_order.append(block_id)
        block_controls.append(
            ft.ReorderableDragHandle(
                content=row_card,
                key=f"reorder-{block_id}",
                data="action-arrangement-drag-region",
            )
            if full_card_drag else row_card
        )
        estimated_height += height

    def member_reorder_list(group_id: str, member_ids: list[str], member_rows: list[ft.Control]) -> ft.ReorderableListView:
        order = list(member_ids)
        member_item_extent = member_card_height + member_gap
        member_list_height = max(1, len(member_rows) * member_item_extent - member_gap)

        def reorder_members(event: Any) -> None:
            old_index = int(getattr(event, "old_index", -1))
            new_index = int(getattr(event, "new_index", -1))
            if not (0 <= old_index < len(order) and 0 <= new_index < len(order)):
                return
            dragged_id = order.pop(old_index)
            target_id = order[new_index - 1] if old_index < new_index else order[new_index]
            order.insert(new_index, dragged_id)
            if reorder_group_member is not None:
                reorder_group_member(dragged_id, target_id)

        return ft.ReorderableListView(
            controls=[
                ft.ReorderableDragHandle(
                    content=row,
                    key=f"group-member-{group_id}-{member_id}",
                    data="action-arrangement-group-member-drag-region",
                )
                for member_id, row in zip(member_ids, member_rows)
            ],
            spacing=0,
            item_extent=member_item_extent,
            show_default_drag_handles=False,
            build_controls_on_demand=False,
            auto_scroll=False,
            height=max(1, member_list_height),
            on_reorder=reorder_members,
            data="action-arrangement-group-member-list",
        )

    def reorder_blocks(event: Any) -> None:
        old_index = int(getattr(event, "old_index", -1))
        new_index = int(getattr(event, "new_index", -1))
        if not (0 <= old_index < len(baseline_order) and 0 <= new_index < len(baseline_order)):
            return
        dragged_id = baseline_order[old_index]
        target_id = baseline_order[new_index]
        moved_id = baseline_order.pop(old_index)
        baseline_order.insert(new_index, moved_id)
        moved_control = exercise_list.controls.pop(old_index)
        exercise_list.controls.insert(new_index, moved_control)
        reorder_exercise(dragged_id, target_id)

    for index, exercise in enumerate(exercises):
        exercise_id = str(exercise.get("id") or "")
        if not exercise_id or exercise_id in rendered:
            continue
        group = groups.get(
            str(exercise.get("group_id") or group_id_by_member.get(exercise_id, ""))
        )
        if group:
            member_ids = [str(item) for item in group.get("exercise_ids", []) if str(item) in by_id]
            if exercise_id != (member_ids[0] if member_ids else ""):
                continue
            rendered.update(member_ids)
            title = "超级组" if group.get("group_type") == "superset" else "复合组"
            member_rows = []
            for member_index, member_id in enumerate(member_ids, 1):
                member = by_id[member_id]
                member_details: list[ft.Control] = [
                    ft.Text(str(member.get("name", "")), size=15, weight="bold", color=TEXT),
                    small_text(_exercise_detail(member)),
                ]
                if completed_counts is not None:
                    member_details.append(small_text(f"已完成 {completed_counts.get(member_id, 0)} 组"))
                member_card = ft.Container(
                    content=ft.Row([
                        ft.Container(content=ft.Text(str(member_index), color="#FFFFFF", weight="bold"), width=28, height=28, bgcolor=PRIMARY, border_radius=8, alignment=ft.Alignment.CENTER),
                        ft.Column(member_details, expand=True, spacing=2),
                        _drag_handle(size=32),
                        _fixed_icon_button(ft.Icons.EDIT_OUTLINED, "编辑参数", GREEN, lambda e, value=member_id: edit_exercise(value)),
                        _fixed_icon_button(
                            ft.Icons.LINK_OFF,
                            "移出组合",
                            RED,
                            lambda e, value=member_id: remove_group_member(value) if remove_group_member is not None else None,
                            size=32,
                        ),
                    ], spacing=8),
                    height=member_card_height,
                    bgcolor=SURFACE,
                    border_radius=8,
                    padding=8,
                )
                member_rows.append(ft.Container(
                    content=member_card,
                    height=member_card_height + member_gap,
                    padding=ft.Padding(left=0, top=0, right=0, bottom=member_gap),
                ))
            member_list = member_reorder_list(str(group.get("id") or ""), member_ids, member_rows)
            group_header = ft.ReorderableDragHandle(
                content=ft.Row([
                    ft.Column([
                        ft.Text(f"{title} · {len(member_ids)} 个动作", size=16, weight="bold", color=TEXT),
                        small_text("组内动作会绑定在一个大框内排序和训练"),
                    ], spacing=2, expand=True),
                    _drag_handle(size=40),
                    _fixed_icon_button(ft.Icons.ADD, "编辑组合", GREEN, lambda e, value=exercise_id: group_exercise(value)),
                    _fixed_icon_button(ft.Icons.LINK_OFF, "解除组合", RED, lambda e, value=exercise_id: delete_group(value)),
                ], spacing=8),
                key=f"group-drag-{exercise_id}",
                data="action-arrangement-group-drag-region",
            )
            row_card = ft.Container(
                content=ft.Column([
                    group_header,
                    member_list,
                ], spacing=8),
                bgcolor="#FFFFFF",
                border=thin_border(PRIMARY),
                border_radius=10,
                padding=12,
                data="action-arrangement-group-card",
                key=f"action-group-{exercise_id}",
            )
            # Group members contain a title, prescription, completion line,
            # and an edit button; the normal card estimate is too short and
            # clips the last member inside the reorder viewport.
            register_block(
                exercise_id,
                row_card,
                92 + member_list.height,
                full_card_drag=False,
            )
            continue

        rendered.add(exercise_id)
        row_card = build_action_arrangement_card(
            exercise,
            index + 1,
            edit_exercise=edit_exercise,
            group_exercise=group_exercise,
            delete_exercise=delete_exercise,
            completed_count=(completed_counts.get(exercise_id, 0) if completed_counts is not None else None),
        )
        register_block(exercise_id, row_card, 94)

    # ``ft.Container`` is not a stable runtime class in every supported Flet
    # environment, so do not use it in ``isinstance``.  These controls are
    # constructed above and are either a drag handle containing a card or a
    # group card itself; both support the margin property.
    for block_control in block_controls[:-1]:
        block_card = (
            block_control.content
            if getattr(block_control, "data", None) == "action-arrangement-drag-region"
            else block_control
        )
        block_card.margin = ft.Margin(left=0, top=0, right=0, bottom=8)

    exercise_list = ft.ReorderableListView(
        controls=block_controls,
        spacing=0,
        show_default_drag_handles=False,
        build_controls_on_demand=False,
        auto_scroll=True,
        height=min(max_height, max(94, estimated_height + max(0, len(block_controls) - 1) * 8)),
        on_reorder=reorder_blocks,
        data=data,
    )

    return exercise_list


def build_planned_training(session: Mapping[str, Any], actions: PlannedTrainingActions) -> ft.Control:
    exercises = session.get("exercises", []) if isinstance(session.get("exercises", []), list) else []
    exercise_list = build_action_arrangement_list(
        session,
        edit_exercise=actions.edit_exercise,
        group_exercise=actions.group_exercise,
        delete_exercise=actions.delete_exercise,
        delete_group=actions.delete_group,
        reorder_exercise=actions.reorder_exercise,
        reorder_group_member=actions.reorder_group_member,
        remove_group_member=actions.remove_group_member,
    )

    return ft.Column([
        ft.Container(content=ft.Column([
            ft.Row([ft.Column([small_text("训练计划", color=ON_PRIMARY), ft.Text("当前的训练", size=25, weight="bold", color=ON_PRIMARY)], spacing=2), ft.Icon(ft.Icons.FITNESS_CENTER, size=42, color=ON_PRIMARY)], alignment="spaceBetween"),
            ft.Text(f"{len(exercises)} 个动作 · {sum(len(item.get('sets', [])) for item in exercises if item.get('recording_mode', 'strength') == 'strength')} 个力量组", size=14, color=ON_PRIMARY, weight="bold"),
            make_button("开始训练", on_click=actions.start, icon=ft.Icons.PLAY_ARROW, bgcolor=CARD, color=GREEN, expand=True, height=58),
        ], spacing=12), bgcolor=PRIMARY, border_radius=12, padding=20,
            margin=ft.Margin(left=0, top=8, right=0, bottom=8)),
        page_card(ft.Column([
            ft.Row([section_title("动作安排"), make_button("添加动作", on_click=actions.add_exercise, icon=ft.Icons.ADD, bgcolor=PRIMARY_SOFT, color=GREEN)], alignment="spaceBetween"),
            small_text("长按卡片或移动手柄排序；经过其他动作时会显示平滑换位。"),
            exercise_list if exercises else ft.Container(content=small_text("还没有动作，先添加一个动作"), bgcolor=SURFACE, border_radius=12, padding=14),
        ], spacing=8), padding=14),
        page_card(ft.Row([
            make_button("复用历史训练", on_click=actions.reuse_history, icon=ft.Icons.HISTORY, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
            make_button("清空", on_click=actions.clear, icon=ft.Icons.DELETE_OUTLINE, bgcolor="#FCECEC", color=RED, expand=True),
        ], spacing=8), padding=12),
    ], spacing=0)


__all__ = [
    "EmptyTrainingActions",
    "PlannedTrainingActions",
    "build_action_arrangement_card",
    "build_action_arrangement_list",
    "build_empty_training",
    "build_planned_training",
]
