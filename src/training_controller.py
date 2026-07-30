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
import flet_audio as fta

from app_defaults import ABS_ACTIONS, FATIGUE_OPTIONS, INTENSITY_OPTIONS, TRAINING_TARGETS
from app_state import AppState
from app_utils import to_float
from analytics_service import summarize_daily_training
from controller_runtime import ControllerRuntime
from exercise_library import (
    EXERCISE_CATEGORIES, delete_custom_exercise, exercise_catalog, load_custom_exercises,
    save_custom_exercise, search_exercises_with_fallback,
)
from form_views import FormViewContext, build_dialog, build_full_form_sheet
from repositories import AppRepositories
from training_clock_service import finalize_session_clock, session_elapsed_seconds
from training_experience_service import (
    BODY_PART_ORDER, adjust_weight_kg, adjust_rest_cycle, copy_whole_session, create_exercise_group, exercise_usage_stats,
    finish_rest_cycle, format_weight_kg, history_training_cards, normalize_weight_input,
    next_group_work, normalize_exercise_groups, pause_rest_cycle, remove_exercise_from_group,
    reorder_group_members, rest_remaining_seconds,
    reorder_session_exercise_blocks, resume_rest_cycle, skip_rest_cycle, sort_exercises, start_rest_cycle,
    undo_completed_set_result,
)
from training_models import TrainingSession, normalize_recording_mode
from training_picker_views import (
    CUSTOM_CARDIO_METRIC_FIELDS, bind_dialog_close_button, bind_training_parameter_mode,
    build_category_sidebar, build_exercise_card, build_exercise_help,
)
from training_plan_views import (
    EmptyTrainingActions, PlannedTrainingActions,
    build_action_arrangement_list, build_empty_training, build_planned_training,
)
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
    GREEN, ORANGE, PRIMARY, PRIMARY_SOFT, RED, SUB, SURFACE, TEXT, card, page_card,
    make_button, mobile_dropdown, mobile_text_field, responsive_field_grid,
    section_title, set_input_focused, small_text, thin_border, three_field_grid, two_field_grid,
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

CUSTOM_MUSCLE_OPTIONS = {
    "胸": ("胸大肌", "上胸", "中胸", "下胸"), "背": ("背阔肌", "上背", "中背", "下背"),
    "腿": ("股四头肌", "腘绳肌", "小腿", "内收肌", "外展肌"), "臀部": ("臀大肌", "臀中肌"),
    "肩": ("三角肌前束", "三角肌中束", "三角肌后束"), "二头": ("肱二头肌", "肱肌"),
    "三头": ("肱三头肌",), "小臂": ("前臂屈肌", "前臂伸肌"), "腹部": ("上腹", "下腹", "腹斜肌"),
    "核心稳定": ("腹横肌", "核心稳定"), "颈部": ("颈部肌群",), "有氧": ("心肺系统",),
    "热身动作": ("全身热身",), "拉伸": ("目标肌群拉伸",), "其他": ("其他",),
}
CUSTOM_EQUIPMENT_OPTIONS = ("杠铃", "哑铃", "壶铃", "绳索", "悍马机", "史密斯机", "器械", "TRX&弹力带", "自重", "其他")


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
    completion_audio = {"service": None}

    # Audio services must be attached while the page is being built. Creating one
    # only at the completion tap races the first play call on Android.
    try:
        completion_audio["service"] = fta.Audio(src="assets/training_complete.mp3", volume=1.0)
        page.services.append(completion_audio["service"])
    except Exception:
        completion_audio["service"] = None

    def play_completion_audio():
        """Play the bundled completion cue without affecting workout persistence."""
        try:
            audio = completion_audio["service"]
            if audio is None:
                return

            async def play_audio():
                try:
                    await audio.play()
                except Exception:
                    pass

            page.run_task(play_audio)
        except Exception:
            pass

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

    def full_form_sheet(title, controls, on_save, save_label="保存", header_action=None):
        return build_full_form_sheet(
            FormViewContext(close_control=close_control, scroll_mode=_SCROLL_HIDDEN),
            title,
            controls,
            on_save,
            save_label,
            header_action,
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

    def open_add_exercise_dialog(after_save=None):
        ensure_session()
        dialog_width = responsive_width()
        page_size = 24
        selected = {"category": "胸", "subgroup": "全部", "equipment": "全部", "sort": "frequent", "limit": page_size, "show_more_equipment": False}
        common_equipment_names = (
            "杠铃", "哑铃", "绳索", "史密斯机", "悍马机", "倒蹬机",
            "蝴蝶机", "器械", "自重",
        )
        selected_names: list[str] = []
        custom_exercises = load_custom_exercises()
        catalog = exercise_catalog(custom_exercises)
        categories = tuple(dict.fromkeys([*EXERCISE_CATEGORIES, *(item.get("category", "其他") for item in custom_exercises)]))
        # Leave more of the phone width to the filters and results while
        # keeping the body-part rail readable.
        equipment_panel_width = max(226, dialog_width - 64)
        # Rendering a whole body-part at once can mean hundreds of cards in
        # the web canvas. Keep the picker responsive and reveal more on demand.
        list_holder = ft.GridView(
            # Force one mobile column.  ``max_extent`` lets Flet switch to two
            # narrow columns at some phone widths, so keep the deliberate
            # large-card right margin as GridView padding instead.
            runs_count=1,
            # Phone cards need a real lower breathing area beneath the add
            # button and prescription, rather than inheriting desktop-tight
            # proportions from the original grid.
            child_aspect_ratio=2.25,
            spacing=8,
            run_spacing=8,
            expand=True,
            build_controls_on_demand=True,
            cache_extent=180,
            padding=ft.Padding(left=0, top=0, right=8, bottom=0),
        )
        load_more_holder = ft.Column(spacing=6)
        category_rows = ft.Column(spacing=3, width=68, scroll=_SCROLL_HIDDEN)
        subgroup_rows = ft.Row(spacing=6, scroll=_SCROLL_HIDDEN)
        equipment_rows = ft.Column(spacing=6, width=equipment_panel_width)
        selection_status = ft.Text("已选择 0 个动作", size=13, color=SUB, weight="bold")
        search_notice = ft.Text("", size=12, color=ORANGE, visible=False)
        search = mobile_text_field("搜索动作名称、器械或目标肌群", "", width=dialog_width)
        library_dlg = None
        pending_setup = {"dialog": None}
        keyboard_focus_target = {"control": None}

        def dismiss_search_focus(after_focus=None):
            """Move real focus off the search field before another surface opens."""
            set_input_focused(False)
            target = keyboard_focus_target.get("control")
            focus = getattr(target, "focus", None)

            async def transfer_focus():
                try:
                    if callable(focus):
                        await focus()
                except (AttributeError, RuntimeError, TypeError):
                    pass
                finally:
                    if after_focus is not None:
                        after_focus()

            if callable(focus):
                try:
                    page.run_task(transfer_focus)
                    return
                except (AttributeError, RuntimeError, TypeError):
                    pass
            if after_focus is not None:
                after_focus()

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
            def show_help():
                help_dlg = dialog_base(
                    exercise.get("name", "动作说明"),
                    build_exercise_help(exercise, dialog_width, _SCROLL_HIDDEN),
                    [ft.Container(content=make_button("知道了", on_click=lambda e: close_control(help_dlg), expand=True), width=dialog_width)],
                    on_close=lambda e: close_control(help_dlg),
                )
                open_control(help_dlg)

            dismiss_search_focus(show_help)

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
            initial_part = str(exercise.get("category") or "胸") if is_new_custom else "胸"
            if initial_part not in CUSTOM_MUSCLE_OPTIONS:
                initial_part = "其他"
            body_part = mobile_dropdown(
                "训练部位", initial_part,
                [ft.dropdown.Option(value, value) for value in CUSTOM_MUSCLE_OPTIONS], width=dialog_width,
            )
            initial_target = next(iter(exercise.get("target_muscles", [])), CUSTOM_MUSCLE_OPTIONS[initial_part][0])
            if initial_target not in CUSTOM_MUSCLE_OPTIONS[initial_part]:
                initial_target = CUSTOM_MUSCLE_OPTIONS[initial_part][0]
            target_muscle = mobile_dropdown(
                "目标肌群", initial_target,
                [ft.dropdown.Option(value, value) for value in CUSTOM_MUSCLE_OPTIONS[initial_part]], width=dialog_width,
            )
            initial_equipment = str(exercise.get("equipment") or "其他")
            if initial_equipment not in CUSTOM_EQUIPMENT_OPTIONS:
                initial_equipment = "其他"
            equipment = mobile_dropdown(
                "器械", initial_equipment,
                [ft.dropdown.Option(value, value) for value in CUSTOM_EQUIPMENT_OPTIONS], width=dialog_width,
            )

            def refresh_target_options(event=None):
                part = str(body_part.value or "其他")
                options = CUSTOM_MUSCLE_OPTIONS.get(part, CUSTOM_MUSCLE_OPTIONS["其他"])
                target_muscle.field.options = [ft.dropdown.Option(value, value) for value in options]
                if target_muscle.value not in options:
                    target_muscle.value = options[0]
                if event is not None:
                    page.update()

            body_part.field.on_select = refresh_target_options
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
                if after_save is not None:
                    after_save()

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
                        "category": str(body_part.value or "其他"),
                        "equipment": str(equipment.value or "其他"),
                        "target_muscles": [str(target_muscle.value or "其他")],
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
                    *([section_title("动作说明"), body_part, target_muscle, equipment, cues, mistakes] if is_new_custom else []),
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

        def confirm_delete_custom_exercise(exercise):
            exercise_name = str(exercise.get("name") or "").strip()
            if not exercise_name:
                return
            confirm_dlg = None

            def remove_definition(e=None):
                if not delete_custom_exercise(exercise_name):
                    snack("未找到可删除的自定义动作")
                    return
                custom_exercises[:] = [
                    item for item in custom_exercises
                    if str(item.get("name") or "").casefold() != exercise_name.casefold()
                ]
                catalog[:] = exercise_catalog(custom_exercises)
                if exercise_name in selected_names:
                    selected_names.remove(exercise_name)
                selection_status.value = f"已选择 {len(selected_names)} 个动作"
                close_control(confirm_dlg)
                rebuild_list()
                page.update()
                snack("已删除自定义动作；历史与当前计划不受影响")

            confirm_dlg = dialog_base(
                "删除自定义动作？",
                ft.Column([
                    ft.Text(exercise_name, size=17, weight="bold"),
                    small_text("仅从动作库移除，不会影响历史训练或当前已加入计划的动作。"),
                ], spacing=8),
                [
                    make_button("取消", on_click=lambda e: close_control(confirm_dlg), expand=True),
                    make_button("确认删除", on_click=remove_definition, bgcolor="#C73B3B", color="#FFFFFF", expand=True),
                ],
                on_close=lambda e: close_control(confirm_dlg),
            )
            open_control(confirm_dlg)

        def exercise_row(exercise):
            usage = usage_stats.get(str(exercise.get("name", "")).casefold(), {})
            exercise_name = str(exercise.get("name") or "")
            return build_exercise_card(
                exercise,
                usage,
                lambda e, item=exercise: open_help(item),
                lambda e, item=exercise: toggle_exercise(item),
                selected=exercise_name in selected_names,
                on_delete=None,
                title_width=max(140, equipment_panel_width - 110),
            )

        def toggle_exercise(exercise):
            def apply_toggle():
                exercise_name = str(exercise.get("name") or "")
                if exercise_name in selected_names:
                    selected_names.remove(exercise_name)
                elif exercise_name:
                    selected_names.append(exercise_name)
                selection_status.value = f"已选择 {len(selected_names)} 个动作"
                rebuild_list()
                page.update()

            dismiss_search_focus(apply_toggle)

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
            category_rows.controls.extend(build_category_sidebar(categories, selected["category"], choose_category))

        def estimate_equipment_width(label):
            # Matches make_button's 14px text and 20px horizontal padding.
            ascii_count = sum(1 for char in label if ord(char) < 128)
            visual_units = len(label) + ascii_count * 0.35
            return min(equipment_panel_width, max(62, int(visual_units * 15 + 30)))

        def pack_equipment_controls(items, ordered_count):
            """Pack ordered popular tools first, then let rare tools fill gaps."""
            rows = []
            used_widths = []
            for index, (label, control) in enumerate(items):
                width = estimate_equipment_width(label)
                control.width = width
                target = None
                if index < ordered_count:
                    if rows and used_widths[-1] + 6 + width <= equipment_panel_width:
                        target = len(rows) - 1
                else:
                    for row_index, used in enumerate(used_widths):
                        if used + 6 + width <= equipment_panel_width:
                            target = row_index
                            break
                if target is None:
                    rows.append([control])
                    used_widths.append(width)
                else:
                    rows[target].append(control)
                    used_widths[target] += 6 + width
            return [ft.Row(row, spacing=6, width=equipment_panel_width) for row in rows]

        def rebuild_filters():
            visible = [item for item in catalog if item.get("category") == selected["category"]]
            subgroups = list(dict.fromkeys(str(item.get("subgroup") or "整体") for item in visible))
            if selected["subgroup"] not in subgroups:
                selected["subgroup"] = "全部"
            filtered_visible = visible if selected["subgroup"] == "全部" else [
                item for item in visible
                if str(item.get("subgroup") or "整体") == selected["subgroup"]
            ]
            # Only show equipment that exists for the current body-part and
            # subgroup; e.g. abductor work does not advertise barbells.
            equipment = list(dict.fromkeys(str(item.get("equipment") or "其他") for item in filtered_visible))
            equipment_priority = (
                *common_equipment_names, "大剪刀", "鹦鹉螺机", "腿屈伸机",
                "腿弯举机", "髋内收外展机", "壶铃", "弹力带", "健身球",
                "TRX&弹力带", "其他",
            )
            priority_index = {value: index for index, value in enumerate(equipment_priority)}
            equipment.sort(key=lambda value: (priority_index.get(value, len(priority_index)), value))
            # “全部”是虚拟选项，不属于动作库的器械值；展开冷门器械时
            # 必须保留它，否则 rebuild 会立即把展开状态重置掉。
            if selected["equipment"] != "全部" and selected["equipment"] not in equipment:
                selected["equipment"] = "全部"
                selected["show_more_equipment"] = False
            subgroup_rows.controls = [
                make_button(label, on_click=lambda e, value=label: choose_subgroup(value), bgcolor=PRIMARY if selected["subgroup"] == label else PRIMARY_SOFT, color="#FFFFFF" if selected["subgroup"] == label else GREEN)
                for label in ["全部", *subgroups]
            ]
            common_equipment = [item for item in equipment if item in common_equipment_names]
            other_equipment = [item for item in equipment if item not in common_equipment]

            def equipment_button(label):
                return make_button(
                    label,
                    on_click=lambda e, value=label: choose_equipment(value),
                    bgcolor=PRIMARY if selected["equipment"] == label else PRIMARY_SOFT,
                    color="#FFFFFF" if selected["equipment"] == label else GREEN,
                )

            if selected["show_more_equipment"]:
                popular_labels = ["全部", *common_equipment]
                expanded_items = [(label, equipment_button(label)) for label in [*popular_labels, *other_equipment]]
                expanded_items.append((
                    "收起器械",
                    make_button("收起器械", on_click=lambda e: toggle_more_equipment(), bgcolor=PRIMARY_SOFT, color=GREEN),
                ))
                controls = pack_equipment_controls(expanded_items, len(popular_labels))
            else:
                # Keep common equipment in one horizontally expandable strip;
                # rare equipment only appears after the explicit more action.
                pinned = [selected["equipment"]] if selected["equipment"] in other_equipment else []
                compact_labels = ["全部", *pinned, *common_equipment]
                compact_items = [(label, equipment_button(label)) for label in compact_labels]
                compact_row = ft.Row(
                    [
                        *[control for _label, control in compact_items],
                        *([make_button(
                            "更多器械",
                            on_click=lambda e: toggle_more_equipment(),
                            bgcolor=PRIMARY_SOFT,
                            color=GREEN,
                        )] if [item for item in other_equipment if item not in pinned] else []),
                    ],
                    spacing=6,
                    width=equipment_panel_width,
                    scroll=_SCROLL_HIDDEN,
                )
                controls = [compact_row]
            equipment_rows.controls = controls

        def choose_category(category):
            selected["category"] = category
            selected["limit"] = page_size
            selected["show_more_equipment"] = False
            rebuild_categories()
            rebuild_filters()
            rebuild_list()
            page.update()

        def choose_subgroup(subgroup):
            selected["subgroup"] = subgroup
            selected["limit"] = page_size
            rebuild_filters()
            rebuild_list()
            page.update()

        def choose_equipment(equipment):
            was_expanded = selected["show_more_equipment"]
            selected["equipment"] = equipment
            # Choosing a normal compact option returns the selector to compact
            # mode, which also releases a previously pinned uncommon option.
            if equipment == "全部" or equipment in common_equipment_names:
                selected["show_more_equipment"] = False
            selected["limit"] = page_size
            rebuild_filters()
            rebuild_list()
            page.update()

        def toggle_more_equipment():
            selected["show_more_equipment"] = not selected["show_more_equipment"]
            rebuild_filters()
            page.update()

        def load_more(e=None):
            selected["limit"] += page_size
            rebuild_list()
            page.update()

        def on_search_change(e=None):
            selected["limit"] = page_size
            rebuild_list(e)

        def rebuild_list(e=None):
            query = (search.value or "").strip()
            # Respect the current filters first.  A real search term may then
            # relax over-specific filters so familiar names never lead to a
            # blank page merely because the catalog classified the variant in
            # another subgroup, tool, or body part.
            results, fallback_scope = search_exercises_with_fallback(
                query,
                selected["category"],
                selected["subgroup"],
                selected["equipment"],
                catalog,
            )
            search_notice.visible = bool(fallback_scope)
            search_notice.value = (
                "当前部位没有结果，已显示其他部位的同名动作"
                if fallback_scope == "category"
                else "当前细分肌群或器械没有结果，已为你放宽筛选"
                if fallback_scope == "filters"
                else ""
            )
            # Text search is ordered by exact/common-name relevance.  The
            # popular/recent order remains the default only when browsing.
            if not query:
                results = sort_exercises(results, usage_stats, selected["sort"])
            total_results = len(results)
            rendered_results = results[:selected["limit"]]
            list_holder.controls.clear()
            list_holder.controls.extend(exercise_row(item) for item in rendered_results)
            load_more_holder.controls.clear()
            if total_results > len(rendered_results):
                load_more_holder.controls.append(make_button(
                    f"加载更多（已显示 {len(rendered_results)}/{total_results}）",
                    on_click=load_more,
                    bgcolor=PRIMARY_SOFT,
                    color=GREEN,
                    expand=True,
                ))
            if not results:
                list_holder.controls.append(ft.Container(content=small_text("没有匹配动作，可使用下方自定义动作"), bgcolor=SURFACE, border_radius=10, padding=12))
            if e is not None:
                page.update()

        search.on_change = on_search_change
        rebuild_categories()
        rebuild_filters()
        rebuild_list()
        custom_item = {"name": "", "category": "自定义", "equipment": "其他", "target_muscles": [], "cues": [], "mistakes": [], "default_weight_kg": None, "default_reps": 10, "default_sets": 4, "recording_mode": "strength", "distance_enabled": True}
        browser_panel = ft.Row([
            ft.Container(content=category_rows, width=52, padding=ft.Padding(left=0, top=0, right=0, bottom=0)),
            ft.VerticalDivider(width=1, color="#D9E6E1"),
            ft.Column([subgroup_rows, equipment_rows, search_notice, selection_status, list_holder, load_more_holder], width=equipment_panel_width, spacing=8),
        ], width=dialog_width, height=560, spacing=8)
        add_custom_action = ft.IconButton(
            icon=ft.Icons.ADD,
            tooltip="新建自定义动作",
            width=48,
            height=48,
            icon_color=PRIMARY,
            on_click=lambda e: open_setup(custom_item),
        )
        keyboard_focus_target["control"] = add_custom_action
        library_dlg = full_form_sheet(
            f"添加动作 · {len(catalog)} 个",
            [search, browser_panel],
            add_selected_exercises,
            save_label="添加已选动作",
            header_action=add_custom_action,
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

    def bodyweight_weight_field(value=""):
        control = mobile_text_field(
            "重量 kg",
            value,
            keyboard_type=_KEYBOARD_NUMBER,
            hint_text="自重留空",
            expand=True,
        )
        control.field.hint_style = ft.TextStyle(color="#98A39F", size=14)
        control.field.content_padding = ft.Padding(left=10, top=12, right=8, bottom=12)
        return control

    def build_action_summary_controls(exercise):
        source_exercise = next(
            (
                item for item in exercise_catalog(load_custom_exercises())
                if str(item.get("id") or "") == str(exercise.get("exercise_id") or "")
            ),
            {},
        )
        mode = normalize_recording_mode(exercise.get("recording_mode"))
        mode_label = {"strength": "力量", "timed": "计时", "cardio": "有氧"}[mode]
        controls: list[ft.Control] = [
            small_text(f"记录模式：{mode_label}"),
        ]
        media_src = str(source_exercise.get("gif") or source_exercise.get("image") or "")
        if media_src:
            controls.append(ft.Container(
                content=ft.Image(src=media_src, height=190, fit="contain"),
                height=206,
                alignment=ft.Alignment(0, 0),
                bgcolor="#FFFFFF",
                border_radius=12,
                padding=8,
            ))
        cues = [str(cue).strip() for cue in source_exercise.get("cues", []) if str(cue).strip()]
        if cues:
            controls.extend([
                section_title("动作要点"),
                ft.Column(
                    [ft.Text(f"{index}. {cue}", size=13, color=TEXT) for index, cue in enumerate(cues, 1)],
                    spacing=5,
                ),
            ])
        return controls

    def open_edit_planned_exercise(exercise_id):
        session, exercise = planned_exercise(exercise_id)
        if not session or not exercise or session.get("status") == "active":
            return
        dialog_width = responsive_width()
        mode = normalize_recording_mode(exercise.get("recording_mode"))
        raw_sets = [item for item in exercise.get("sets", []) if isinstance(item, dict)]
        first_set = raw_sets[0] if raw_sets else {}
        weight = bodyweight_weight_field(
            "" if to_float(first_set.get("weight_kg")) <= 0 else f"{to_float(first_set.get('weight_kg')):g}"
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
        summary_controls = build_action_summary_controls(exercise)
        controls: list[ft.Control] = [
            section_title(str(exercise.get("name") or "编辑动作")),
            summary_controls[0],
        ]
        if mode == "strength":
            controls.append(three_field_grid(weight, reps, sets, viewport_width=dialog_width))
        else:
            controls.append(two_field_grid(duration_min, duration_sec, viewport_width=dialog_width))
            if mode == "cardio" and exercise.get("distance_enabled"):
                controls.append(distance)
            if mode == "cardio" and metric_fields:
                controls.append(responsive_field_grid(list(metric_fields.values()), columns=2, viewport_width=dialog_width))
        controls.extend(summary_controls[1:])
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
            try:
                copied = copy_whole_session(
                    card_item["session"], current, mode=mode, new_date=state.get("date")
                )
            except ValueError as exc:
                snack(str(exc))
                return
            state["training"]["session"] = copied
            state["training_exercise_index"] = 0
            state["training_set_index"] = 0
            persist_session(copied)
            refresh()
            snack(f"已复用 {card_item['combination']} 训练")

        def choose_card(card_item):
            current = session_data()
            has_plan = bool(current and current.get("exercises"))
            if not has_plan:
                close_control(history_dlg)
                apply_card(card_item, "replace")
                return
            confirm_dlg = None

            def dismiss_confirm(e=None):
                if confirm_dlg is not None:
                    close_control(confirm_dlg)
                open_control(history_dlg)

            def apply_confirmed(mode):
                if confirm_dlg is not None:
                    close_control(confirm_dlg)
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
            # Keep only one modal open. Nested dialogs intermittently swallow taps on Android.
            close_control(history_dlg)
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

    def open_exercise_group_dialog(base_exercise_id, after_save=None):
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
            if len(member_ids) < 2:
                if existing_group is None:
                    snack("至少选择两个动作")
                    return
                existing_group_id = str(existing_group.get("id") or "")
                session["exercise_groups"] = normalize_exercise_groups(
                    session.get("exercises", []),
                    [
                        group for group in session.get("exercise_groups", [])
                        if not isinstance(group, dict) or str(group.get("id") or "") != existing_group_id
                    ],
                )
                persist_session(session)
                close_control(dlg)
                if after_save is not None:
                    after_save()
                else:
                    refresh()
                snack("已解除动作组合，动作均已保留")
                return
            try:
                session["exercise_groups"] = create_exercise_group(
                    session.get("exercises", []),
                    session.get("exercise_groups", []),
                    member_ids,
                    str(group_type.value or ""),
                )
            except ValueError as exc:
                snack("至少选择两个有效动作" if "at least two" in str(exc) else "动作组合设置无效")
                return
            persist_session(session)
            close_control(dlg)
            if after_save is not None:
                after_save()
            else:
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

    def delete_session_exercise(exercise_id):
        session = session_data()
        if not session or session.get("status") == "active":
            return
        exercises = session.get("exercises", [])
        index = next(
            (position for position, item in enumerate(exercises) if str(item.get("id") or "") == str(exercise_id)),
            None,
        )
        if index is not None:
            exercises.pop(index)
        session["exercise_groups"] = normalize_exercise_groups(exercises, session.get("exercise_groups", []))
        persist_session(session)
        refresh()

    def delete_exercise_group(base_exercise_id):
        session = session_data()
        if not session or session.get("status") == "active":
            return
        groups = session.get("exercise_groups", [])
        group = next((
            item for item in groups
            if isinstance(item, dict) and str(base_exercise_id) in {str(member) for member in item.get("exercise_ids", [])}
        ), None)
        if group is None:
            return
        group_id = str(group.get("id") or "")
        session["exercise_groups"] = [
            item for item in groups
            if not isinstance(item, dict) or str(item.get("id") or "") != group_id
        ]
        session["exercise_groups"] = normalize_exercise_groups(
            session.get("exercises", []), session["exercise_groups"]
        )
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
        if not session or not training_set:
            return
        current_weight = training_set.get("weight_kg")
        field = bodyweight_weight_field(
            "" if to_float(current_weight) <= 0 else format_weight_kg(current_weight)
        )
        dlg = None

        def save_weight(_=None):
            try:
                raw_value = str(field.field.value or "").strip()
                training_set["weight_kg"] = (
                    0.0 if raw_value in {"", "自重"} else normalize_weight_input(raw_value)
                )
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

    def open_reps_editor(e=None):
        session, exercise, training_set = current_training_items()
        if not session or not training_set:
            return
        field = mobile_text_field(
            "次数",
            str(max(0, int(to_float(training_set.get("reps"), 0)))),
            width=responsive_width(),
            keyboard_type=_KEYBOARD_NUMBER,
        )
        dlg = None

        def save_reps(_=None):
            reps = max(0, int(to_float(field.field.value, 0)))
            if reps <= 0:
                snack("请填写有效次数")
                return
            training_set["reps"] = reps
            persist_session(session)
            close_control(dlg)
            refresh()

        dlg = dialog_base(
            "编辑本组次数",
            ft.Column([field], width=responsive_width(), spacing=8, tight=True),
            [ft.Container(content=ft.Row([
                make_button("取消", on_click=lambda event: close_control(dlg), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                make_button("确认", on_click=save_reps, expand=True),
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

    def training_cursor_sequence(session):
        exercises = normalized_session_exercises(session)
        if not exercises:
            return []
        positions = {str(item.get("id") or ""): index for index, item in enumerate(exercises)}
        groups = {
            str(item.get("id") or ""): item
            for item in session.get("exercise_groups", [])
            if isinstance(item, dict) and str(item.get("id") or "")
        }
        visited_groups = set()
        sequence = []

        def append_exercise(exercise_index, exercise):
            if normalize_recording_mode(exercise.get("recording_mode")) == "strength":
                sequence.extend(
                    (exercise_index, set_index)
                    for set_index, item in enumerate(exercise.get("sets", []))
                    if isinstance(item, dict)
                )
            else:
                sequence.append((exercise_index, 0))

        for exercise_index, exercise in enumerate(exercises):
            group_id = str(exercise.get("group_id") or "")
            group = groups.get(group_id)
            if not group:
                append_exercise(exercise_index, exercise)
                continue
            if group_id in visited_groups:
                continue
            visited_groups.add(group_id)
            members = [
                (positions[member_id], exercises[positions[member_id]])
                for member_id in (str(item) for item in group.get("exercise_ids", []))
                if member_id in positions
            ]
            max_rounds = max((
                len(member.get("sets", []))
                if normalize_recording_mode(member.get("recording_mode")) == "strength" else 1
                for _, member in members
            ), default=0)
            for round_index in range(max_rounds):
                for member_index, member in members:
                    if normalize_recording_mode(member.get("recording_mode")) == "strength":
                        sets = member.get("sets", [])
                        if round_index < len(sets) and isinstance(sets[round_index], dict):
                            sequence.append((member_index, round_index))
                    elif round_index == 0:
                        sequence.append((member_index, 0))
        return sequence

    def training_completion_sequence(session, cursor_sequence=None):
        exercises = normalized_session_exercises(session)
        sequence = cursor_sequence if cursor_sequence is not None else training_cursor_sequence(session)
        completed = []
        for exercise_index, set_index in sequence:
            if not (0 <= exercise_index < len(exercises)):
                completed.append(False)
                continue
            exercise = exercises[exercise_index]
            if normalize_recording_mode(exercise.get("recording_mode")) == "strength":
                sets = exercise.get("sets", [])
                completed.append(
                    bool(sets[set_index].get("completed"))
                    if 0 <= set_index < len(sets) and isinstance(sets[set_index], dict)
                    else False
                )
            else:
                completed.append(bool(exercise.get("completed")))
        return tuple(completed)

    def move_training(direction):
        session, exercise, training_set = current_training_items()
        sequence = training_cursor_sequence(session)
        if not sequence:
            return
        current = (
            safe_int(state.get("training_exercise_index", 0)),
            safe_int(state.get("training_set_index", 0)),
        )
        try:
            position = sequence.index(current)
        except ValueError:
            position = next((index for index, item in enumerate(sequence) if item[0] == current[0]), 0)
        target = sequence[max(0, min(len(sequence) - 1, position + int(direction)))]
        state["training_exercise_index"], state["training_set_index"] = target
        completion_prompt["key"] = ""
        refresh()

    def adjust_current_set_count(direction):
        session, exercise, training_set = current_training_items()
        if not session or not exercise or normalize_recording_mode(exercise.get("recording_mode")) != "strength":
            snack("当前动作不使用组数")
            return
        sets = exercise.setdefault("sets", [])
        pending_before = [
            index for index, item in enumerate(sets)
            if isinstance(item, dict) and not item.get("completed")
        ]
        if int(direction) > 0:
            source = training_set if isinstance(training_set, dict) else (sets[-1] if sets else {})
            sets.append({
                "id": f"set_{uuid.uuid4().hex}",
                "order": len(sets) + 1,
                "weight_kg": max(0, to_float(source.get("weight_kg"))),
                "reps": max(0, safe_int(source.get("reps"))),
                "completed": False,
                "warmup": bool(source.get("warmup", False)),
                "completed_at": "",
            })
            if not pending_before:
                state["training_set_index"] = len(sets) - 1
            message = "已增加一组"
        else:
            if len(sets) <= 1:
                snack("每个力量动作至少保留一组")
                return
            selected_index = safe_int(state.get("training_set_index", 0))
            remove_index = (
                selected_index
                if selected_index in pending_before
                else pending_before[-1] if pending_before else None
            )
            if remove_index is None:
                snack("已完成的组不能删除")
                return
            sets.pop(remove_index)
            for index, item in enumerate(sets):
                if isinstance(item, dict):
                    item["order"] = index + 1
            state["training_set_index"] = min(remove_index, len(sets) - 1)
            message = "已减少一组"
        completion_prompt["key"] = ""
        persist_session(session)
        refresh()
        snack(message)

    def open_active_action_manager(event=None):
        session, current_exercise, _training_set = current_training_items()
        exercises = normalized_session_exercises(session)
        if not session or not exercises:
            snack("当前没有可调整的动作")
            return
        dialog_width = responsive_width()
        rows_slot = ft.Column(spacing=0)
        manager_dlg = None

        def current_exercise_id():
            _session, exercise, _set = current_training_items()
            return str(exercise.get("id") or "") if exercise else ""

        def open_edit_active_exercise(exercise_id):
            item = next(
                (value for value in exercises if str(value.get("id") or "") == str(exercise_id)),
                None,
            )
            if not item or normalize_recording_mode(item.get("recording_mode")) != "strength":
                snack("当前动作不支持重量和组数编辑")
                return
            raw_sets = [value for value in item.get("sets", []) if isinstance(value, dict)]
            last_completed_index = max(
                (index for index, value in enumerate(raw_sets) if value.get("completed")),
                default=-1,
            )
            locked_set_count = last_completed_index + 1
            template = (
                raw_sets[locked_set_count]
                if locked_set_count < len(raw_sets)
                else raw_sets[-1] if raw_sets else {}
            )
            width = responsive_width()
            weight = bodyweight_weight_field(
                "" if to_float(template.get("weight_kg")) <= 0 else f"{to_float(template.get('weight_kg')):g}"
            )
            reps = mobile_text_field(
                "次数",
                "" if template.get("reps") is None else str(int(to_float(template.get("reps")))),
                keyboard_type=_KEYBOARD_NUMBER,
                expand=True,
            )
            sets = mobile_text_field("组数", str(max(1, len(raw_sets))), keyboard_type=_KEYBOARD_NUMBER, expand=True)
            edit_dlg = None

            def save_edit(event=None):
                set_count = max(1, min(12, int(to_float(sets.value, len(raw_sets) or 1))))
                if set_count < locked_set_count:
                    snack(f"组数不能截断第 {locked_set_count} 个已完成组")
                    return
                weight_value = max(0, to_float(weight.value))
                reps_value = max(0, int(to_float(reps.value)))
                updated_sets = []
                for index in range(set_count):
                    original = raw_sets[index] if index < len(raw_sets) else {}
                    if index < locked_set_count:
                        updated = dict(original)
                    else:
                        updated = {
                            **original,
                            "weight_kg": weight_value,
                            "reps": reps_value,
                            "completed": False,
                            "warmup": False,
                            "completed_at": "",
                        }
                    updated.update({
                        "id": str(updated.get("id") or f"set_{uuid.uuid4().hex}"),
                        "order": index + 1,
                    })
                    updated_sets.append(updated)
                item["sets"] = updated_sets
                persist_session(session)
                close_control(edit_dlg)
                rebuild_rows()
                refresh()
                snack(f"已更新 {item.get('name', '动作')} 参数")

            summary_controls = build_action_summary_controls(item)
            edit_dlg = full_form_sheet(
                "编辑训练参数",
                [
                    section_title(str(item.get("name") or "编辑动作")),
                    summary_controls[0],
                    three_field_grid(weight, reps, sets, viewport_width=width),
                    *summary_controls[1:],
                ],
                save_edit,
                save_label="保存修改",
            )
            open_control(edit_dlg)

        def persist_order(active_id):
            for index, item in enumerate(exercises):
                item["order"] = index + 1
            session["exercises"] = exercises
            session["exercise_groups"] = normalize_exercise_groups(
                exercises,
                session.get("exercise_groups", []),
            )
            persist_session(session)
            current_index = min(
                safe_int(state.get("training_exercise_index", 0)),
                len(exercises) - 1,
            )
            if active_id:
                current_index = next(
                    (
                        index for index, item in enumerate(exercises)
                        if str(item.get("id") or "") == active_id
                    ),
                    current_index,
                )
            state["training_exercise_index"] = max(0, current_index)
            state["training_set_index"] = min(
                safe_int(state.get("training_set_index", 0)),
                max(0, len(exercises[state["training_exercise_index"]].get("sets", [])) - 1),
            )

        def reorder_action(dragged_id, target_id):
            if not dragged_id or dragged_id == target_id:
                return
            active_id = current_exercise_id()
            reordered = reorder_session_exercise_blocks(
                exercises,
                session.get("exercise_groups", []),
                dragged_id,
                target_id,
            )
            exercises[:] = reordered
            persist_order(active_id)
            rebuild_rows()
            page.update()

        def reorder_action_group_member(dragged_id, target_id):
            active_id = current_exercise_id()
            exercises[:] = reorder_group_members(
                exercises,
                session.get("exercise_groups", []),
                dragged_id,
                target_id,
            )
            persist_order(active_id)
            rebuild_rows()
            page.update()

        def remove_action_group_member(exercise_id):
            active_id = current_exercise_id()
            session["exercise_groups"] = remove_exercise_from_group(
                exercises,
                session.get("exercise_groups", []),
                exercise_id,
            )
            persist_order(active_id)
            rebuild_rows()
            page.update()
            snack("已将动作移出组合")

        def remove_action(exercise_id):
            if len(exercises) <= 1:
                snack("训练中至少保留一个动作")
                return
            index = next(
                (idx for idx, item in enumerate(exercises) if str(item.get("id") or "") == str(exercise_id)),
                None,
            )
            if index is None:
                return
            item = exercises[index]
            completed = bool(item.get("completed")) or any(
                isinstance(training_set, dict) and training_set.get("completed")
                for training_set in item.get("sets", [])
            )
            if completed:
                snack("已经完成过组数的动作不能删除")
                return
            active_id = current_exercise_id()
            removed_id = str(item.get("id") or "")
            exercises.pop(index)
            persist_order("" if active_id == removed_id else active_id)
            if active_id == removed_id:
                state["training_exercise_index"] = min(index, len(exercises) - 1)
                state["training_set_index"] = 0
            rebuild_rows()
            page.update()
            snack("已删除未完成动作")

        def remove_action_group(exercise_id):
            group = next((
                value for value in session.get("exercise_groups", [])
                if isinstance(value, dict) and str(exercise_id) in {
                    str(member_id) for member_id in value.get("exercise_ids", [])
                }
            ), None)
            if group is None:
                return
            group_id = str(group.get("id") or "")
            session["exercise_groups"] = [
                value for value in session.get("exercise_groups", [])
                if not isinstance(value, dict) or str(value.get("id") or "") != group_id
            ]
            session["exercise_groups"] = normalize_exercise_groups(
                exercises,
                session["exercise_groups"],
            )
            persist_session(session)
            rebuild_rows()
            page.update()
            snack("已解除动作组合")

        def refresh_manager_after_group():
            nonlocal session, exercises
            # Persisting a session replaces the state object with a normalized
            # copy. Rebind the still-open manager to that fresh object so the
            # new combination appears immediately, without closing and
            # reopening this sheet.
            fresh_session = session_data()
            if isinstance(fresh_session, dict):
                session = fresh_session
                exercises = normalized_session_exercises(session)
            rebuild_rows()
            page.update()

        def edit_action_group(exercise_id):
            open_exercise_group_dialog(
                exercise_id,
                after_save=refresh_manager_after_group,
            )

        def rebuild_rows():
            completed_counts = {
                str(item.get("id") or ""): sum(
                    1 for training_set in item.get("sets", [])
                    if isinstance(training_set, dict) and training_set.get("completed")
                )
                for item in exercises
            }
            rows_slot.controls = [build_action_arrangement_list(
                session,
                edit_exercise=open_edit_active_exercise,
                group_exercise=edit_action_group,
                delete_exercise=remove_action,
                delete_group=remove_action_group,
                reorder_exercise=reorder_action,
                reorder_group_member=reorder_action_group_member,
                remove_group_member=remove_action_group_member,
                completed_counts=completed_counts,
                max_height=520,
                data="active-action-reorder-list",
            )]

        def add_action(event=None):
            close_control(manager_dlg)
            open_add_exercise_dialog(after_save=open_active_action_manager)

        def finish_manager(event=None):
            current_session = session_data()
            current_cycle = current_session.get("rest_cycle") if isinstance(current_session, dict) else None
            if (
                isinstance(current_cycle, dict)
                and current_cycle.get("status") == "running"
                and rest_remaining_seconds(current_cycle, datetime.datetime.now()) <= 0
            ):
                complete_rest_if_elapsed(current_session)
            close_control(manager_dlg)
            refresh()

        rebuild_rows()
        manager_dlg = full_form_sheet(
            "调整动作顺序",
            [
                make_button(
                    "增加动作",
                    on_click=add_action,
                    icon=ft.Icons.ADD,
                    bgcolor=PRIMARY_SOFT,
                    color=GREEN,
                    expand=True,
                ),
                rows_slot,
            ],
            finish_manager,
            save_label="完成",
        )
        open_control(manager_dlg)

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
            # A visible app must always attempt its bundled player.  The
            # notifier ignores this call while paused/hidden, where the native
            # AlarmManager remains responsible for delivery.
            trigger_foreground = getattr(rest_notifier, "trigger_foreground", None)
            if callable(trigger_foreground):
                trigger_foreground(str(finished.get("id", "")))
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
        if not incomplete:
            play_completion_audio()
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

        return page_card(ft.Column([
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
            cursor_sequence = training_cursor_sequence(session)
            cursor_position = (
                safe_int(state.get("training_exercise_index", 0)),
                safe_int(state.get("training_set_index", 0)),
            )
            try:
                current_work_index = cursor_sequence.index(cursor_position)
            except ValueError:
                current_work_index = 0

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
                    viewport_width=float(getattr(page, "width", 430) or 430),
                    current_work_index=current_work_index,
                    work_completed=training_completion_sequence(session, cursor_sequence),
                ),
                ActiveTrainingActions(
                    close=lambda e: set_view("today"),
                    finish=finish_session,
                    show_help=lambda e: open_planned_exercise_help(str(exercise.get("id") or "")) if exercise else None,
                    select_set=select_training_set,
                    adjust_rest=adjust_rest,
                    toggle_rest=toggle_rest_pause,
                    skip_rest=skip_rest,
                    adjust_weight=lambda direction: adjust_current("weight_kg", direction),
                    edit_weight=open_weight_editor,
                    adjust_reps=lambda direction: adjust_current("reps", direction),
                    edit_reps=open_reps_editor,
                    edit_duration=open_duration_editor,
                    edit_distance=open_distance_editor,
                    edit_metric=open_cardio_metric_editor,
                    complete_or_undo=undo_current_set if selected_set_done else complete_current_set,
                    ask_complete=ask_complete_current,
                    cancel_complete=cancel_complete_current,
                    move_exercise=move_training,
                    adjust_sets=adjust_current_set_count,
                    manage_actions=open_active_action_manager,
                ),
            )
            training_clock_refs["elapsed"] = result.elapsed_control
            training_clock_refs["rest"] = result.rest_control
            return result.control

        def reorder_planned_exercise(dragged_id, target_id):
            if not dragged_id or dragged_id == target_id:
                return
            raw_session["exercises"] = reorder_session_exercise_blocks(
                raw_session.get("exercises", []),
                raw_session.get("exercise_groups", []),
                dragged_id,
                target_id,
            )
            raw_session["exercise_groups"] = normalize_exercise_groups(raw_session["exercises"], raw_session.get("exercise_groups", []))
            persist_session(raw_session)
            refresh()

        def reorder_planned_group_member(dragged_id, target_id):
            raw_session["exercises"] = reorder_group_members(
                raw_session.get("exercises", []),
                raw_session.get("exercise_groups", []),
                dragged_id,
                target_id,
            )
            raw_session["exercise_groups"] = normalize_exercise_groups(
                raw_session["exercises"], raw_session.get("exercise_groups", [])
            )
            persist_session(raw_session)
            refresh()

        def remove_planned_group_member(exercise_id):
            raw_session["exercise_groups"] = remove_exercise_from_group(
                raw_session.get("exercises", []),
                raw_session.get("exercise_groups", []),
                exercise_id,
            )
            persist_session(raw_session)
            refresh()

        return build_planned_training(raw_session, PlannedTrainingActions(
            start=start_session,
            add_exercise=lambda e: open_add_exercise_dialog(),
            delete_exercise=delete_session_exercise,
            reuse_history=reuse_history_session,
            clear=clear_today_training,
            group_exercise=open_exercise_group_dialog,
            delete_group=delete_exercise_group,
            show_help=open_planned_exercise_help,
            edit_exercise=open_edit_planned_exercise,
            reorder_exercise=reorder_planned_exercise,
            reorder_group_member=reorder_planned_group_member,
            remove_group_member=remove_planned_group_member,
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
