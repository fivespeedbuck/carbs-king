"""Completed training summary view."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from training_models import TrainingSession
from ui_components import GREEN, PRIMARY, PRIMARY_SOFT, RED, SUB, SURFACE, TEXT, card, make_button, section_title, small_text, thin_border


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
        padding=ft.Padding(left=8, top=8, right=8, bottom=4),
    )


def _completed_exercise_detail(exercise) -> str:
    mode = exercise.recording_mode
    if mode == "cardio":
        duration = max(0, int(exercise.duration_seconds or 0))
        parts = ["有氧", f"{duration // 60}:{duration % 60:02d}"]
        if exercise.distance_km is not None:
            parts.append(f"{exercise.distance_km:g} km")
        return " · ".join(parts)
    if mode == "timed":
        duration = max(0, int(exercise.duration_seconds or 0))
        return f"计时 · {duration // 60}:{duration % 60:02d}"
    completed_sets = [item for item in exercise.sets if item.completed]
    if not completed_sets:
        return "未完成正式组"
    last_set = completed_sets[-1]
    weight = "自重" if not last_set.weight_kg else f"{last_set.weight_kg:g} kg"
    reps = "--" if last_set.reps is None else str(last_set.reps)
    return f"{len(completed_sets)}组 · {weight} × {reps}"


def build_today_completed_training(
    sessions: Sequence[TrainingSession],
    actions: TrainingWorkspaceTabsActions,
) -> ft.Control:
    if not sessions:
        return card(ft.Column([
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
        exercise_rows = [
            ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(exercise.name or "未命名动作", size=14, weight="bold", color=TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(_completed_exercise_detail(exercise), size=12, color=SUB, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ], spacing=1, expand=True),
                    ft.Text(exercise.body_part or "", size=12, color=GREEN, weight="bold", max_lines=1),
                ], spacing=8),
                bgcolor=SURFACE,
                border_radius=6,
                padding=8,
            )
            for exercise in session.exercises
        ]
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
    rows = []
    for exercise in session.exercises:
        mode = exercise.recording_mode
        done = sum(1 for item in exercise.sets if item.completed)
        volume = sum((item.weight_kg or 0) * (item.reps or 0) for item in exercise.sets if item.completed)
        if mode == "cardio":
            duration = max(0, int(exercise.duration_seconds or 0))
            detail = f"{exercise.body_part} · 有氧 {duration // 60}:{duration % 60:02d}"
            value = f"{exercise.distance_km:g} km" if exercise.distance_km is not None else "已完成"
            for metric_key in exercise.cardio_metric_fields:
                if metric_key in exercise.cardio_metrics:
                    detail += f" · {_METRIC_LABELS.get(metric_key, metric_key)} {exercise.cardio_metrics[metric_key]:g}"
        elif mode == "timed":
            duration = max(0, int(exercise.duration_seconds or 0))
            detail = f"{exercise.body_part} · 计时 {duration // 60}:{duration % 60:02d}"
            value = "已完成" if exercise.completed else "未完成"
        else:
            detail = f"{exercise.body_part} · 已完成 {done}/{len(exercise.sets)} 组"
            value = f"{volume:g} kg"
        rows.append(ft.Container(
            content=ft.Row([
                ft.Column([ft.Text(exercise.name, size=15, weight="bold", color=TEXT), small_text(detail)], expand=True, spacing=3),
                ft.Text(value, size=15, weight="bold", color=PRIMARY),
            ]), bgcolor="#FFFFFF", border=thin_border(), border_radius=10, padding=12,
        ))
    return ft.Column([
        ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.EMOJI_EVENTS, size=48, color="#FFD166"),
                ft.Text(title, size=28, weight="bold", color="#FFFFFF"),
                ft.Row([
                    ft.Column([ft.Text(f"{duration_minutes:g}", size=26, weight="bold", color="#FFFFFF"), ft.Text("分钟", size=12, color="#EAFBF5", weight="bold")], horizontal_alignment="center", expand=True),
                    ft.Column([ft.Text(f"{completed_sets}/{planned_sets}", size=26, weight="bold", color="#FFFFFF"), ft.Text("完成组", size=12, color="#EAFBF5", weight="bold")], horizontal_alignment="center", expand=True),
                    ft.Column([ft.Text(f"{volume_kg:g}", size=26, weight="bold", color="#FFFFFF"), ft.Text("总容量 kg", size=12, color="#EAFBF5", weight="bold")], horizontal_alignment="center", expand=True),
                ], spacing=8),
            ], horizontal_alignment="center", spacing=12),
            bgcolor="#173E35", border_radius=12, padding=22, margin=8,
        ),
        card(ft.Column([section_title("动作明细"), *rows], spacing=8), padding=14),
        card(ft.Column([
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
