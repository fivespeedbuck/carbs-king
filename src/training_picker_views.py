"""Exercise-library picker and help presentation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import flet as ft

from app_utils import to_float
from ui_components import GREEN, ORANGE, PRIMARY, PRIMARY_SOFT, RED, SUB, SURFACE, TEXT, make_button, single_line_font_size, small_text, thin_border


CUSTOM_CARDIO_METRIC_FIELDS = (
    "speed_kph",
    "incline_percent",
    "resistance_level",
    "cadence_rpm",
    "strides_per_minute",
    "stroke_rate_spm",
    "steps_per_minute",
)


def training_parameter_mode_state(
    recording_mode: str,
    *,
    is_new_custom: bool,
    distance_enabled: bool,
    cardio_metric_fields: Sequence[str],
) -> dict[str, Any]:
    """Return the visible parameter groups and applicable cardio metric keys."""
    mode = recording_mode if recording_mode in {"strength", "timed", "cardio"} else "strength"
    configured_metrics = tuple(key for key in cardio_metric_fields if key in CUSTOM_CARDIO_METRIC_FIELDS)
    metric_keys = configured_metrics or (CUSTOM_CARDIO_METRIC_FIELDS if is_new_custom and mode == "cardio" else ())
    return {
        "mode": mode,
        "strength": mode == "strength",
        "duration": mode in {"timed", "cardio"},
        "distance": mode == "cardio" and (distance_enabled or is_new_custom),
        "metric_keys": metric_keys if mode == "cardio" else (),
    }


def apply_training_parameter_visibility(state: Mapping[str, Any], *, strength, duration, distance, metrics) -> None:
    """Apply a mode state to the four parameter sections."""
    strength.visible = bool(state["strength"])
    duration.visible = bool(state["duration"])
    distance.visible = bool(state["distance"])
    metrics.visible = bool(state["metric_keys"])


def bind_training_parameter_mode(
    mode_input,
    *,
    is_new_custom: bool,
    distance_enabled: bool,
    cardio_metric_fields: Sequence[str],
    strength,
    duration,
    distance,
    metrics,
    request_update: Callable[[], None],
) -> Callable[[Any], None]:
    """Bind parameter visibility to Flet 0.85's real Dropdown on_select event."""

    def handle_select(event=None):
        event_control = getattr(event, "control", None)
        selected_mode = getattr(event_control, "value", None)
        if selected_mode is None:
            selected_mode = mode_input.value
        else:
            mode_input.value = selected_mode
        state = training_parameter_mode_state(
            selected_mode,
            is_new_custom=is_new_custom,
            distance_enabled=distance_enabled,
            cardio_metric_fields=cardio_metric_fields,
        )
        apply_training_parameter_visibility(
            state,
            strength=strength,
            duration=duration,
            distance=distance,
            metrics=metrics,
        )
        if event is not None:
            request_update()

    dropdown = getattr(mode_input, "field", mode_input)
    dropdown.on_select = handle_select
    handle_select()
    return handle_select


def bind_dialog_close_button(dialog: ft.AlertDialog, on_close: Callable[[Any], None]) -> ft.IconButton:
    """Bind the title X to an explicit 48dp close target."""
    title_controls = getattr(getattr(dialog, "title", None), "controls", [])
    close_button = title_controls[-1] if title_controls else None
    # Flet exposes IconButton as a control factory in some runtimes, rather
    # than a Python class suitable for ``isinstance``.
    if close_button is None or not hasattr(close_button, "on_click"):
        raise ValueError("dialog title must end with a close IconButton")
    close_button.width = 48
    close_button.height = 48
    close_button.on_click = on_close
    return close_button


def build_exercise_help(exercise: Mapping[str, Any], width: int, scroll_mode: Any) -> ft.Control:
    target = " · ".join(exercise.get("target_muscles", []))
    cues = [ft.Text(f"{index}. {text}", size=13, color=TEXT) for index, text in enumerate(exercise.get("cues", []), 1)]
    mistakes = [ft.Text(f"· {text}", size=13, color=SUB) for text in exercise.get("mistakes", [])]
    media_src = str(exercise.get("gif") or exercise.get("image") or "")
    media = ft.Container(
        content=ft.Image(src=media_src, fit="contain", height=210) if media_src else ft.Icon(ft.Icons.FITNESS_CENTER, size=56, color=GREEN),
        alignment=ft.Alignment.CENTER,
        bgcolor=SURFACE,
        border_radius=12,
        padding=8,
    )
    details = [
        media,
        ft.Text(f"器械 · {exercise.get('equipment', '其他')}", size=13, color=SUB),
        ft.Container(content=ft.Text(f"目标肌群 · {target}", size=13, color=GREEN, weight="bold"), bgcolor=SURFACE, border_radius=10, padding=10),
        ft.Text("动作要点", size=15, weight="bold", color=TEXT),
        *cues,
    ]
    if mistakes:
        details.extend([ft.Text("常见错误", size=15, weight="bold", color=ORANGE), *mistakes])
    return ft.Column(details, width=width, height=430, spacing=8, scroll=scroll_mode)


def build_exercise_card(
    exercise: Mapping[str, Any],
    usage: Mapping[str, Any],
    on_help: Callable[[Any], None],
    on_toggle: Callable[[Any], None],
    *,
    selected: bool = False,
    on_delete: Callable[[Any], None] | None = None,
    title_width: float = 140.0,
) -> ft.Control:
    weight = exercise.get("default_weight_kg")
    reps = exercise.get("default_reps")
    sets = exercise.get("default_sets")
    mode = str(exercise.get("recording_mode") or "strength")
    if mode == "cardio":
        default_text = "有氧 · 时长" + (" / 距离" if exercise.get("distance_enabled") else "")
    elif mode == "timed":
        default_text = "计时 · 分钟 / 秒"
    else:
        default_text = "自重" if weight is None else f"{to_float(weight):g} kg"
        default_text += f" × {reps} 次 / {sets} 组"
    usage_text = f"练过 {usage['session_count']} 次" if usage.get("session_count") else ""
    exercise_name = str(exercise.get("name") or "")
    title_size = single_line_font_size(
        exercise_name,
        title_width,
        maximum=14,
        minimum=10,
    )
    media_src = str(exercise.get("gif") or exercise.get("image") or "").strip()
    media = (
        ft.Image(
            src=media_src,
            fit="contain",
            gapless_playback=True,
            cache_width=160,
            cache_height=160,
            data="exercise-card-media-image",
        )
        if media_src
        else ft.Icon(ft.Icons.FITNESS_CENTER, size=30, color=GREEN)
    )
    return ft.Container(
        content=ft.Row([
            ft.Column([
                ft.Column([
                    # Every action name owns the same two-line slot, even when
                    # the visible text only needs one line. Long names shrink
                    # instead of wrapping and moving the bottom detail zone.
                    ft.Container(
                        content=ft.Text(
                            exercise_name,
                            size=title_size,
                            weight="bold",
                            color=TEXT,
                            max_lines=1,
                            overflow="ellipsis",
                            data="exercise-card-title",
                        ),
                        height=32,
                        alignment=ft.Alignment(-1, 0),
                    ),
                    ft.Container(
                        # Preserve one history line even for never-trained
                        # actions so bottom details match the in-session card.
                        content=ft.Text(usage_text or " ", size=12, color=SUB, max_lines=1, overflow="ellipsis"),
                        height=18,
                        alignment=ft.Alignment(-1, 0),
                        data="exercise-card-usage-placeholder",
                    ),
                ], spacing=1),
                # Keep equipment and prescription on the bottom baseline of
                # every grid card, independent of action-name length.
                ft.Column([
                    ft.Text(str(exercise.get("equipment") or "其他"), size=12, color=SUB, max_lines=1, overflow="ellipsis"),
                    ft.Text(default_text, size=12, color=SUB, max_lines=1, overflow="ellipsis"),
                ], spacing=1),
            ], expand=True, spacing=1, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(
                content=media,
                width=76,
                height=104,
                bgcolor="#FFFFFF",
                border_radius=8,
                alignment=ft.Alignment.CENTER,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                on_click=on_help,
                data="exercise-card-media",
            ),
            ft.Column([
                ft.IconButton(icon=ft.Icons.HELP_OUTLINE, tooltip="动作说明", icon_color=GREEN, width=44, height=44, icon_size=27, on_click=on_help),
                *([ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    tooltip="删除自定义动作",
                    icon_color=RED,
                    width=44,
                    height=44,
                    icon_size=25,
                    on_click=on_delete,
                )] if on_delete is not None else []),
                ft.IconButton(
                    icon=ft.Icons.CHECK_CIRCLE if selected else ft.Icons.ADD_CIRCLE_OUTLINE,
                    tooltip="取消选择" if selected else "选择动作",
                    icon_color="#FFFFFF" if selected else GREEN,
                    bgcolor=PRIMARY if selected else None,
                    width=44,
                    height=44,
                    icon_size=27,
                    on_click=on_toggle,
                ),
            ], width=44, spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
        bgcolor=PRIMARY_SOFT if selected else "#FFFFFF",
        border=thin_border(PRIMARY) if selected else thin_border(),
        border_radius=12,
        padding=10,
        ink=True,
        on_click=on_toggle,
        # Reserve explicit bottom space on the phone picker.  Without it the
        # prescription and add control read as visually glued to the card edge.
        height=176 if on_delete is not None else 164,
        expand=True,
    )


def build_exercise_grid_card(
    exercise: Mapping[str, Any],
    on_help: Callable[[Any], None],
    on_toggle: Callable[[Any], None],
    *,
    selected: bool = False,
) -> ft.Control:
    """Compact visual card used by the new offline exercise browser."""
    image_src = str(exercise.get("image") or "")
    picture = ft.Image(src=image_src, fit="contain", height=112) if image_src else ft.Icon(ft.Icons.FITNESS_CENTER, size=42, color=GREEN)
    return ft.Container(
        content=ft.Column([
            ft.Container(content=picture, height=118, alignment=ft.Alignment.CENTER),
            ft.Text("讲解", size=11, color=PRIMARY, weight="bold", on_click=on_help),
            ft.Text(str(exercise.get("name") or ""), size=14, weight="bold", color=TEXT),
            ft.Text(f"{exercise.get('equipment', '其他')} · {exercise.get('subgroup', '整体')}", size=12, color=SUB),
            ft.IconButton(icon=ft.Icons.CHECK_CIRCLE if selected else ft.Icons.ADD_CIRCLE_OUTLINE, icon_color="#FFFFFF" if selected else GREEN, bgcolor=PRIMARY if selected else None, width=42, height=42, on_click=on_toggle),
        ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        expand=True,
        bgcolor=PRIMARY_SOFT if selected else "#FFFFFF",
        border=thin_border(PRIMARY) if selected else thin_border(),
        padding=8,
    )


def build_category_rows(
    categories: Sequence[str],
    selected: str,
    on_select: Callable[[str], None],
) -> list[ft.Control]:
    buttons = [
        make_button(
            category,
            on_click=lambda e, value=category: on_select(value),
            bgcolor=PRIMARY if selected == category else PRIMARY_SOFT,
            color="#FFFFFF" if selected == category else GREEN,
            expand=True,
        )
        for category in categories
    ]
    return [ft.Row(buttons[:4], spacing=6), ft.Row(buttons[4:], spacing=6)]


def build_category_sidebar(
    categories: Sequence[str],
    selected: str,
    on_select: Callable[[str], None],
) -> list[ft.Control]:
    """Left-side category rail for the visual exercise browser."""
    display_labels = {"核心稳定": "核心"}
    return [
        ft.Container(
            content=ft.Text(
                display_labels.get(category, category),
                size=14,
                weight="bold" if selected == category else None,
                color="#FFFFFF" if selected == category else SUB,
                text_align="center",
                max_lines=1,
                overflow="ellipsis",
            ),
            bgcolor=PRIMARY if selected == category else None,
            border_radius=8,
            padding=ft.Padding(left=3, top=12, right=3, bottom=12),
            alignment=ft.Alignment.CENTER,
            on_click=lambda e, value=category: on_select(value),
            ink=True,
        )
        for category in categories
    ]


def build_sort_row(on_select: Callable[[str], None], selected: str = "frequent") -> ft.Control:
    return ft.Row([
        make_button("热门", on_click=lambda e: on_select("frequent"), bgcolor=PRIMARY if selected == "frequent" else PRIMARY_SOFT, color="#FFFFFF" if selected == "frequent" else GREEN, expand=True),
        make_button("最近", on_click=lambda e: on_select("recent"), bgcolor=PRIMARY if selected == "recent" else PRIMARY_SOFT, color="#FFFFFF" if selected == "recent" else GREEN, expand=True),
    ], spacing=6)


__all__ = [
    "CUSTOM_CARDIO_METRIC_FIELDS",
    "apply_training_parameter_visibility",
    "bind_dialog_close_button",
    "bind_training_parameter_mode",
    "build_category_rows",
    "build_category_sidebar",
    "build_exercise_card",
    "build_exercise_grid_card",
    "build_exercise_help",
    "build_sort_row",
    "training_parameter_mode_state",
]
