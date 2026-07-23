"""Training feature controller for plans, sessions, clocks, rest, and history reuse."""

from __future__ import annotations

import copy
import datetime
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from app_defaults import ABS_ACTIONS, FATIGUE_OPTIONS, INTENSITY_OPTIONS, TRAINING_TARGETS
from app_state import AppState
from app_utils import to_float
from analytics_service import summarize_daily_training
from controller_runtime import ControllerRuntime
from exercise_library import (
    EXERCISE_CATEGORIES, exercise_catalog, load_custom_exercises,
    save_custom_exercise, search_exercises,
)
from form_views import FormViewContext, build_dialog, build_full_form_sheet
from repositories import AppRepositories
from training_clock_service import finalize_session_clock, session_elapsed_seconds
from training_experience_service import (
    BODY_PART_ORDER, adjust_weight_kg, adjust_rest_cycle, copy_whole_session, create_exercise_group, exercise_usage_stats,
    finish_rest_cycle, format_weight_kg, history_training_cards, normalize_weight_input,
    next_group_work, normalize_exercise_groups, pause_rest_cycle, rest_remaining_seconds,
    reorder_session_exercise_blocks, resume_rest_cycle, skip_rest_cycle, sort_exercises, start_rest_cycle,
    undo_completed_set_result,
)
from training_models import TrainingSession, normalize_recording_mode
from training_picker_views import (
    CUSTOM_CARDIO_METRIC_FIELDS, bind_dialog_close_button, bind_training_parameter_mode,
    build_category_rows, build_exercise_card, build_exercise_help, build_sort_row,
)
from training_plan_views import EmptyTrainingActions, PlannedTrainingActions, build_empty_training, build_planned_training
from training_summary_views import (
    TrainingSummaryActions,
    TrainingWorkspaceTabsActions,
    build_today_completed_training,
    build_training_summary,
    build_training_workspace_tabs,
)
from training_service import (
    append_session_once, completed_work_count, find_active_daily_session, is_rapid_repeat,
    planned_work_count, raw_training_sessions, recommend_carb_day, session_completion_state,
    rest_required_after_work, session_summary_title, session_volume, session_work_progress,
)
from training_views import ActiveTrainingActions, ActiveTrainingModel, build_active_training
from ui_components import (
    GREEN, PRIMARY, PRIMARY_SOFT, RED, SUB, SURFACE, TEXT, card,
    make_button, mobile_dropdown, mobile_text_field, responsive_field_grid,
    section_title, small_text, thin_border, three_field_grid, two_field_grid,
)


CARDIO_METRIC_LABELS = {
    "speed_kph": "速度 km/h",
    "incline_percent": "坡度 %",
    "resistance_level": "阻力/档位",
    "cadence_rpm": "踏频 rpm",
    "strides_per_minute": "步频 spm",
    "stroke_rate_spm": "桨频 spm",
    "steps_per_minute": "爬楼步频 spm",
}


@dataclass(frozen=True)
class TrainingControllerDependencies:
    state: AppState
    repositories: AppRepositories
    records: dict[str, Any]
    runtime: ControllerRuntime
    persist_daily: Callable[..., None]
    persist_training_session: Callable[[str, dict[str, Any]], None]
    load_date: Callable[..., None]
    rest_notifier: Any
    training_clock_refs: dict[str, Any]
    exercise_drag_state: dict[str, Any]
    keyboard_number: Any
    scroll_hidden: Any
    current_scroll: Callable[[], float]
    scroll_to: Callable[..., None]
    viewport_height: Callable[[], float]


@dataclass
class TrainingController:
    render_page: Callable[[], ft.Control]
    session_data: Callable[[], dict[str, Any] | None]
    session_model: Callable[[], TrainingSession | None]
    find_active_session_date: Callable[[], str | None]
    resume_session_date: Callable[[str], None]
    elapsed_seconds: Callable[..., int]
    clock_text: Callable[[int], str]
    complete_rest_if_elapsed: Callable[..., bool]
    training_carb_warning: Callable[[], str]
    restore_cursor: Callable[[], None]


def create_training_controller(deps: TrainingControllerDependencies) -> TrainingController:
    state = deps.state
    records = deps.records
    runtime = deps.runtime
    page = runtime.page
    refresh = runtime.refresh
    snack = runtime.snack
    set_view = runtime.navigate
    open_control = runtime.open_control
    close_control = runtime.close_control
    responsive_width = runtime.responsive_width
    save_current = deps.persist_daily
    save_training_session = deps.persist_training_session
    load_record_for_date = deps.load_date
    rest_notifier = deps.rest_notifier
    training_clock_refs = deps.training_clock_refs
    exercise_drag_state = deps.exercise_drag_state
    _KEYBOARD_NUMBER = deps.keyboard_number
    _SCROLL_HIDDEN = deps.scroll_hidden
    completion_prompt = {"key": ""}
    active_cursor = {"session_id": ""}
    workspace_tab = {"value": "current"}

    def safe_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def normalized_session_exercises(session):
        """Keep the active cursor on JSON objects after legacy/refactor imports."""
        if not isinstance(session, dict):
            return []
        raw_exercises = session.get("exercises", [])
        exercises = [item for item in raw_exercises if isinstance(item, dict)] if isinstance(raw_exercises, list) else []
        changed = exercises != raw_exercises
        for exercise in exercises:
            if normalize_recording_mode(exercise.get("recording_mode")) != "strength":
                continue
            raw_sets = exercise.get("sets", [])
            sets = [item for item in raw_sets if isinstance(item, dict)] if isinstance(raw_sets, list) else []
            if sets != raw_sets:
                exercise["sets"] = sets
                changed = True
        if changed:
            session["exercises"] = exercises
            session["exercise_groups"] = normalize_exercise_groups(
                exercises,
                session.get("exercise_groups", []),
            )
        return exercises

    def first_pending_set_index(exercise, start_index=0):
        if not isinstance(exercise, dict):
            return None
        if normalize_recording_mode(exercise.get("recording_mode")) != "strength":
            return 0 if not exercise.get("completed") else None
        sets = exercise.get("sets", [])
        if not isinstance(sets, list):
            return None
        for index in range(max(0, safe_int(start_index)), len(sets)):
            training_set = sets[index]
            if isinstance(training_set, dict) and not training_set.get("completed"):
                return index
        return None

    def move_cursor_to_pending(exercises, start_index=0, start_set_index=0):
        for exercise_index in range(max(0, safe_int(start_index)), len(exercises)):
            pending_set = first_pending_set_index(
                exercises[exercise_index],
                start_set_index if exercise_index == start_index else 0,
            )
            if pending_set is None:
                continue
            state["training_exercise_index"] = exercise_index
            state["training_set_index"] = pending_set
            return True
        return False

    def dialog_base(title, content, actions=None, on_close=None):
        return build_dialog(title, content, actions=actions, on_close=on_close)

    def full_form_sheet(title, controls, on_save, save_label="保存"):
        return build_full_form_sheet(
            FormViewContext(close_control=close_control, scroll_mode=_SCROLL_HIDDEN),
            title,
            controls,
            on_save,
            save_label,
        )

    def training_signature():
        training = state.get("training", {})
        signature_data = {
            "summary_note": str(training.get("summary_note", "")),
            "targets": training.get("targets", []),
            "session": training.get("session"),
            "sessions": training.get("sessions", []),
        }
        return json.dumps(signature_data, ensure_ascii=False, sort_keys=True)

    def training_carb_warning():
        training = state.get("training", {})
        if training.get("carb_reminder_dismissed_signature") == training_signature():
            return ""
        recommended = recommend_carb_day(training)
        current = state.get("day_type")
        if recommended and recommended != current:
            summary = summarize_daily_training({"training": training})
            parts = summary.get("body_part_label") or "当前训练安排"
            return f"{parts}按你的碳循环规则更适合{recommended}，当前是{current}"
        return ""

    def open_training_dialog():
        if len(state["training"]["targets"]) >= 3:
            snack("每天最多记录 3 个训练目标")
            return

        raw_width = to_float(getattr(page, "width", None), 430)
        dialog_width = max(260, min(340, int(raw_width) - 56))
        dlg = None

        def target_button(name):
            return ft.Container(
                content=ft.Text(name, size=14, weight="bold", color=TEXT, text_align="center"),
                bgcolor="#FFFFFF",
                border_radius=8,
                padding=12,
                on_click=lambda e, n=name: (close_control(dlg), open_training_detail_dialog(n)),
                expand=True,
            )

        rows = []
        for i in range(0, len(TRAINING_TARGETS), 3):
            row_items = TRAINING_TARGETS[i:i+3]
            rows.append(ft.Row([target_button(x) for x in row_items], spacing=8))

        content = ft.Column(rows, width=dialog_width, height=360, spacing=8, scroll=_SCROLL_HIDDEN)

        dlg = dialog_base(
            "选择训练目标",
            content,
            [],
            on_close=lambda e: close_control(dlg),
        )
        open_control(dlg)

    def open_training_detail_dialog(selected_target):
        raw_width = to_float(getattr(page, "width", None), 430)
        dialog_width = max(260, min(340, int(raw_width) - 56))
        cardio_targets = ["跑步", "徒步", "游泳", "骑行", "打球"]
        dlg = None

        note = mobile_text_field("备注", width=dialog_width)
        intensity = mobile_dropdown("训练强度", "恢复" if selected_target == "休息" else "中等", [ft.dropdown.Option(x) for x in INTENSITY_OPTIONS], width=dialog_width)

        incline = mobile_text_field("坡度 %", keyboard_type=_KEYBOARD_NUMBER, expand=True)
        speed = mobile_text_field("速度 km/h", keyboard_type=_KEYBOARD_NUMBER, expand=True)
        climb_minutes = mobile_text_field("时长 min", keyboard_type=_KEYBOARD_NUMBER, expand=True)

        abs_action = mobile_dropdown("腹部动作", "仰卧抬腿", [ft.dropdown.Option(x) for x in ABS_ACTIONS], width=dialog_width)
        reps = mobile_text_field("次数/组数", width=dialog_width)

        cardio_minutes = mobile_text_field("时长 min", keyboard_type=_KEYBOARD_NUMBER, width=dialog_width)

        controls = [ft.Text(selected_target, size=16, weight="bold", color=PRIMARY), intensity]

        if selected_target == "爬坡":
            controls.extend([
                small_text("爬坡参数"),
                ft.Row([incline, speed], spacing=8),
                climb_minutes,
            ])
        elif selected_target == "腹":
            controls.extend([
                small_text("腹部参数"),
                abs_action,
                reps,
            ])
        elif selected_target in cardio_targets:
            controls.extend([
                small_text("运动参数"),
                cardio_minutes,
            ])

        controls.append(note)

        def confirm(e):
            note_text = (note.value or "").strip()
            detail = selected_target

            if selected_target == "爬坡":
                parts = []
                if incline.value:
                    parts.append(f"坡度 {incline.value}%")
                if speed.value:
                    parts.append(f"速度 {speed.value} km/h")
                if climb_minutes.value:
                    parts.append(f"{climb_minutes.value} 分钟")
                detail = "，".join(parts) if parts else "爬坡"
            elif selected_target == "腹":
                detail = abs_action.value or "腹部训练"
                if reps.value:
                    detail += f"：{reps.value}"
            elif selected_target in cardio_targets:
                detail = f"{cardio_minutes.value} 分钟" if cardio_minutes.value else selected_target
            elif selected_target in ["休息", "其他"] and note_text:
                detail = note_text
                note_text = ""

            state["training"]["targets"].append({
                "target": selected_target,
                "detail": detail,
                "note": note_text,
                "intensity": intensity.value or "中等",
            })
            close_control(dlg)
            save_current()
            refresh()
            snack("训练已添加")

        dlg = full_form_sheet(f"{selected_target}记录", controls, confirm)
        open_control(dlg)

    def delete_training(idx):
        if 0 <= idx < len(state["training"]["targets"]):
            state["training"]["targets"].pop(idx)
            save_current()
            refresh()

    def session_data():
        value = state.get("training", {}).get("session")
        return value if isinstance(value, dict) else None

    def find_active_session_date():
        current = session_data()
        if current and current.get("status") == "active":
            return state.get("date")
        record_date, _ = find_active_daily_session(records)
        return record_date

    def resume_session_date(record_date):
        load_record_for_date(record_date)
        state["current_view"] = "training"
        refresh()

    def session_model():
        value = session_data()
        return TrainingSession.from_dict(value) if value else None

    def iso_now():
        return datetime.datetime.now().isoformat(timespec="seconds")

    def parse_iso(value):
        try:
            return datetime.datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    def elapsed_seconds(session=None):
        session = session or session_data()
        return session_elapsed_seconds(session, datetime.datetime.now())

    def clock_text(seconds):
        seconds = max(0, int(seconds or 0))
        hours, rest = divmod(seconds, 3600)
        minutes, secs = divmod(rest, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def persist_session(session, record_date=None):
        target_date = str(record_date or state.get("date") or session.get("date") or "")
        save_training_session(target_date, session)

    def create_empty_session():
        training = state["training"]
        current = training.get("session")
        archive = training.setdefault("sessions", [])
        if isinstance(current, dict) and current.get("status") == "completed":
            training["sessions"] = append_session_once(archive, current)
        state["training"]["session"] = {
            "id": f"session_{uuid.uuid4().hex}",
            "date": state["date"],
            "status": "planned",
            "started_at": "",
            "ended_at": "",
            "total_duration_min": None,
            "exercises": [],
            "exercise_groups": [],
            "summary_note": "",
            "fatigue_status": state["training"].get("fatigue_status", "状态一般"),
            "rest_until": "",
            "rest_cycle": None,
            "incomplete": False,
        }
        state["training_exercise_index"] = 0
        state["training_set_index"] = 0
        save_current()

    def ensure_session():
        if not session_data() or session_data().get("status") == "completed":
            create_empty_session()
        return session_data()

    def open_add_exercise_dialog():
        ensure_session()
        dialog_width = responsive_width()
        selected = {"category": "胸", "sort": "frequent"}
        selected_names: list[str] = []
        custom_exercises = load_custom_exercises()
        catalog = exercise_catalog(custom_exercises)
        categories = (*EXERCISE_CATEGORIES, *(("自定义",) if custom_exercises else ()))
        list_holder = ft.Column(spacing=8)
        category_rows = ft.Column(spacing=6)
        selection_status = ft.Text("已选择 0 个动作", size=13, color=SUB, weight="bold")
        search = mobile_text_field("搜索动作名称、器械或目标肌群", "", width=dialog_width)
        library_dlg = None
        pending_setup = {"dialog": None}

        def after_library_dismiss(e=None):
            next_dialog = pending_setup.get("dialog")
            pending_setup["dialog"] = None
            if next_dialog is not None:
                open_control(next_dialog)

        usage_stats = exercise_usage_stats(records)

        def previous_defaults(exercise_name, fallback):
            for record_date in sorted(records, reverse=True):
                record = records.get(record_date, {})
                training = record.get("training", {}) if isinstance(record, dict) else {}
                sessions = raw_training_sessions(training)
                for previous in reversed(sessions):
                    for exercise in previous.get("exercises", []) if isinstance(previous, dict) else []:
                        if exercise.get("name") != exercise_name:
                            continue
                        mode = normalize_recording_mode(exercise.get("recording_mode"))
                        if mode != "strength" and exercise.get("completed"):
                            return {
                                "recording_mode": mode,
                                "duration_seconds": exercise.get("duration_seconds"),
                                "distance_km": exercise.get("distance_km"),
                                "cardio_metrics": exercise.get("cardio_metrics", {}),
                            }
                        completed_sets = [item for item in exercise.get("sets", []) if item.get("completed")]
                        if completed_sets:
                            last = completed_sets[-1]
                            return {
                                "recording_mode": "strength",
                                "weight_kg": last.get("weight_kg"),
                                "reps": last.get("reps"),
                                "sets": len(exercise.get("sets", [])),
                            }
            mode = normalize_recording_mode(fallback.get("recording_mode"))
            return {
                "recording_mode": mode,
                "weight_kg": fallback.get("default_weight_kg"),
                "reps": fallback.get("default_reps"),
                "sets": fallback.get("default_sets", 4),
                "duration_seconds": fallback.get("default_duration_seconds"),
                "distance_km": None,
                "cardio_metrics": {},
            }

        def exercise_entry_from_defaults(source_exercise, defaults, order):
            action_name = str(source_exercise.get("name") or "").strip()
            selected_mode = normalize_recording_mode(defaults.get("recording_mode"))

            def numeric_default(key, fallback_key, fallback=0):
                value = defaults.get(key)
                if value in (None, ""):
                    value = source_exercise.get(fallback_key)
                return to_float(value, fallback)

            set_count = max(1, min(12, int(numeric_default("sets", "default_sets", 4))))
            weight_value = max(0, to_float(defaults.get("weight_kg")))
            reps_value = max(0, int(numeric_default("reps", "default_reps")))
            duration_seconds = max(0, int(numeric_default("duration_seconds", "default_duration_seconds")))
            metric_keys = [
                key for key in source_exercise.get("cardio_metric_fields", [])
                if key in CARDIO_METRIC_LABELS
            ] if selected_mode == "cardio" else []
            previous_metrics = defaults.get("cardio_metrics", {}) if isinstance(defaults.get("cardio_metrics"), dict) else {}
            return {
                "id": f"session_exercise_{uuid.uuid4().hex}",
                "exercise_id": str(source_exercise.get("id") or action_name),
                "name": action_name,
                "body_part": source_exercise.get("category", source_exercise.get("body_part", "自定义")),
                "order": order,
                "recording_mode": selected_mode,
                "sets": [{
                    "id": f"set_{uuid.uuid4().hex}",
                    "order": index + 1,
                    "weight_kg": weight_value,
                    "reps": reps_value,
                    "completed": False,
                    "warmup": False,
                    "completed_at": "",
                } for index in range(set_count)] if selected_mode == "strength" else [],
                "duration_seconds": duration_seconds if selected_mode != "strength" else None,
                "distance_km": defaults.get("distance_km") if selected_mode == "cardio" else None,
                "distance_enabled": selected_mode == "cardio" and bool(source_exercise.get("distance_enabled")),
                "cardio_metric_fields": metric_keys,
                "cardio_metrics": {
                    key: max(0, to_float(previous_metrics.get(key)))
                    for key in metric_keys
                    if previous_metrics.get(key) is not None
                },
                "completed": False,
                "completed_at": "",
                "group_id": "",
                "group_order": None,
                "note": "",
            }

        def open_help(exercise):
            help_dlg = dialog_base(
                exercise.get("name", "动作说明"),
                build_exercise_help(exercise, dialog_width, _SCROLL_HIDDEN),
                [ft.Container(content=make_button("知道了", on_click=lambda e: close_control(help_dlg), expand=True), width=dialog_width)],
                on_close=lambda e: close_control(help_dlg),
            )
            open_control(help_dlg)

        def open_setup(exercise):
            is_new_custom = not str(exercise.get("name", "")).strip()
            defaults = previous_defaults(exercise.get("name", ""), exercise)
            name = mobile_text_field("动作名称", exercise.get("name", ""), width=dialog_width)
            mode = mobile_dropdown(
                "记录模式", defaults["recording_mode"],
                [ft.dropdown.Option("strength", "力量"), ft.dropdown.Option("timed", "计时"), ft.dropdown.Option("cardio", "有氧")],
                width=dialog_width,
            )
            mode.field.disabled = bool(exercise.get("name"))
            weight = mobile_text_field("重量 kg", "" if defaults.get("weight_kg") is None else f"{to_float(defaults.get('weight_kg')):g}", keyboard_type=_KEYBOARD_NUMBER, expand=True)
            reps = mobile_text_field("次数", "" if defaults.get("reps") is None else str(int(to_float(defaults.get("reps")))), keyboard_type=_KEYBOARD_NUMBER, expand=True)
            sets = mobile_text_field("组数", str(int(to_float(defaults.get("sets"), 4))), keyboard_type=_KEYBOARD_NUMBER, expand=True)
            duration = max(0, int(to_float(defaults.get("duration_seconds"))))
            duration_min = mobile_text_field("分钟", str(duration // 60), keyboard_type=_KEYBOARD_NUMBER, expand=True)
            duration_sec = mobile_text_field("秒", str(duration % 60), keyboard_type=_KEYBOARD_NUMBER, expand=True)
            distance = mobile_text_field("距离 km（可选）", "" if defaults.get("distance_km") is None else f"{to_float(defaults.get('distance_km')):g}", keyboard_type=_KEYBOARD_NUMBER, expand=True)
            cues = mobile_text_field(
                "动作诀窍（每行一条）",
                "\n".join(exercise.get("cues", [])),
                width=dialog_width,
                height=108,
                multiline=True,
                min_lines=3,
                max_lines=3,
            )
            mistakes = mobile_text_field(
                "注意点（每行一条）",
                "\n".join(exercise.get("mistakes", [])),
                width=dialog_width,
                height=108,
                multiline=True,
                min_lines=3,
                max_lines=3,
            )
            configured_metric_keys = [
                key for key in exercise.get("cardio_metric_fields", [])
                if key in CARDIO_METRIC_LABELS
            ]
            available_metric_keys = configured_metric_keys or (
                list(CUSTOM_CARDIO_METRIC_FIELDS) if is_new_custom else []
            )
            metric_fields = {
                key: mobile_text_field(
                    CARDIO_METRIC_LABELS.get(key, key),
                    "" if defaults.get("cardio_metrics", {}).get(key) is None else f"{to_float(defaults.get('cardio_metrics', {}).get(key)):g}",
                    keyboard_type=_KEYBOARD_NUMBER,
                    expand=True,
                )
                for key in available_metric_keys
            }
            strength_fields = three_field_grid(weight, reps, sets, viewport_width=dialog_width)
            duration_fields = two_field_grid(duration_min, duration_sec, viewport_width=dialog_width)
            distance_holder = ft.Container(distance)
            metrics_holder = responsive_field_grid(
                list(metric_fields.values()),
                columns=2,
                viewport_width=dialog_width,
            )

            bind_training_parameter_mode(
                mode,
                is_new_custom=is_new_custom,
                distance_enabled=bool(exercise.get("distance_enabled")),
                cardio_metric_fields=available_metric_keys,
                strength=strength_fields,
                duration=duration_fields,
                distance=distance_holder,
                metrics=metrics_holder,
                request_update=page.update,
            )
            saved_setup = {"message": ""}

            def after_setup_dismiss(e=None):
                message = saved_setup.get("message", "")
                if not message:
                    return
                saved_setup["message"] = ""
                refresh()
                snack(message)

            def confirm(e):
                session = ensure_session()
                action_name = (name.value or "").strip()
                if not action_name:
                    snack("请填写动作名称")
                    return
                selected_mode = normalize_recording_mode(mode.value)
                set_count = max(1, min(12, int(to_float(sets.value, 4))))
                duration_seconds = max(0, int(to_float(duration_min.value)) * 60 + min(59, max(0, int(to_float(duration_sec.value)))))
                if selected_mode != "strength" and duration_seconds <= 0:
                    snack("请填写有效时长")
                    return
                selected_metric_keys = [
                    key for key, field in metric_fields.items()
                    if selected_mode == "cardio" and str(field.value or "").strip()
                ]
                source_exercise = exercise
                if is_new_custom:
                    custom_spec = {
                        "name": action_name,
                        "category": "自定义",
                        "equipment": "其他",
                        "target_muscles": [],
                        "cues": [item.strip() for item in str(cues.value or "").splitlines() if item.strip()],
                        "mistakes": [item.strip() for item in str(mistakes.value or "").splitlines() if item.strip()],
                        "default_weight_kg": max(0, to_float(weight.value)) if selected_mode == "strength" else None,
                        "default_reps": max(0, int(to_float(reps.value, 0))),
                        "default_sets": set_count,
                        "recording_mode": selected_mode,
                        "distance_enabled": selected_mode == "cardio",
                        "cardio_metric_fields": selected_metric_keys,
                        "aliases": [],
                        "default_duration_seconds": duration_seconds if selected_mode != "strength" else None,
                    }
                    try:
                        source_exercise = save_custom_exercise(custom_spec)
                    except ValueError as exc:
                        snack(str(exc))
                        return
                exercise_entry = {
                    "id": f"session_exercise_{uuid.uuid4().hex}",
                    "exercise_id": action_name,
                    "name": action_name,
                    "body_part": source_exercise.get("category", "自定义"),
                    "order": len(session.get("exercises", [])) + 1,
                    "recording_mode": selected_mode,
                    "sets": [{
                        "id": f"set_{uuid.uuid4().hex}",
                        "order": index + 1,
                        "weight_kg": max(0, to_float(weight.value)),
                        "reps": max(0, int(to_float(reps.value, 0))),
                        "completed": False,
                        "warmup": False,
                        "completed_at": "",
                    } for index in range(set_count)] if selected_mode == "strength" else [],
                    "duration_seconds": duration_seconds if selected_mode != "strength" else None,
                    "distance_km": max(0, to_float(distance.value)) if selected_mode == "cardio" and str(distance.value or "").strip() else None,
                    "distance_enabled": selected_mode == "cardio" and bool(source_exercise.get("distance_enabled", is_new_custom)),
                    "cardio_metric_fields": list(source_exercise.get("cardio_metric_fields", selected_metric_keys)) if selected_mode == "cardio" else [],
                    "cardio_metrics": {
                        key: max(0, to_float(field.value))
                        for key, field in metric_fields.items()
                        if str(field.value or "").strip()
                    } if selected_mode == "cardio" else {},
                    "completed": False,
                    "completed_at": "",
                    "group_id": "",
                    "group_order": None,
                    "note": "",
                }
                session.setdefault("exercises", []).append(exercise_entry)
                persist_session(session)
                saved_setup["message"] = f"已添加 {action_name}"
                close_control(setup_dlg)

            setup_dlg = full_form_sheet(
                "新增自定义动作" if is_new_custom else "设置动作",
                [
                    section_title("动作"), name, mode,
                    *([section_title("动作说明"), cues, mistakes] if is_new_custom else []),
                    ft.Container(content=small_text("默认值仅用于首次添加；有历史时使用上次成绩，自重动作的重量可留空。"), bgcolor=SURFACE, border_radius=8, padding=8),
                    section_title("训练参数"),
                    strength_fields, duration_fields, distance_holder, metrics_holder,
                ],
                confirm,
                save_label="保存并加入训练" if is_new_custom else "加入训练",
            )
            setup_dlg.on_dismiss = after_setup_dismiss
            if library_dlg and library_dlg.open:
                pending_setup["dialog"] = setup_dlg
                close_control(library_dlg)
            else:
                open_control(setup_dlg)

        def exercise_row(exercise):
            usage = usage_stats.get(str(exercise.get("name", "")).casefold(), {})
            exercise_name = str(exercise.get("name") or "")
            return build_exercise_card(
                exercise,
                usage,
                lambda e, item=exercise: open_help(item),
                lambda e, item=exercise: toggle_exercise(item),
                selected=exercise_name in selected_names,
            )

        def toggle_exercise(exercise):
            exercise_name = str(exercise.get("name") or "")
            if exercise_name in selected_names:
                selected_names.remove(exercise_name)
            elif exercise_name:
                selected_names.append(exercise_name)
            selection_status.value = f"已选择 {len(selected_names)} 个动作"
            rebuild_list()
            page.update()

        def add_selected_exercises(e=None):
            if not selected_names:
                snack("请先选择至少一个动作")
                return
            session = ensure_session()
            source_by_name = {
                str(item.get("name") or ""): item
                for item in catalog
                if str(item.get("name") or "")
            }
            added = 0
            for exercise_name in selected_names:
                source_exercise = source_by_name.get(exercise_name)
                if not source_exercise:
                    continue
                defaults = previous_defaults(exercise_name, source_exercise)
                entry = exercise_entry_from_defaults(
                    source_exercise,
                    defaults,
                    len(session.get("exercises", [])) + 1,
                )
                session.setdefault("exercises", []).append(entry)
                added += 1
            if not added:
                snack("没有可添加的动作")
                return
            persist_session(session)
            close_control(library_dlg)
            refresh()
            snack(f"已添加 {added} 个动作，可在计划卡片中单独编辑")

        def rebuild_categories():
            category_rows.controls.clear()
            category_rows.controls.extend(build_category_rows(categories, selected["category"], choose_category))

        def choose_category(category):
            selected["category"] = category
            rebuild_categories()
            rebuild_list()
            page.update()

        def choose_sort(mode):
            selected["sort"] = mode
            rebuild_list()
            page.update()

        def rebuild_list(e=None):
            query = (search.value or "").strip()
            results = search_exercises(query, None if query else selected["category"], catalog)
            results = sort_exercises(results, usage_stats, selected["sort"])
            list_holder.controls.clear()
            list_holder.controls.extend(exercise_row(item) for item in results)
            if not results:
                list_holder.controls.append(ft.Container(content=small_text("没有匹配动作，可使用下方自定义动作"), bgcolor=SURFACE, border_radius=10, padding=12))
            if e is not None:
                page.update()

        search.on_change = rebuild_list
        rebuild_categories()
        rebuild_list()
        custom_item = {"name": "", "category": "自定义", "equipment": "其他", "target_muscles": [], "cues": [], "mistakes": [], "default_weight_kg": None, "default_reps": 10, "default_sets": 4, "recording_mode": "strength", "distance_enabled": True}
        sort_row = build_sort_row(choose_sort)
        custom_button = make_button(
            "新建自定义动作",
            on_click=lambda e: open_setup(custom_item),
            icon=ft.Icons.ADD,
            bgcolor=PRIMARY_SOFT,
            color=GREEN,
            expand=True,
        )
        library_dlg = full_form_sheet(
            f"添加动作 · {len(catalog)} 个",
            [search, sort_row, category_rows, selection_status, list_holder, custom_button],
            add_selected_exercises,
            save_label="添加已选动作",
        )
        library_dlg.on_dismiss = after_library_dismiss
        open_control(library_dlg)

    def planned_exercise(exercise_id):
        session = session_data()
        if not isinstance(session, dict):
            return None, None
        exercise = next(
            (
                item for item in session.get("exercises", [])
                if isinstance(item, dict) and str(item.get("id") or "") == str(exercise_id)
            ),
            None,
        )
        return session, exercise

    def open_planned_exercise_help(exercise_id):
        _session, exercise = planned_exercise(exercise_id)
        if not exercise:
            return
        catalog = exercise_catalog(load_custom_exercises())
        definition = next(
            (item for item in catalog if str(item.get("name") or "") == str(exercise.get("name") or "")),
            {
                "name": exercise.get("name", "动作说明"),
                "target_muscles": [],
                "cues": exercise.get("cues", []),
                "mistakes": exercise.get("mistakes", []),
            },
        )
        dialog_width = responsive_width()
        help_dlg = dialog_base(
            definition.get("name", "动作说明"),
            build_exercise_help(definition, dialog_width, _SCROLL_HIDDEN),
            [ft.Container(
                content=make_button("知道了", on_click=lambda e: close_control(help_dlg), expand=True),
                width=dialog_width,
            )],
            on_close=lambda e: close_control(help_dlg),
        )
        open_control(help_dlg)

    def open_edit_planned_exercise(exercise_id):
        session, exercise = planned_exercise(exercise_id)
        if not session or not exercise or session.get("status") == "active":
            return
        dialog_width = responsive_width()
        mode = normalize_recording_mode(exercise.get("recording_mode"))
        raw_sets = [item for item in exercise.get("sets", []) if isinstance(item, dict)]
        first_set = raw_sets[0] if raw_sets else {}
        weight = mobile_text_field(
            "重量 kg（自重可留空）",
            "" if to_float(first_set.get("weight_kg")) <= 0 else f"{to_float(first_set.get('weight_kg')):g}",
            keyboard_type=_KEYBOARD_NUMBER,
            expand=True,
        )
        reps = mobile_text_field(
            "次数",
            "" if first_set.get("reps") is None else str(int(to_float(first_set.get("reps")))),
            keyboard_type=_KEYBOARD_NUMBER,
            expand=True,
        )
        sets = mobile_text_field(
            "组数",
            str(max(1, len(raw_sets))),
            keyboard_type=_KEYBOARD_NUMBER,
            expand=True,
        )
        duration = max(0, int(to_float(exercise.get("duration_seconds"))))
        duration_min = mobile_text_field("分钟", str(duration // 60), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        duration_sec = mobile_text_field("秒", str(duration % 60), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        distance = mobile_text_field(
            "距离 km（可选）",
            "" if exercise.get("distance_km") is None else f"{to_float(exercise.get('distance_km')):g}",
            keyboard_type=_KEYBOARD_NUMBER,
            expand=True,
        )
        metric_keys = [
            key for key in exercise.get("cardio_metric_fields", [])
            if key in CARDIO_METRIC_LABELS
        ]
        metric_fields = {
            key: mobile_text_field(
                CARDIO_METRIC_LABELS.get(key, key),
                "" if exercise.get("cardio_metrics", {}).get(key) is None else f"{to_float(exercise.get('cardio_metrics', {}).get(key)):g}",
                keyboard_type=_KEYBOARD_NUMBER,
                expand=True,
            )
            for key in metric_keys
        }
        mode_label = {"strength": "力量", "timed": "计时", "cardio": "有氧"}[mode]
        controls: list[ft.Control] = [
            section_title(str(exercise.get("name") or "编辑动作")),
            small_text(f"记录模式：{mode_label}"),
        ]
        if mode == "strength":
            controls.append(three_field_grid(weight, reps, sets, viewport_width=dialog_width))
        else:
            controls.append(two_field_grid(duration_min, duration_sec, viewport_width=dialog_width))
            if mode == "cardio" and exercise.get("distance_enabled"):
                controls.append(distance)
            if mode == "cardio" and metric_fields:
                controls.append(responsive_field_grid(list(metric_fields.values()), columns=2, viewport_width=dialog_width))

        edit_dlg = None

        def save_edit(e=None):
            if mode == "strength":
                set_count = max(1, min(12, int(to_float(sets.value, len(raw_sets) or 1))))
                weight_value = max(0, to_float(weight.value))
                reps_value = max(0, int(to_float(reps.value)))
                exercise["sets"] = [{
                    **(raw_sets[index] if index < len(raw_sets) else {}),
                    "id": str(raw_sets[index].get("id") or f"set_{uuid.uuid4().hex}") if index < len(raw_sets) else f"set_{uuid.uuid4().hex}",
                    "order": index + 1,
                    "weight_kg": weight_value,
                    "reps": reps_value,
                    "completed": False,
                    "warmup": False,
                    "completed_at": "",
                } for index in range(set_count)]
            else:
                duration_seconds = max(0, int(to_float(duration_min.value)) * 60 + min(59, max(0, int(to_float(duration_sec.value)))))
                if duration_seconds <= 0:
                    snack("请填写有效时长")
                    return
                exercise["duration_seconds"] = duration_seconds
                if mode == "cardio" and exercise.get("distance_enabled"):
                    exercise["distance_km"] = max(0, to_float(distance.value)) if str(distance.value or "").strip() else None
                if mode == "cardio":
                    exercise["cardio_metrics"] = {
                        key: max(0, to_float(field.value))
                        for key, field in metric_fields.items()
                        if str(field.value or "").strip()
                    }
            persist_session(session)
            close_control(edit_dlg)
            refresh()
            snack(f"已更新 {exercise.get('name', '动作')} 参数")

        edit_dlg = full_form_sheet(
            "编辑训练参数",
            controls,
            save_edit,
            save_label="保存修改",
        )
        open_control(edit_dlg)

    def reuse_history_session(e=None):
        dialog_width = responsive_width()
        selected = {"part": "全部"}
        cards_holder = ft.Column(spacing=8)
        filters_holder = ft.Column(spacing=6)
        history_dlg = None

        def apply_card(card_item, mode):
            current = session_data()
            copied = copy_whole_session(
                card_item["session"], current, mode=mode, new_date=state.get("date")
            )
            state["training"]["session"] = copied
            state["training_exercise_index"] = 0
            state["training_set_index"] = 0
            close_control(history_dlg)
            persist_session(copied)
            refresh()
            snack(f"已复用 {card_item['combination']} 训练")

        def choose_card(card_item):
            current = session_data()
            has_plan = bool(current and current.get("exercises"))
            if not has_plan:
                apply_card(card_item, "replace")
                return
            confirm_dlg = None

            def dismiss_confirm(e=None):
                if confirm_dlg is not None:
                    close_control(confirm_dlg)

            def apply_confirmed(mode):
                dismiss_confirm()
                apply_card(card_item, mode)

            confirm_dlg = dialog_base(
                "当前计划已有动作",
                ft.Column([
                    ft.Text(f"复用 {card_item['combination']} · {card_item['date']}", size=15, weight="bold", color=TEXT),
                    small_text("请选择替换当前计划，或把整场历史训练追加到当前计划。"),
                ], width=dialog_width, spacing=8),
                [
                    make_button("取消", on_click=dismiss_confirm, bgcolor=SURFACE, color=SUB, expand=True),
                    make_button("整场追加", on_click=lambda e: apply_confirmed("append"), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                    make_button("替换", on_click=lambda e: apply_confirmed("replace"), expand=True),
                ],
                on_close=dismiss_confirm,
            )
            bind_dialog_close_button(confirm_dlg, dismiss_confirm)
            open_control(confirm_dlg)

        def rebuild_cards():
            part = None if selected["part"] == "全部" else selected["part"]
            cards = history_training_cards(records, part)
            cards_holder.controls.clear()
            for item in cards:
                cards_holder.controls.append(ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(item["combination"], size=16, weight="bold", color=TEXT),
                            small_text(f"最近 {item['date']} · {item['exercise_count']} 个动作"),
                        ], expand=True, spacing=3),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, color=GREEN),
                    ]),
                    bgcolor="#FFFFFF", border=thin_border(), border_radius=12, padding=14,
                    on_click=lambda e, card=item: choose_card(card),
                ))
            if not cards:
                cards_holder.controls.append(ft.Container(content=small_text("该部位还没有可复用的完整训练"), bgcolor=SURFACE, border_radius=10, padding=14))

        def choose_part(part):
            selected["part"] = part
            rebuild_filters()
            rebuild_cards()
            page.update()

        def rebuild_filters():
            buttons = []
            for part in ("全部", *BODY_PART_ORDER):
                active = selected["part"] == part
                buttons.append(make_button(part, on_click=lambda e, p=part: choose_part(p), bgcolor=PRIMARY if active else PRIMARY_SOFT, color="#FFFFFF" if active else GREEN, expand=True))
            filters_holder.controls[:] = [ft.Row(buttons[i:i + 3], spacing=6) for i in range(0, len(buttons), 3)]

        rebuild_filters()
        rebuild_cards()
        history_dlg = dialog_base(
            "复用历史训练",
            ft.Column([small_text("同一部位组合只显示最近一场"), filters_holder, cards_holder], width=dialog_width, height=520, spacing=10, scroll=_SCROLL_HIDDEN),
            [],
            on_close=lambda e: close_control(history_dlg),
        )
        open_control(history_dlg)

    def open_exercise_group_dialog(base_exercise_id):
        session = session_data()
        exercises = session.get("exercises", []) if session else []
        if not session or len(exercises) < 2:
            snack("至少添加两个动作后才能组成组合组")
            return
        dialog_width = responsive_width()
        existing_group = next((
            group for group in session.get("exercise_groups", [])
            if isinstance(group, dict) and base_exercise_id in group.get("exercise_ids", [])
        ), None)
        selected_ids = set(existing_group.get("exercise_ids", [])) if existing_group else {base_exercise_id}
        group_type = mobile_dropdown(
            "组合类型",
            existing_group.get("group_type", "superset") if existing_group else "superset",
            [ft.dropdown.Option("superset", "超级组"), ft.dropdown.Option("compound", "复合组")],
            width=dialog_width,
        )
        checks = []
        for exercise in exercises:
            exercise_id = str(exercise.get("id") or "")
            checkbox = ft.Checkbox(
                label=str(exercise.get("name") or "动作"),
                value=exercise_id in selected_ids,
                disabled=exercise_id == base_exercise_id,
                data=exercise_id,
            )
            checks.append(checkbox)
        dlg = None

        def confirm_group(e=None):
            member_ids = [str(item.data) for item in checks if item.value]
            try:
                session["exercise_groups"] = create_exercise_group(
                    session.get("exercises", []),
                    session.get("exercise_groups", []),
                    member_ids,
                    str(group_type.value or ""),
                )
            except ValueError as exc:
                snack(str(exc))
                return
            persist_session(session)
            close_control(dlg)
            refresh()

        dlg = full_form_sheet(
            "设置动作组合",
            [group_type, small_text("至少选择两个动作；组内按列表顺序连续完成，整组后统一休息。"), *checks],
            confirm_group,
            save_label="保存组合",
        )
        open_control(dlg)

    def clear_today_training(e=None):
        session = session_data()
        cycle = session.get("rest_cycle") if isinstance(session, dict) else None
        if isinstance(cycle, dict):
            rest_notifier.cancel(str(cycle.get("id", "")), release_claim=False)
        training = state["training"]
        training.clear()
        training.update({
            "total_duration_min": "", "total_calories_kcal": "", "fatigue_status": "状态一般",
            "summary_note": "", "targets": [], "carb_reminder_dismissed_signature": "",
            "session": None, "sessions": [],
        })
        state["training_exercise_index"] = 0
        state["training_set_index"] = 0
        save_current()
        refresh()

    def start_session(e=None):
        session = ensure_session()
        if not session.get("exercises"):
            open_add_exercise_dialog()
            return
        session.update({"status": "active", "started_at": session.get("started_at") or iso_now(), "ended_at": ""})
        persist_session(session)
        refresh()

    def delete_session_exercise(index):
        session = session_data()
        if not session or session.get("status") == "active":
            return
        exercises = session.get("exercises", [])
        if 0 <= index < len(exercises):
            exercises.pop(index)
        session["exercise_groups"] = normalize_exercise_groups(exercises, session.get("exercise_groups", []))
        persist_session(session)
        refresh()

    def current_training_items():
        session = session_data()
        exercises = normalized_session_exercises(session)
        if not exercises:
            return session, None, None
        session_id = "" if not isinstance(session, dict) else str(
            session.get("id")
            or f"{session.get('date', '')}:{session.get('started_at', '')}"
        )
        if session_id and active_cursor["session_id"] != session_id:
            move_cursor_to_pending(exercises)
            active_cursor["session_id"] = session_id
        exercise_index = max(0, min(safe_int(state.get("training_exercise_index", 0)), len(exercises) - 1))
        state["training_exercise_index"] = exercise_index
        exercise = exercises[exercise_index]
        sets = exercise.get("sets", [])
        if not sets:
            return session, exercise, None
        set_index = max(0, min(safe_int(state.get("training_set_index", 0)), len(sets) - 1))
        state["training_set_index"] = set_index
        return session, exercise, sets[set_index]

    def work_key(session, exercise, training_set):
        if not session or not exercise:
            return ""
        mode = normalize_recording_mode(exercise.get("recording_mode"))
        if mode == "strength":
            return f"{session.get('id')}:{exercise.get('id')}:{training_set.get('id') if training_set else ''}"
        return f"{session.get('id')}:{exercise.get('id')}:completed"

    def exercise_is_done(exercise):
        if not isinstance(exercise, dict):
            return False
        if normalize_recording_mode(exercise.get("recording_mode")) == "strength":
            sets = exercise.get("sets", [])
            return bool(sets) and all(bool(item.get("completed")) for item in sets if isinstance(item, dict))
        return bool(exercise.get("completed"))

    def next_pending_label(session, start_index=0, start_set_index=0):
        exercises = normalized_session_exercises(session)
        for candidate_index in range(max(0, start_index), len(exercises)):
            candidate = exercises[candidate_index]
            mode = normalize_recording_mode(candidate.get("recording_mode"))
            if mode == "strength":
                set_index = first_pending_set_index(
                    candidate,
                    start_set_index if candidate_index == start_index else 0,
                )
                if set_index is not None:
                    return f"下一个：{candidate.get('name', '动作')} · 第 {set_index + 1} 组"
            elif not candidate.get("completed"):
                return f"下一个：{candidate.get('name', '动作')}"
        return "下一个：暂无，准备结束训练"

    def current_pending_label(exercise, set_index=0, group_position_text=""):
        """Describe the work item at the active cursor, primarily for the rest card."""
        if not isinstance(exercise, dict):
            return "下一个：暂无，准备结束训练"
        mode = normalize_recording_mode(exercise.get("recording_mode"))
        if mode == "strength":
            sets = exercise.get("sets", [])
            index = safe_int(set_index)
            if not isinstance(sets, list) or not (0 <= index < len(sets)):
                return "下一个：暂无，准备结束训练"
            training_set = sets[index]
            if not isinstance(training_set, dict) or training_set.get("completed"):
                return "下一个：暂无，准备结束训练"
            label = f"下一个：{exercise.get('name', '动作')} · 第 {index + 1} 组"
        else:
            if exercise.get("completed"):
                return "下一个：暂无，准备结束训练"
            label = f"下一个：{exercise.get('name', '动作')}"
        if group_position_text:
            label += f" · {group_position_text}"
        return label

    def rest_is_active(session):
        cycle = session.get("rest_cycle") if isinstance(session, dict) else None
        return isinstance(cycle, dict) and cycle.get("status") in {"running", "paused"}

    def active_group_context(session, exercise, training_set):
        if not session or not exercise:
            return "", "", (), "下一个：暂无"
        exercises = normalized_session_exercises(session)
        exercise_id = str(exercise.get("id") or "")
        positions = {str(item.get("id") or ""): index for index, item in enumerate(exercises) if isinstance(item, dict)}
        current_index = positions.get(exercise_id, safe_int(state.get("training_exercise_index", 0)))
        set_index = safe_int(state.get("training_set_index", 0))
        group_id = str(exercise.get("group_id") or "")
        group = next(
            (
                item for item in session.get("exercise_groups", [])
                if isinstance(item, dict) and str(item.get("id") or "") == group_id
            ),
            None,
        )
        if not group:
            next_set_index = set_index + 1 if normalize_recording_mode(exercise.get("recording_mode")) == "strength" else 0
            next_exercise_index = current_index if normalize_recording_mode(exercise.get("recording_mode")) == "strength" else current_index + 1
            return "", "", (), next_pending_label(session, next_exercise_index, next_set_index)

        member_ids = [str(item) for item in group.get("exercise_ids", []) if str(item) in positions]
        member_index = member_ids.index(exercise_id) if exercise_id in member_ids else 0
        group_type = "超级组" if group.get("group_type") == "superset" else "复合组"
        members = tuple(
            (
                str(exercises[positions[member_id]].get("name") or "动作"),
                member_id,
                member_id == exercise_id,
                exercise_is_done(exercises[positions[member_id]]),
            )
            for member_id in member_ids
        )
        round_index = set_index if normalize_recording_mode(exercise.get("recording_mode")) == "strength" else 0
        preview_session = copy.deepcopy(session)
        preview_exercises = normalized_session_exercises(preview_session)
        preview_positions = {
            str(item.get("id") or ""): index
            for index, item in enumerate(preview_exercises)
            if isinstance(item, dict)
        }
        preview_exercise = preview_exercises[preview_positions[exercise_id]] if exercise_id in preview_positions else None
        if preview_exercise is not None:
            if normalize_recording_mode(preview_exercise.get("recording_mode")) == "strength":
                preview_sets = preview_exercise.get("sets", [])
                if 0 <= round_index < len(preview_sets):
                    preview_sets[round_index]["completed"] = True
            else:
                preview_exercise["completed"] = True
        next_work = next_group_work(preview_session, exercise_id, round_index)
        if next_work and next_work.get("exercise_id") in positions:
            next_exercise = exercises[positions[next_work["exercise_id"]]]
            next_position = member_ids.index(next_work["exercise_id"]) + 1 if next_work["exercise_id"] in member_ids else 1
            next_set = safe_int(next_work.get("set_index"), 0)
            set_label = f" · 第 {next_set + 1} 组" if normalize_recording_mode(next_exercise.get("recording_mode")) == "strength" else ""
            next_label = f"下一个：{next_exercise.get('name', '动作')}{set_label} · 组内第 {next_position}/{len(member_ids)} 个"
        elif next_work and next_work.get("group_complete"):
            last_member_index = max((positions.get(member_id, current_index) for member_id in member_ids), default=current_index)
            next_label = next_pending_label(session, max(last_member_index + 1, current_index + 1))
        else:
            next_label = next_pending_label(session, current_index + 1)
        return group_type, f"组内第 {member_index + 1}/{len(member_ids)} 个", members, next_label

    def restore_training_cursor():
        session = session_data()
        if not session or session.get("status") != "active":
            return
        for exercise_index, exercise in enumerate(session.get("exercises", [])):
            if normalize_recording_mode(exercise.get("recording_mode")) != "strength" and not exercise.get("completed"):
                state["training_exercise_index"] = exercise_index
                state["training_set_index"] = 0
                return
            for set_index, item in enumerate(exercise.get("sets", [])):
                if not item.get("completed"):
                    state["training_exercise_index"] = exercise_index
                    state["training_set_index"] = set_index
                    return

    def adjust_current(field, delta):
        session, exercise, training_set = current_training_items()
        if not training_set or training_set.get("completed"):
            return
        current = to_float(training_set.get(field), 0)
        value = max(0, current + delta)
        training_set[field] = int(value) if field == "reps" else adjust_weight_kg(current, int(delta))
        persist_session(session)
        refresh()

    def open_weight_editor(e=None):
        session, exercise, training_set = current_training_items()
        if not session or not training_set or training_set.get("completed"):
            return
        field = mobile_text_field(
            "重量（kg）",
            format_weight_kg(training_set.get("weight_kg", 0)),
            width=responsive_width(),
            keyboard_type=_KEYBOARD_NUMBER,
        )
        dlg = None

        def save_weight(_=None):
            try:
                training_set["weight_kg"] = normalize_weight_input(field.field.value)
            except ValueError as exc:
                snack(str(exc))
                return
            persist_session(session)
            close_control(dlg)
            refresh()

        dlg = dialog_base(
            "编辑本组重量",
            ft.Column([field], width=responsive_width(), spacing=8, tight=True),
            [ft.Container(content=ft.Row([
                make_button("取消", on_click=lambda event: close_control(dlg), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                make_button("确认", on_click=save_weight, expand=True),
            ], spacing=8), width=responsive_width())],
            on_close=lambda event: close_control(dlg),
        )
        open_control(dlg)

    def open_duration_editor(e=None):
        session, exercise, training_set = current_training_items()
        if not session or not exercise or normalize_recording_mode(exercise.get("recording_mode")) == "strength" or exercise.get("completed"):
            return
        duration = max(0, int(to_float(exercise.get("duration_seconds"))))
        minutes = mobile_text_field("分钟", str(duration // 60), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        seconds = mobile_text_field("秒", str(duration % 60), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        dlg = None

        def save_duration(_=None):
            value = max(0, int(to_float(minutes.value)) * 60 + min(59, max(0, int(to_float(seconds.value)))))
            if value <= 0:
                snack("请填写有效时长")
                return
            exercise["duration_seconds"] = value
            persist_session(session)
            close_control(dlg)
            refresh()

        dlg = dialog_base(
            "编辑动作时长",
            ft.ResponsiveRow([ft.Container(minutes, col={"xs": 6}), ft.Container(seconds, col={"xs": 6})], width=responsive_width()),
            [make_button("确认", on_click=save_duration, expand=True)],
            on_close=lambda event: close_control(dlg),
        )
        open_control(dlg)

    def open_distance_editor(e=None):
        session, exercise, training_set = current_training_items()
        if not session or not exercise or normalize_recording_mode(exercise.get("recording_mode")) != "cardio" or exercise.get("completed"):
            return
        field = mobile_text_field("距离 km（可选）", "" if exercise.get("distance_km") is None else f"{to_float(exercise.get('distance_km')):g}", width=responsive_width(), keyboard_type=_KEYBOARD_NUMBER)
        dlg = None

        def save_distance(_=None):
            exercise["distance_km"] = max(0, to_float(field.value)) if str(field.value or "").strip() else None
            persist_session(session)
            close_control(dlg)
            refresh()

        dlg = dialog_base(
            "编辑有氧距离", ft.Column([field], width=responsive_width()),
            [make_button("确认", on_click=save_distance, expand=True)],
            on_close=lambda event: close_control(dlg),
        )
        open_control(dlg)

    def open_cardio_metric_editor(metric_key, metric_label):
        session, exercise, training_set = current_training_items()
        if not session or not exercise or normalize_recording_mode(exercise.get("recording_mode")) != "cardio" or exercise.get("completed"):
            return
        metrics = exercise.setdefault("cardio_metrics", {})
        field = mobile_text_field(metric_label, "" if metrics.get(metric_key) is None else f"{to_float(metrics.get(metric_key)):g}", width=responsive_width(), keyboard_type=_KEYBOARD_NUMBER)
        dlg = None

        def save_metric(_=None):
            if str(field.value or "").strip():
                metrics[metric_key] = max(0, to_float(field.value))
            else:
                metrics.pop(metric_key, None)
            persist_session(session)
            close_control(dlg)
            refresh()

        dlg = dialog_base(
            f"编辑{metric_label}", ft.Column([field], width=responsive_width()),
            [make_button("确认", on_click=save_metric, expand=True)],
            on_close=lambda event: close_control(dlg),
        )
        open_control(dlg)

    def undo_current_set(e=None):
        completion_prompt["key"] = ""
        session, exercise, training_set = current_training_items()
        active_cycle = session.get("rest_cycle") if isinstance(session, dict) else None
        if isinstance(active_cycle, dict):
            rest_notifier.cancel(str(active_cycle.get("id", "")), release_claim=False)
        if session and exercise and normalize_recording_mode(exercise.get("recording_mode")) != "strength":
            if not exercise.get("completed"):
                return
            exercise["completed"] = False
            exercise["completed_at"] = ""
            session["rest_cycle"] = None
            session["rest_until"] = ""
            persist_session(session)
            refresh()
            return
        if not session or not training_set or not training_set.get("completed"):
            return
        result = undo_completed_set_result(session, str(training_set.get("id", "")))
        restored = result["session"]
        restored["rest_cycle"] = None
        restored["rest_until"] = ""
        persist_session(restored)
        refresh()
        snack("已撤销本组完成状态，可重新调整重量和次数")

    def move_training(direction):
        session, exercise, training_set = current_training_items()
        exercises = session.get("exercises", []) if session else []
        if not exercises:
            return
        index = max(0, min(len(exercises) - 1, safe_int(state.get("training_exercise_index", 0)) + direction))
        state["training_exercise_index"] = index
        next_sets = exercises[index].get("sets", [])
        state["training_set_index"] = next((i for i, item in enumerate(next_sets) if not item.get("completed")), 0)
        refresh()

    def advance_after_work(session, exercise_index, set_index):
        exercises = normalized_session_exercises(session)
        if not exercises or not (0 <= exercise_index < len(exercises)):
            restore_training_cursor()
            return False

        current = exercises[exercise_index]
        group_id = str(current.get("group_id") or "")
        group = next((item for item in session.get("exercise_groups", []) if isinstance(item, dict) and str(item.get("id") or "") == group_id), None)
        if group:
            positions = {str(item.get("id") or ""): index for index, item in enumerate(exercises)}
            member_indexes = [positions[str(item)] for item in group.get("exercise_ids", []) if str(item) in positions]
            round_index = set_index if normalize_recording_mode(current.get("recording_mode")) == "strength" else 0
            next_work = next_group_work(session, str(current.get("id") or ""), round_index)
            if next_work and next_work.get("exercise_id") in positions:
                state["training_exercise_index"] = positions[next_work["exercise_id"]]
                state["training_set_index"] = safe_int(next_work.get("set_index"), 0)
                return bool(next_work.get("grouped_round_complete"))
            next_block_index = max(member_indexes, default=exercise_index) + 1
            move_cursor_to_pending(exercises, next_block_index)
            return bool(next_work and next_work.get("grouped_round_complete"))

        if normalize_recording_mode(current.get("recording_mode")) == "strength":
            next_set = first_pending_set_index(current, set_index + 1)
            if next_set is not None:
                state["training_set_index"] = next_set
                return True
        move_cursor_to_pending(exercises, exercise_index + 1)
        return rest_required_after_work(current.get("recording_mode"))

    def ask_complete_current(e=None):
        session, exercise, training_set = current_training_items()
        if not exercise or rest_is_active(session):
            return
        completion_prompt["key"] = work_key(session, exercise, training_set)
        refresh()

    def cancel_complete_current(e=None):
        completion_prompt["key"] = ""
        refresh()

    def complete_current_set(e=None):
        clicked_at = datetime.datetime.now().timestamp()
        if is_rapid_repeat(state.get("last_complete_click_at", 0), clicked_at):
            return
        state["last_complete_click_at"] = clicked_at
        session, exercise, training_set = current_training_items()
        if not exercise or rest_is_active(session):
            completion_prompt["key"] = ""
            return
        current_key = work_key(session, exercise, training_set)
        if completion_prompt.get("key") != current_key:
            completion_prompt["key"] = current_key
            refresh()
            return
        completion_prompt["key"] = ""
        exercise_index = safe_int(state.get("training_exercise_index", 0))
        set_index = safe_int(state.get("training_set_index", 0))
        mode = normalize_recording_mode(exercise.get("recording_mode"))
        if mode == "strength":
            if not training_set or training_set.get("completed"):
                return
            training_set["completed"] = True
            training_set["completed_at"] = iso_now()
        else:
            if exercise.get("completed") or int(to_float(exercise.get("duration_seconds"))) <= 0:
                return
            exercise["completed"] = True
            exercise["completed_at"] = iso_now()
        should_rest = advance_after_work(
            session,
            exercise_index,
            set_index,
        )
        cycle = None
        if should_rest:
            cycle = start_rest_cycle(90, datetime.datetime.now())
            session["rest_cycle"] = cycle
            session["rest_until"] = cycle["ends_at"]
        persist_session(session)
        if cycle:
            rest_notifier.trigger_after(str(cycle.get("id", "")), 90)
        refresh()

    def complete_rest_if_elapsed(session, now=None, record_date=None):
        cycle = session.get("rest_cycle") if isinstance(session, dict) else None
        if not isinstance(cycle, dict):
            return False
        finished, should_notify = finish_rest_cycle(cycle, now or datetime.datetime.now())
        if finished == cycle:
            return False
        session["rest_cycle"] = finished
        session["rest_until"] = ""
        persist_session(session, record_date=record_date)
        if should_notify:
            rest_notifier.trigger_foreground(str(finished.get("id", "")))
        return True

    def adjust_rest(seconds):
        session = session_data()
        cycle = session.get("rest_cycle") if session else None
        if not session or not isinstance(cycle, dict):
            return
        cycle_id = str(cycle.get("id", ""))
        rest_notifier.cancel(cycle_id)
        session["rest_cycle"] = adjust_rest_cycle(cycle, seconds, datetime.datetime.now())
        session["rest_until"] = session["rest_cycle"].get("ends_at", "") if session["rest_cycle"].get("status") == "running" else ""
        persist_session(session)
        if not complete_rest_if_elapsed(session) and session["rest_cycle"].get("status") == "running":
            remaining = rest_remaining_seconds(session["rest_cycle"], datetime.datetime.now())
            rest_notifier.trigger_after(cycle_id, remaining)
        refresh()

    def toggle_rest_pause(e=None):
        session = session_data()
        cycle = session.get("rest_cycle") if session else None
        if not session or not isinstance(cycle, dict):
            return
        cycle_id = str(cycle.get("id", ""))
        rest_notifier.cancel(cycle_id)
        if cycle.get("status") == "paused":
            cycle = resume_rest_cycle(cycle, datetime.datetime.now())
        else:
            cycle = pause_rest_cycle(cycle, datetime.datetime.now())
        session["rest_cycle"] = cycle
        session["rest_until"] = cycle.get("ends_at", "") if cycle.get("status") == "running" else ""
        persist_session(session)
        if cycle.get("status") == "running":
            rest_notifier.trigger_after(cycle_id, rest_remaining_seconds(cycle, datetime.datetime.now()))
        refresh()

    def skip_rest(e=None):
        session = session_data()
        cycle = session.get("rest_cycle") if session else None
        if not session or not isinstance(cycle, dict):
            return
        rest_notifier.cancel(str(cycle.get("id", "")), release_claim=False)
        session["rest_cycle"] = skip_rest_cycle(cycle, datetime.datetime.now())
        session["rest_until"] = ""
        persist_session(session)
        refresh()

    def finalize_session(incomplete=False):
        session = session_data()
        if not session:
            return
        active_rest = session.get("rest_cycle") if isinstance(session.get("rest_cycle"), dict) else None
        if active_rest:
            rest_notifier.cancel(str(active_rest.get("id", "")), release_claim=False)
        session = finalize_session_clock(session, datetime.datetime.now(), incomplete=incomplete)
        session["rest_until"] = ""
        session["rest_cycle"] = None
        state["training"]["total_duration_min"] = str(session["total_duration_min"])
        state["training"]["sessions"] = append_session_once(state["training"].get("sessions", []), session)
        persist_session(session)
        refresh()
        snack("未完整训练已保存" if incomplete else "训练完成，成绩已保存")

    def finish_session(e=None):
        session = session_data()
        if not session:
            return
        completion = session_completion_state(session)
        remaining_work = completion["remaining_work"]
        all_completed = completion["all_sets_completed"]
        dialog_width = responsive_width()
        confirm_dlg = dialog_base(
            "结束训练？",
            ft.Column([
                ft.Text(
                    "全部训练项目已完成。" if all_completed else f"还有 {remaining_work} 个训练项目没有完成。",
                    size=14,
                    weight="bold",
                    color=TEXT,
                ),
                small_text("确认结束并保存本次成绩，避免误触。" if all_completed else "可以继续训练，也可以按未完整训练保存当前成绩。"),
            ], width=dialog_width, spacing=8, tight=True),
            [
                ft.Container(
                    content=ft.Row([
                        make_button("继续训练", on_click=lambda e: close_control(confirm_dlg), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                        make_button("确认结束", on_click=lambda e: (close_control(confirm_dlg), finalize_session(not all_completed)), bgcolor="#FCECEC", color=RED, expand=True),
                    ], spacing=8),
                    width=dialog_width,
                ),
            ],
            on_close=lambda e: close_control(confirm_dlg),
        )
        open_control(confirm_dlg)

    def repeat_session(e=None):
        previous = session_data()
        if not previous:
            return
        session = copy_whole_session(previous, mode="replace", new_date=state.get("date"))
        state["training"]["session"] = session
        state["training_exercise_index"] = 0
        state["training_set_index"] = 0
        persist_session(session)
        refresh()

    # ---------- render ----------

    def render_training():
        tr = state["training"]
        target_controls = []
        for idx, t in enumerate(tr.get("targets", [])):
            intensity_text = t.get("intensity", "中等")
            target_controls.append(ft.Container(content=ft.Row([
                ft.Column([ft.Text(f"{t.get('target','')} · {intensity_text}", size=13, weight="bold", color=TEXT), small_text(f"{t.get('detail','')}" + (f"｜{t.get('note','')}" if t.get("note") else ""))], expand=True, spacing=1),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, icon_size=18, on_click=lambda e, i=idx: delete_training(i)),
            ]), bgcolor="#FAFAFA", border_radius=8, padding=8, margin=2))
        if not target_controls:
            target_controls.append(ft.Container(content=small_text("暂无训练目标"), bgcolor="#FAFAFA", border_radius=12, padding=10))

        duration_field = mobile_text_field(label="时长 min", value=tr.get("total_duration_min", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True, on_change=lambda e: (tr.update({"total_duration_min": e.control.value}), save_current()))
        calories_field = mobile_text_field(label="消耗 kcal", value=tr.get("total_calories_kcal", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True, on_change=lambda e: (tr.update({"total_calories_kcal": e.control.value}), save_current()))
        def save_training_note(e=None):
            tr["summary_note"] = note_field.value or ""
            save_current()
            refresh()

        note_field = mobile_text_field(label="训练备注", value=tr.get("summary_note", ""), expand=True, on_blur=save_training_note, on_submit=save_training_note)
        fatigue_dd = mobile_dropdown(label="状态", value=tr.get("fatigue_status", "状态一般"), options=[ft.dropdown.Option(x) for x in FATIGUE_OPTIONS], on_change=lambda e: (tr.update({"fatigue_status": e.control.value}), save_current(), refresh()), expand=True)

        return card(ft.Column([
            ft.Row([section_title("训练记录"), make_button("添加", on_click=lambda e: open_training_dialog(), icon=ft.Icons.ADD)], alignment="spaceBetween"),
            ft.Row([duration_field, calories_field], spacing=8, vertical_alignment="start"),
            note_field,
            fatigue_dd,
            ft.Column(target_controls, spacing=2),
        ], spacing=8))

    def render_current_training_workspace():
        session = session_model()
        raw_session = session_data()
        if not session or not raw_session:
            return build_empty_training(EmptyTrainingActions(
                reuse_history=reuse_history_session,
                create_free=lambda e: (create_empty_session(), refresh()),
                add_first=lambda e: open_add_exercise_dialog(),
            ))

        status = session.status
        if status == "completed":
            completed = completed_work_count(session)
            planned = planned_work_count(session)
            volume = session_volume(session)
            duration = session.total_duration_min or round(elapsed_seconds(raw_session) / 60, 1)
            return build_training_summary(
                session,
                title=session_summary_title(raw_session),
                duration_minutes=duration,
                completed_sets=completed,
                planned_sets=planned,
                volume_kg=volume,
                advice=training_carb_warning() or "训练成绩已计入今天记录，记得补充练后餐和水分。",
                actions=TrainingSummaryActions(
                    repeat=repeat_session,
                    create_new=lambda e: (create_empty_session(), refresh()),
                ),
            )

        if status == "active":
            session, exercise, training_set = current_training_items()
            model = TrainingSession.from_dict(session)
            completed = completed_work_count(model)
            planned = planned_work_count(model)
            rest_cycle = session.get("rest_cycle") if isinstance(session.get("rest_cycle"), dict) else None
            rest_status = rest_cycle.get("status") if rest_cycle else ""
            rest_seconds = rest_remaining_seconds(rest_cycle, datetime.datetime.now()) if rest_cycle else 0
            recording_mode = normalize_recording_mode(exercise.get("recording_mode")) if exercise else "strength"
            weight = to_float(training_set.get("weight_kg"), 0) if training_set else 0
            reps = int(to_float(training_set.get("reps"), 0)) if training_set else 0
            selected_set_done = bool(training_set and training_set.get("completed")) if recording_mode == "strength" else bool(exercise and exercise.get("completed"))
            group_label, group_position_text, group_members, next_work_text = active_group_context(session, exercise, training_set)
            if rest_status in {"running", "paused"}:
                next_work_text = current_pending_label(
                    exercise,
                    state.get("training_set_index", 0),
                    group_position_text,
                )
            current_key = work_key(session, exercise, training_set)

            def select_training_set(index):
                state["training_set_index"] = index
                completion_prompt["key"] = ""
                refresh()

            result = build_active_training(
                ActiveTrainingModel(
                    completed_sets=completed,
                    planned_sets=planned,
                    progress=session_work_progress(model),
                    elapsed_text=clock_text(elapsed_seconds(session)),
                    rest_status=rest_status,
                    rest_seconds=rest_seconds,
                    exercise_name=exercise.get("name", "当前动作") if exercise else "当前动作",
                    exercise_index=safe_int(state.get("training_exercise_index", 0)),
                    exercise_count=len(session.get("exercises", [])),
                    sets_completed=[bool(item.get("completed")) for item in exercise.get("sets", []) if isinstance(item, dict)] if exercise else [],
                    selected_set_index=safe_int(state.get("training_set_index", 0)),
                    weight_text=(
                        format_weight_kg(weight)
                        if recording_mode == "strength" and weight > 0
                        else "自重" if recording_mode == "strength" else ""
                    ),
                    reps=reps,
                    selected_set_done=selected_set_done,
                    recording_mode=recording_mode,
                    duration_seconds=max(0, int(to_float(exercise.get("duration_seconds")))) if exercise else 0,
                    distance_text="" if not exercise or exercise.get("distance_km") is None else f"{to_float(exercise.get('distance_km')):g}",
                    distance_enabled=bool(exercise and exercise.get("distance_enabled")),
                    cardio_metrics=tuple(
                        (
                            key,
                            CARDIO_METRIC_LABELS.get(key, key),
                            f"{to_float(exercise.get('cardio_metrics', {}).get(key)):g}" if exercise.get("cardio_metrics", {}).get(key) is not None else "未填写",
                        )
                        for key in exercise.get("cardio_metric_fields", [])
                        if key in CARDIO_METRIC_LABELS
                    ) if exercise else (),
                    group_label=group_label,
                    group_position_text=group_position_text,
                    group_members=group_members,
                    next_work_text=next_work_text,
                    confirm_complete=bool(current_key and completion_prompt.get("key") == current_key),
                    viewport_height=deps.viewport_height(),
                ),
                ActiveTrainingActions(
                    close=lambda e: set_view("today"),
                    finish=finish_session,
                    select_set=select_training_set,
                    adjust_rest=adjust_rest,
                    toggle_rest=toggle_rest_pause,
                    skip_rest=skip_rest,
                    adjust_weight=lambda direction: adjust_current("weight_kg", direction),
                    edit_weight=open_weight_editor,
                    adjust_reps=lambda direction: adjust_current("reps", direction),
                    edit_duration=open_duration_editor,
                    edit_distance=open_distance_editor,
                    edit_metric=open_cardio_metric_editor,
                    complete_or_undo=undo_current_set if selected_set_done else complete_current_set,
                    ask_complete=ask_complete_current,
                    cancel_complete=cancel_complete_current,
                    move_exercise=move_training,
                ),
            )
            training_clock_refs["elapsed"] = result.elapsed_control
            training_clock_refs["rest"] = result.rest_control
            return result.control


        def finish_exercise_drag(e=None):
            exercise_drag_state.update({"id": None, "active": False})

        def accept_exercise_drop(target_id):
            dragged_id = str(exercise_drag_state.get("id") or "")
            if not dragged_id or dragged_id == target_id:
                finish_exercise_drag()
                return
            raw_session["exercises"] = reorder_session_exercise_blocks(
                raw_session.get("exercises", []),
                raw_session.get("exercise_groups", []),
                dragged_id,
                target_id,
            )
            raw_session["exercise_groups"] = normalize_exercise_groups(raw_session["exercises"], raw_session.get("exercise_groups", []))
            persist_session(raw_session)
            finish_exercise_drag()
            refresh()

        def auto_scroll_exercise_drag(e):
            position = getattr(e, "global_position", None)
            y = float(getattr(position, "y", 0) or 0)
            offset = float(deps.current_scroll())
            if y and y < 150:
                deps.scroll_to(offset=max(0, offset - 28), duration=80)
            elif y > max(500, float(getattr(page, "height", 860) or 860) - 150):
                deps.scroll_to(offset=offset + 28, duration=80)

        return build_planned_training(raw_session, PlannedTrainingActions(
            start=start_session,
            add_exercise=lambda e: open_add_exercise_dialog(),
            delete_exercise=delete_session_exercise,
            reuse_history=reuse_history_session,
            clear=clear_today_training,
            group_exercise=open_exercise_group_dialog,
            show_help=open_planned_exercise_help,
            edit_exercise=open_edit_planned_exercise,
            drag_start=lambda exercise_id: exercise_drag_state.update({"id": exercise_id, "active": True}),
            drag_complete=finish_exercise_drag,
            drag_move=auto_scroll_exercise_drag,
            drag_accept=accept_exercise_drop,
        ))

    def completed_sessions_today() -> list[TrainingSession]:
        target_date = str(state.get("date") or "")
        return [
            TrainingSession.from_dict(item)
            for item in raw_training_sessions(state.get("training", {}))
            if str(item.get("status") or "") == "completed"
            and str(item.get("date") or target_date) == target_date
        ]

    def select_workspace_tab(value: str):
        workspace_tab["value"] = "completed" if value == "completed" else "current"
        refresh()

    def create_new_from_workspace(e=None):
        create_empty_session()
        workspace_tab["value"] = "current"
        refresh()

    def request_delete_completed_session(session_id: str):
        dialog_width = responsive_width()
        confirm_dlg = None

        def dismiss(e=None):
            close_control(confirm_dlg)

        def confirm(e=None):
            training = state.get("training", {})
            training["sessions"] = [
                item
                for item in training.get("sessions", [])
                if not isinstance(item, dict) or str(item.get("id") or "") != session_id
            ]
            current = training.get("session")
            if (
                isinstance(current, dict)
                and current.get("status") == "completed"
                and str(current.get("id") or "") == session_id
            ):
                training["session"] = None
            save_current()
            dismiss()
            refresh()
            snack("本场训练已删除")

        confirm_dlg = dialog_base(
            "删除本场训练？",
            ft.Container(
                content=small_text("只删除这一场已完成训练，不影响当天其他训练、饮食和动作库。"),
                width=dialog_width,
            ),
            [
                make_button("取消", on_click=dismiss, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                make_button("确认删除", on_click=confirm, bgcolor="#FCECEC", color=RED, expand=True),
            ],
            on_close=dismiss,
        )
        open_control(confirm_dlg)

    def render_training_workspace():
        raw_session = session_data()
        if isinstance(raw_session, dict) and raw_session.get("status") == "active":
            workspace_tab["value"] = "current"
            return render_current_training_workspace()

        completed_sessions = completed_sessions_today()
        actions = TrainingWorkspaceTabsActions(
            select_current=lambda e: select_workspace_tab("current"),
            select_completed=lambda e: select_workspace_tab("completed"),
            create_new=create_new_from_workspace,
            delete_session=request_delete_completed_session,
        )
        tabs = build_training_workspace_tabs(workspace_tab["value"], len(completed_sessions), actions)
        content = (
            build_today_completed_training(completed_sessions, actions)
            if workspace_tab["value"] == "completed"
            else render_current_training_workspace()
        )
        return ft.Column([tabs, content], spacing=0)

    return TrainingController(
        render_page=render_training_workspace,
        session_data=session_data,
        session_model=session_model,
        find_active_session_date=find_active_session_date,
        resume_session_date=resume_session_date,
        elapsed_seconds=elapsed_seconds,
        clock_text=clock_text,
        complete_rest_if_elapsed=complete_rest_if_elapsed,
        training_carb_warning=training_carb_warning,
        restore_cursor=restore_training_cursor,
    )


__all__ = ["TrainingController", "TrainingControllerDependencies", "create_training_controller"]
