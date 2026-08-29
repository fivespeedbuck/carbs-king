"""Completed training summary view."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from training_models import TrainingSession
from ui_components import GREEN, PRIMARY, PRIMARY_SOFT, RED, SUB, SURFACE, TEXT, page_card, make_button, section_title, small_text, thin_border


_METRIC_LABELS = {
    "speed_kph": "速度", "incline_percent": "坡度", "resistance_level": "阻力",
    "cadence_rpm": "踏频", "strides_per_minute": "步频", "stroke_rate_spm": "桨频",
    "steps_per_minute": "爬楼步频",
}


@dataclass(frozen=True)
class TrainingSummaryActions:
    repeat: Callable[[Any], None]
    create_new: Callable[[Any], None]


@dataclass(frozen=True)
class TrainingWorkspaceTabsActions:
    select_current: Callable[[Any], None]
    select_completed: Callable[[Any], None]
    create_new: Callable[[Any], None]
    delete_session: Callable[[str], None]


def build_training_workspace_tabs(
    active_tab: str,
    completed_count: int,
    actions: TrainingWorkspaceTabsActions,
) -> ft.Control:
    return ft.Container(
        content=ft.Row([
            make_button(
                "当前训练",
                on_click=actions.select_current,
                bgcolor=PRIMARY if active_tab == "current" else PRIMARY_SOFT,
                color="#FFFFFF" if active_tab == "current" else GREEN,
                expand=True,
                height=48,
            ),
            make_button(
                f"今日已训练 {completed_count}",
                on_click=actions.select_completed,
                bgcolor=PRIMARY if active_tab == "completed" else PRIMARY_SOFT,
                color="#FFFFFF" if active_tab == "completed" else GREEN,
                expand=True,
                height=48,
            ),
        ], spacing=8),
        padding=ft.Padding(left=0, top=8, right=0, bottom=4),
    )


def _completed_exercise_detail(exercise) -> str:
    mode = exercise.recording_mode
    if mode == "cardio":
        duration = max(0, int(exercise.duration_seconds or 0))
        parts = ["有氧", f"{duration // 60}:{duration % 60:02d}"]
        if exercise.distance_km is not None:
            parts.append(f"{exercise.distance_km:g} km")
        for metric_key in exercise.cardio_metric_fields:
            if metric_key in exercise.cardio_metrics:
                parts.append(f"{_METRIC_LABELS.get(metric_key, metric_key)} {exercise.cardio_metrics[metric_key]:g}")
        return " · ".join(parts)
    if mode == "timed":
        duration = max(0, int(exercise.duration_seconds or 0))
        return f"计时 · {duration // 60}:{duration % 60:02d}"
    completed_sets = [item for item in exercise.sets if item.completed]
    if not completed_sets:
        return "未完成正式组"
    volume = sum((item.weight_kg or 0) * (item.reps or 0) for item in completed_sets)
    return f"已完成 {len(completed_sets)}/{len(exercise.sets)} 组 · 总容量 {volume:g} kg"


def _completed_strength_set_details(exercise) -> list[tuple[str, str]]:
    """Format every completed strength set without collapsing varied inputs."""
    details: list[tuple[str, str]] = []
    for fallback_order, training_set in enumerate(exercise.sets, 1):
        if not training_set.completed:
            continue
        order = training_set.order or fallback_order
        label = f"第 {order} 组" + (" · 热身" if training_set.warmup else "")
        reps = "--" if training_set.reps is None else str(training_set.reps)
        if training_set.weight_kg:
            volume = training_set.weight_kg * (training_set.reps or 0)
            value = f"{training_set.weight_kg:g} kg × {reps} 次 = {volume:g} kg"
        else:
            value = f"自重 × {reps} 次"
        details.append((label, value))
    return details


def _strength_set_detail_controls(exercise) -> list[ft.Control]:
    return [
        # Keep the label and actual value on separate lines. This gives the
        # right-side action total its own width and prevents long set text
        # from being compressed or ellipsized on a phone.
        ft.Column([
            ft.Text(label, size=12, color=SUB, weight="bold"),
            ft.Text(value, size=12, color=TEXT, weight="bold"),
        ], spacing=0, tight=True)
        for label, value in _completed_strength_set_details(exercise)
    ]


def _summary_metric_number_size(values: Sequence[str]) -> int:
    """Keep four summary numbers visually aligned on a compact phone row."""
    longest = max(sum(1 if char.isdigit() else 0.5 for char in value) for value in values)
    if longest <= 4.5:
        return 26
    if longest <= 5.5:
        return 20
    return 18


def _exercise_result_value(exercise) -> str:
    if exercise.recording_mode == "cardio":
        if not exercise.completed:
            return "未完成"
        return f"{exercise.distance_km:g} km" if exercise.distance_km is not None else "已完成"
    if exercise.recording_mode == "timed":
        return "已完成" if exercise.completed else "未完成"
    volume = sum(
        (item.weight_kg or 0) * (item.reps or 0)
        for item in exercise.sets
        if item.completed
    )
    return f"{volume:g} kg"


def _exercise_result_card(exercise, *, show_value: bool, nested: bool = False) -> ft.Control:
    details = _strength_set_detail_controls(exercise) if exercise.recording_mode == "strength" else []
    trailing = _exercise_result_value(exercise) if show_value else (exercise.body_part or "")
    if show_value and not nested:
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([
                        ft.Text(exercise.name, size=15, weight="bold", color=TEXT),
                        small_text(_completed_exercise_detail(exercise)),
                    ], expand=True, spacing=3),
                    ft.Text(trailing, size=15, weight="bold", color=PRIMARY),
                ]),
                *details,
            ], spacing=6),
            bgcolor="#FFFFFF",
            border=thin_border(),
            border_radius=10,
            padding=12,
            data="training-result-exercise-card",
        )
    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text(
                    exercise.name or "未命名动作",
                    size=14 if nested else 15,
                    weight="bold",
                    color=TEXT,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                ),
                ft.Text(
                    trailing,
                    size=12 if nested else 14,
                    color=GREEN if not show_value else PRIMARY,
                    weight="bold",
                    max_lines=1,
                ),
            ], spacing=8),
            ft.Text(_completed_exercise_detail(exercise), size=12, color=SUB),
            *details,
        ], spacing=3 if nested else 5),
        bgcolor=SURFACE if nested else "#FFFFFF",
        border=None if nested else thin_border(),
        border_radius=6 if nested else 10,
        padding=8 if nested else 12,
        data="training-result-exercise-card",
    )


def _training_result_blocks(session: TrainingSession, *, show_value: bool) -> list[ft.Control]:
    groups = {group.id: group for group in session.exercise_groups}
    group_id_by_member = {
        member_id: group.id
        for group in session.exercise_groups
        for member_id in group.exercise_ids
    }
    by_id = {exercise.id: exercise for exercise in session.exercises}
    rendered: set[str] = set()
    blocks: list[ft.Control] = []
    for exercise in session.exercises:
        if exercise.id in rendered:
            continue
        group = groups.get(exercise.group_id or group_id_by_member.get(exercise.id, ""))
        member_ids = [member_id for member_id in group.exercise_ids if member_id in by_id] if group else []
        if group and len(member_ids) >= 2:
            if exercise.id != member_ids[0]:
                continue
            rendered.update(member_ids)
            group_label = "超级组" if group.group_type == "superset" else "复合组"
            blocks.append(ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.LINK, color=PRIMARY, size=20),
                        ft.Column([
                            ft.Text(f"{group_label} · {len(member_ids)} 个动作", size=15, weight="bold", color=TEXT),
                            small_text("组内动作按组合顺序完成"),
                        ], spacing=1, expand=True),
                    ], spacing=8),
                    *[
                        _exercise_result_card(by_id[member_id], show_value=show_value, nested=True)
                        for member_id in member_ids
                    ],
                ], spacing=6),
                bgcolor="#FFFFFF",
                border=thin_border(PRIMARY),
                border_radius=10,
                padding=10,
                data="training-result-group-card",
            ))
            continue
        rendered.add(exercise.id)
        blocks.append(_exercise_result_card(exercise, show_value=show_value, nested=not show_value))
    return blocks


def build_today_completed_training(
    sessions: Sequence[TrainingSession],
    actions: TrainingWorkspaceTabsActions,
) -> ft.Control:
    if not sessions:
        return page_card(ft.Column([
            section_title("今日已训练内容"),
            small_text("今天还没有完成的训练。"),
            make_button("开始今天的训练", on_click=actions.create_new, icon=ft.Icons.ADD, expand=True),
        ], spacing=10), padding=14)

    session_cards: list[ft.Control] = []
    for index, session in enumerate(sessions, 1):
        body_parts: list[str] = []
        for exercise in session.exercises:
            part = str(exercise.body_part or "").strip()
            if part and part not in body_parts and part != "自定义":
                body_parts.append(part)
        title = "+".join(body_parts) or "训练"
        duration = session.total_duration_min or 0
        exercise_rows = _training_result_blocks(session, show_value=False)
        session_cards.append(ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(f"第 {index} 练 · {title}", size=16, weight="bold", color=TEXT, expand=True),
                    ft.Text(f"{duration:g} 分钟", size=12, color=SUB, weight="bold"),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        tooltip="删除本场训练",
                        icon_color=RED,
                        width=40,
                        height=40,
                        on_click=lambda e, session_id=session.id: actions.delete_session(session_id),
                    ),
                ], spacing=8),
                *exercise_rows,
            ], spacing=6),
            bgcolor="#FFFFFF",
            border=thin_border(),
            border_radius=8,
            padding=10,
        ))

    return ft.Column([
        ft.Container(
            content=ft.Row([
                ft.Column([
                    section_title("今日已训练内容"),
                    small_text(f"已完成 {len(sessions)} 场，开始二练不会覆盖已有记录。"),
                ], spacing=2, expand=True),
                make_button("开始二练", on_click=actions.create_new, icon=ft.Icons.ADD, bgcolor=PRIMARY_SOFT, color=GREEN),
            ], spacing=8),
            padding=12,
        ),
        ft.Column(session_cards, spacing=8),
    ], spacing=0)


def build_training_summary(
    session: TrainingSession,
    *,
    title: str,
    duration_minutes: float,
    completed_sets: int,
    planned_sets: int,
    volume_kg: float,
    advice: str,
    actions: TrainingSummaryActions,
) -> ft.Control:
    rows = _training_result_blocks(session, show_value=True)
    cardio_exercises = [exercise for exercise in session.exercises if exercise.recording_mode == "cardio"]
    cardio_duration_minutes = sum(max(0, exercise.duration_seconds or 0) for exercise in cardio_exercises) / 60
    metric_values = [f"{duration_minutes:g}", f"{completed_sets}/{planned_sets}", f"{volume_kg:g}"]
    if cardio_exercises:
        metric_values.append(f"{cardio_duration_minutes:g}")
    number_size = _summary_metric_number_size(metric_values) if cardio_exercises else 26
    metrics: list[ft.Control] = [
        ft.Column([ft.Text(metric_values[0], size=number_size, weight="bold", color="#FFFFFF", no_wrap=True), ft.Text("分钟", size=12, color="#EAFBF5", weight="bold")], horizontal_alignment="center", expand=True),
        ft.Column([ft.Text(metric_values[1], size=number_size, weight="bold", color="#FFFFFF", no_wrap=True), ft.Text("完成项目", size=12, color="#EAFBF5", weight="bold")], horizontal_alignment="center", expand=True),
        ft.Column([ft.Text(metric_values[2], size=number_size, weight="bold", color="#FFFFFF", no_wrap=True), ft.Text("总容量 kg", size=12, color="#EAFBF5", weight="bold")], horizontal_alignment="center", expand=True),
    ]
    if cardio_exercises:
        metrics.append(ft.Column([
            ft.Text(metric_values[3], size=number_size, weight="bold", color="#FFFFFF", no_wrap=True),
            ft.Text("有氧时间", size=12, color="#EAFBF5", weight="bold"),
        ], horizontal_alignment="center", expand=True))
    return ft.Column([
        ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.EMOJI_EVENTS, size=48, color="#FFD166"),
                ft.Text(title, size=28, weight="bold", color="#FFFFFF"),
                ft.Row(metrics, spacing=8),
            ], horizontal_alignment="center", spacing=12),
            bgcolor=PRIMARY, border_radius=12, padding=22,
            margin=ft.Margin(left=0, top=8, right=0, bottom=8),
        ),
        page_card(ft.Column([section_title("动作明细"), *rows], spacing=8), padding=14),
        page_card(ft.Column([
            section_title("练后建议"),
            ft.Text(advice, size=14, color=TEXT),
            ft.Row([
                make_button("再练一次", on_click=actions.repeat, icon=ft.Icons.REPLAY, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                make_button("新训练", on_click=actions.create_new, icon=ft.Icons.ADD, expand=True),
            ], spacing=8),
        ], spacing=10), padding=14),
    ], spacing=0)


__all__ = [
    "TrainingSummaryActions",
    "TrainingWorkspaceTabsActions",
    "build_today_completed_training",
    "build_training_summary",
    "build_training_workspace_tabs",
]
