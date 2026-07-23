# -*- coding: utf-8 -*-
import json
import datetime
import asyncio
import re
from datetime import date
import flet as ft

from app_defaults import DEFAULT_MACRO_MULTIPLIERS
from app_context import AppContext
from app_state import AppState
from app_utils import to_float
from backup_controller import BackupControllerDependencies, create_backup_controller
from backup_service import BackupServiceDependencies, create_backup_service
from controller_runtime import ControllerRuntime
from data_record_controller import DataRecordControllerDependencies, create_data_record_controller
from daily_record_controller import DailyRecordController, DailyRecordDependencies
from diet_controller import DietControllerDependencies, create_diet_controller
from rest_notification import RestNotifier
from repositories import build_default_repositories
from recovery_controller import RecoveryControllerDependencies, create_recovery_controller
from storage_service import (
    APP_DIR,
    load_user_profile,
    save_user_profile,
)
from navigation_service import MAIN_NAV_VIEWS, reset_transient_navigation_state
from navigation_views import build_bottom_navigation
from nutrition_service import create_nutrition_service
from profile_controller import ProfileControllerDependencies, create_profile_controller
from training_experience_service import rest_remaining_seconds
from training_models import TrainingSession
from training_controller import TrainingControllerDependencies, create_training_controller
from training_service import (
    completed_set_count,
    find_active_daily_session,
    planned_set_count,
)
from today_controller import TodayController, TodayControllerDependencies
from ui_components import (
    BG,
    PRIMARY,
    input_is_focused,
)

APP_NAME = "碳水大王"
APP_VERSION = "1.2.2"
MEALS = ["早餐", "午餐", "晚餐", "练前", "练后", "偷吃"]


# ---- Flet compatibility layer ----
# Avoid hard dependency on APIs that changed across Flet versions.
_THEME_LIGHT = getattr(getattr(ft, "ThemeMode", object()), "LIGHT", "light")
_SCROLL_AUTO = getattr(getattr(ft, "ScrollMode", object()), "AUTO", "auto")
_SCROLL_HIDDEN = getattr(getattr(ft, "ScrollMode", object()), "HIDDEN", "hidden")
_KEYBOARD_NUMBER = getattr(getattr(ft, "KeyboardType", object()), "NUMBER", None)

_EVENT_KWARGS = {
    "on_click", "on_change", "on_submit", "on_focus", "on_blur",
    "on_select", "on_dismiss", "on_tap", "on_long_press"
}

def _make_flet_compat_factory(original_cls, aliases=None):
    """
    Flet 0.85.x changed several control constructor signatures.
    This factory strips unsupported keyword arguments from __init__ and applies
    them as object attributes after construction.
    """
    aliases = aliases or {}

    def factory(*args, **kwargs):
        post_attrs = {}

        # Handle aliases first.
        for old_key, new_key in aliases.items():
            if old_key in kwargs:
                post_attrs[new_key] = kwargs.pop(old_key)

        # Events are safest when assigned after construction.
        for key in list(kwargs.keys()):
            if key in _EVENT_KWARGS:
                post_attrs[key] = kwargs.pop(key)

        # Iteratively strip unexpected kwargs and apply as attributes.
        # This prevents one incompatible keyword from killing the app.
        local_kwargs = dict(kwargs)
        stripped = {}
        for _ in range(30):
            try:
                ctrl = original_cls(*args, **local_kwargs)
                for k, v in {**stripped, **post_attrs}.items():
                    try:
                        setattr(ctrl, k, v)
                    except Exception:
                        pass
                return ctrl
            except TypeError as ex:
                msg = str(ex)
                m = re.search(r"unexpected keyword argument '([^']+)'", msg)
                if not m:
                    raise
                bad_key = m.group(1)
                if bad_key in local_kwargs:
                    stripped[bad_key] = local_kwargs.pop(bad_key)
                    continue
                raise

        ctrl = original_cls(*args)
        for k, v in {**stripped, **post_attrs}.items():
            try:
                setattr(ctrl, k, v)
            except Exception:
                pass
        return ctrl

    return factory

# Patch only the controls used in this app.
# This keeps the rest of Flet untouched.
for _name, _aliases in {
    "Container": {},
    "IconButton": {},
    "TextField": {},
    "Dropdown": {},
    "Checkbox": {},
    "DatePicker": {},
    "AlertDialog": {},
    "SnackBar": {},
    "Row": {},
    "Column": {},
    "Text": {"selectable": "enable_interactive_selection"},
    "Divider": {},
    "ListView": {},
    "SafeArea": {},
}.items():
    if hasattr(ft, _name):
        setattr(ft, _name, _make_flet_compat_factory(getattr(ft, _name), _aliases))





def main(page: ft.Page):
    page.title = APP_NAME
    page.bgcolor = BG
    page.theme_mode = _THEME_LIGHT
    try:
        page.theme = ft.Theme(font_family="Microsoft YaHei")
    except Exception:
        try:
            page.theme.font_family = "Microsoft YaHei"
        except Exception:
            pass
    page.scroll = None
    try:
        page.window_width = 430
        page.window_height = 860
    except Exception:
        pass

    # FilePicker is a Service in Flet 0.85.x. Android export uses src_bytes,
    # so the system file chooser can write into shared storage safely.
    file_picker = ft.FilePicker()
    try:
        page.services.append(file_picker)
    except Exception:
        # Compatibility fallback for builds where services still live in overlay.
        if file_picker not in page.overlay:
            page.overlay.append(file_picker)

    def open_control(control):
        try:
            page.show_dialog(control)
        except Exception:
            if control not in page.overlay:
                page.overlay.append(control)
            control.open = True
            page.update()

    def close_control(control):
        try:
            closed = page.pop_dialog()
            if closed is not None:
                return
        except Exception:
            pass
        control.open = False
        page.update()

    active_snack = {"control": None}

    def snack(message, action_label=None, action=None):
        # Flet 0.85.3 compatibility:
        # Keep only one SnackBar in overlay. Accumulated/overlapping SnackBars can
        # make repeated save/update prompts appear intermittently on Android.
        previous = active_snack.get("control")
        if previous is not None:
            try:
                previous.open = False
            except Exception:
                pass
            try:
                if previous in page.overlay:
                    page.overlay.remove(previous)
            except Exception:
                pass

        content_controls = [ft.Text(message, size=13, color="#FFFFFF", expand=True)]
        if action_label and action:
            content_controls.append(ft.Container(
                content=ft.Text(action_label, size=13, weight="bold", color="#FFFFFF"),
                padding=8,
                on_click=lambda e: action(),
            ))
        sb = ft.SnackBar(content=ft.Row(content_controls, spacing=8))
        try:
            sb.duration = 2200
        except Exception:
            pass
        try:
            sb.bgcolor = PRIMARY
        except Exception:
            pass
        page.overlay.append(sb)
        active_snack["control"] = sb
        sb.open = True
        page.update()

    def responsive_bar_width():
        """Fit progress bars to the current card content width.

        The previous version used fixed buckets such as 760/980px.
        This version calculates from the real page width so the bar follows
        window resizing and aligns closer to the card's inner border.
        """
        raw_width = None
        for attr in ["width", "window_width"]:
            try:
                value = getattr(page, attr, None)
                if value:
                    raw_width = float(value)
                    break
            except Exception:
                pass

        if raw_width is None:
            raw_width = 430

        # Mobile-first width. Avoid desktop-width bars on Android.
        content_width = int(raw_width - 72)

        if content_width < 230:
            content_width = 230
        if content_width > 640:
            content_width = 640

        return content_width

    def page_is_mobile():
        """Flet mobile save paths are document URIs, not Python file paths."""
        try:
            platform = getattr(page, "platform", None)
            is_mobile = getattr(platform, "is_mobile", None)
            if callable(is_mobile):
                return bool(is_mobile())
            platform_name = str(getattr(platform, "value", platform) or "").lower()
            return platform_name in ["android", "ios"]
        except Exception:
            return False


    # State
    repositories = build_default_repositories()
    records = repositories.records.load()

    def responsive_width(max_width=340):
        raw_width = to_float(getattr(page, "width", None), 430)
        return max(260, min(max_width, int(raw_width) - 56))



    state = AppState.default(MEALS)

    rest_notifier = RestNotifier(
        page,
        notification_title="组间休息结束",
        notification_body="下一组可以开始了",
    )
    app_context = AppContext(page, state, repositories, rest_notifier)
    training_clock_refs = app_context.training_clock_refs
    exercise_drag_state = app_context.exercise_drag_state

    nutrition_service = create_nutrition_service(state)
    get_targets = nutrition_service.targets
    daily_total = nutrition_service.daily_total

    daily_record_controller = DailyRecordController(DailyRecordDependencies(
        state=state,
        repositories=repositories,
        records=records,
        nutrition=nutrition_service,
        meals=tuple(MEALS),
        load_profile=load_user_profile,
        sleep_total_minutes=lambda: recovery_controller.sleep_total_minutes(),
        format_minutes=lambda minutes: recovery_controller.format_minutes(minutes),
        restore_training_cursor=lambda: training_controller.restore_cursor(),
        refresh=lambda: refresh(),
        snack=snack,
    ))

    def save_current(show=False):
        daily_record_controller.save(show)

    def load_record_for_date(target_date, autosave=False, show=False):
        daily_record_controller.load(target_date, autosave=autosave, show=show)

    saved_profile = load_user_profile()
    latest_body = daily_record_controller.latest_body()
    if saved_profile.get("body_updated_at") or not latest_body:
        state["weight"] = str(saved_profile.get("weight", state["weight"]))
        state["bodyfat"] = str(saved_profile.get("bodyfat", state["bodyfat"]))
    else:
        if latest_body.get("weight") is not None:
            state["weight"] = f"{latest_body['weight']:g}"
        if latest_body.get("bodyfat") is not None:
            state["bodyfat"] = f"{latest_body['bodyfat']:g}"
    state["height"] = str(saved_profile.get("height", state["height"]))
    state["age"] = str(saved_profile.get("age", state["age"]))
    state["sex"] = str(saved_profile.get("sex", state["sex"]))
    state["activity_habit"] = str(saved_profile.get("activity_habit", state["activity_habit"]))
    state["waist_cm"] = str(saved_profile.get("waist_cm", state.get("waist_cm", "")))
    state["arm_cm"] = str(saved_profile.get("arm_cm", state.get("arm_cm", "")))
    state["chest_cm"] = str(saved_profile.get("chest_cm", state.get("chest_cm", "")))
    state["hip_cm"] = str(saved_profile.get("hip_cm", state.get("hip_cm", "")))
    state["thigh_cm"] = str(saved_profile.get("thigh_cm", state.get("thigh_cm", "")))
    state["calf_cm"] = str(saved_profile.get("calf_cm", state.get("calf_cm", "")))
    state["macro_mode"] = saved_profile.get("macro_mode", "auto")
    state["macro_multipliers"] = json.loads(json.dumps(
        saved_profile.get("custom_macro_multipliers", saved_profile.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))
    ))
    state["auto_macro_multipliers"] = json.loads(json.dumps(
        saved_profile.get("auto_macro_multipliers", DEFAULT_MACRO_MULTIPLIERS)
    ))
    state["profile_inited"] = bool(saved_profile.get("profile_inited", False))


    controller_runtime = ControllerRuntime(
        page=page,
        refresh=lambda: refresh(),
        snack=snack,
        navigate=lambda target: set_view(target),
        open_control=open_control,
        close_control=close_control,
        responsive_width=responsive_width,
        responsive_bar_width=responsive_bar_width,
    )
    diet_controller = create_diet_controller(DietControllerDependencies(
        state=state,
        repositories=repositories,
        records=records,
        runtime=controller_runtime,
        persist_daily=lambda show=False: save_current(show),
        persist_records=daily_record_controller.persist_records,
        get_targets=get_targets,
        daily_total=daily_total,
        meals=tuple(MEALS),
        keyboard_number=_KEYBOARD_NUMBER,
        scroll_hidden=_SCROLL_HIDDEN,
    ))
    foods = diet_controller.foods
    supplements = diet_controller.supplements





    backup_service = create_backup_service(BackupServiceDependencies(
        state=state,
        repositories=repositories,
        records=records,
        foods=foods,
        supplements=supplements,
        app_dir=APP_DIR,
        app_version=APP_VERSION,
        load_profile=load_user_profile,
        save_profile=save_user_profile,
        reload_date=lambda target_date, autosave=False, show=False: load_record_for_date(target_date, autosave=autosave, show=show),
    ))
    backup_controller = create_backup_controller(BackupControllerDependencies(
        service=backup_service,
        repositories=repositories,
        runtime=controller_runtime,
        file_picker=file_picker,
        app_version=APP_VERSION,
        page_is_mobile=page_is_mobile,
        load_profile=load_user_profile,
    ))
    profile_controller = create_profile_controller(ProfileControllerDependencies(
        state=state,
        repositories=repositories,
        records=records,
        runtime=controller_runtime,
        nutrition=nutrition_service,
        backup=backup_controller,
        persist_daily=lambda show=False: save_current(show),
        load_profile=load_user_profile,
        keyboard_number=_KEYBOARD_NUMBER,
        scroll_hidden=_SCROLL_HIDDEN,
    ))
    save_profile_from_state = profile_controller.persist_profile

    recovery_controller = create_recovery_controller(RecoveryControllerDependencies(
        state=state,
        runtime=controller_runtime,
        persist_daily=lambda show=False: save_current(show),
        persist_profile=save_profile_from_state,
        supplements=supplements,
        iso_now=lambda: datetime.datetime.now().isoformat(timespec="seconds"),
        keyboard_number=_KEYBOARD_NUMBER,
        scroll_hidden=_SCROLL_HIDDEN,
    ))
    data_record_controller = create_data_record_controller(DataRecordControllerDependencies(
        state=state,
        repositories=repositories,
        records=records,
        daily_records=daily_record_controller,
        runtime=controller_runtime,
        iso_now=lambda: datetime.datetime.now().isoformat(timespec="seconds"),
        keyboard_number=_KEYBOARD_NUMBER,
        scroll_hidden=_SCROLL_HIDDEN,
    ))

    async def scroll_main_column(**kwargs):
        await main_column.scroll_to(**kwargs)

    def request_main_scroll(**kwargs):
        page.run_task(scroll_main_column, **kwargs)

    training_controller = create_training_controller(TrainingControllerDependencies(
        state=state,
        repositories=repositories,
        records=records,
        runtime=controller_runtime,
        persist_daily=lambda show=False: save_current(show),
        persist_training_session=daily_record_controller.persist_training_session,
        load_date=lambda target_date, autosave=False, show=False: load_record_for_date(target_date, autosave=autosave, show=show),
        rest_notifier=rest_notifier,
        training_clock_refs=training_clock_refs,
        exercise_drag_state=exercise_drag_state,
        keyboard_number=_KEYBOARD_NUMBER,
        scroll_hidden=_SCROLL_HIDDEN,
        current_scroll=lambda: view_scroll_offsets.get("training", 0.0),
        scroll_to=request_main_scroll,
        viewport_height=lambda: float(getattr(page, "height", 860) or 860),
    ))
    session_data = training_controller.session_data
    elapsed_seconds = training_controller.elapsed_seconds
    clock_text = training_controller.clock_text
    complete_rest_if_elapsed = training_controller.complete_rest_if_elapsed

    today_controller = TodayController(TodayControllerDependencies(
        state=state,
        records=records,
        runtime=controller_runtime,
        nutrition=nutrition_service,
        training=training_controller,
        recovery=recovery_controller,
        daily_records=daily_record_controller,
        meals=tuple(MEALS),
        responsive_bar_width=responsive_bar_width,
        training_clock_refs=training_clock_refs,
    ))
    def set_view(name):
        previous_view = str(state.get("current_view") or "today")
        reset_transient_navigation_state(state, previous_view, name)
        if name == "me":
            profile_controller.reload_profile()
        state["current_view"] = name
        refresh()


    def render_nav():
        current_session = session_data()
        return build_bottom_navigation(
            str(state.get("current_view") or "today"),
            set_view,
            hide=bool(
                state.get("current_view") == "training"
                and current_session
                and current_session.get("status") == "active"
            ),
        )

    view_scroll_offsets = {view: 0.0 for view in MAIN_NAV_VIEWS}

    def remember_scroll(e):
        view = str(state.get("current_view") or "today")
        if view in view_scroll_offsets:
            view_scroll_offsets[view] = max(0.0, float(getattr(e, "pixels", 0.0) or 0.0))

    main_column = ft.Column(spacing=0, scroll=_SCROLL_HIDDEN, expand=True, on_scroll=remember_scroll)
    nav_holder = ft.Container(bgcolor="#F7FFFFFF")

    def render_main_view(target: str):
        if target == "today":
            return today_controller.render_page(), 8
        if target == "daily_details":
            return recovery_controller.render_page(), 8
        if target == "training":
            return training_controller.render_page(), 0
        if target in {"diet", "foods", "supplements"}:
            return diet_controller.render_page(), 12
        if target == "data":
            return data_record_controller.render_page(), 12
        if target == "me":
            return profile_controller.render_page(), 0
        raise ValueError(f"Unsupported main view: {target}")

    def populate_view(column, target: str):
        control, bottom_space = render_main_view(target)
        column.controls.append(control)
        if bottom_space:
            column.controls.append(ft.Container(height=bottom_space))

    def refresh():
        main_column.controls.clear()
        view = state["current_view"]
        current_session = session_data()
        active_training = bool(
            view == "training"
            and current_session
            and current_session.get("status") == "active"
        )
        # The focus workout is a viewport-sized surface. Disabling the outer
        # column's scroll physics prevents the whole black screen from moving
        # a few pixels on touch; every regular app page keeps hidden scrolling.
        main_column.scroll = None if active_training else _SCROLL_HIDDEN
        main_column.on_scroll = None if active_training else remember_scroll
        if active_training:
            view_scroll_offsets["training"] = 0.0
        shell_bg = "#101513" if active_training else BG
        page.bgcolor = shell_bg
        body_container.bgcolor = shell_bg
        try:
            populate_view(main_column, view)
        except Exception as exc:
            print(f"[refresh] render failed in view={view}: {exc!r}")
            page.bgcolor = BG
            body_container.bgcolor = BG
            main_column.controls.append(ft.Container(
                content=ft.Column([
                    ft.Text("页面加载失败", size=22, weight="bold", color="#182420"),
                    ft.Text("已保护应用不黑屏。请返回今日后再重试。", size=14, color="#4F5D58"),
                    ft.Container(
                        content=ft.Text("返回今日", size=15, weight="bold", color="#FFFFFF", text_align="center"),
                        bgcolor=PRIMARY,
                        border_radius=8,
                        height=48,
                        alignment=ft.Alignment.CENTER,
                        on_click=lambda e: set_view("today"),
                    ),
                ], spacing=12),
                bgcolor="#FFFFFF",
                border_radius=12,
                padding=16,
                margin=12,
            ))
        nav_holder.content = render_nav()
        page.update()
        if not active_training and view in view_scroll_offsets and view_scroll_offsets[view] > 0:
            try:
                request_main_scroll(offset=view_scroll_offsets[view], duration=120)
            except Exception:
                pass

    # Root layout:
    # - body_container expands and owns the vertical scroll
    # - nav_holder is outside body_container, so it stays fixed at the bottom
    body_container = ft.Container(
        content=main_column,
        padding=0,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        expand=True,
    )
    root_layout = ft.Column(
        controls=[body_container, nav_holder],
        spacing=0,
        expand=True,
    )

    try:
        page.add(ft.SafeArea(content=root_layout, expand=True))
    except Exception:
        page.add(root_layout)

    async def training_clock_loop():
        while True:
            await asyncio.sleep(1)
            session = session_data()
            active_date = state.get("date")
            if not session or session.get("status") != "active":
                active_date, session = find_active_daily_session(records)
            if not session or session.get("status") != "active":
                continue
            dashboard_control = training_clock_refs.get("dashboard")
            if dashboard_control is not None:
                model = TrainingSession.from_dict(session)
                completed = completed_set_count(model)
                planned = planned_set_count(model)
                dashboard_control.value = (
                    f"训练开始于 {active_date} · {clock_text(elapsed_seconds(session))}"
                    if active_date != state.get("date")
                    else f"已完成 {completed}/{planned} 组 · {clock_text(elapsed_seconds(session))}"
                )
                try:
                    dashboard_control.update()
                except Exception:
                    pass
            elapsed_control = training_clock_refs.get("elapsed")
            if elapsed_control is not None:
                elapsed_control.value = clock_text(elapsed_seconds(session))
                try:
                    elapsed_control.update()
                except Exception:
                    pass
            rest_cycle = session.get("rest_cycle") if isinstance(session.get("rest_cycle"), dict) else None
            rest_seconds = rest_remaining_seconds(rest_cycle, datetime.datetime.now()) if rest_cycle else 0
            rest_control = training_clock_refs.get("rest")
            if rest_control is not None:
                rest_control.value = str(rest_seconds)
                try:
                    rest_control.update()
                except Exception:
                    pass
            if isinstance(rest_cycle, dict) and rest_cycle.get("status") == "running" and rest_seconds <= 0:
                complete_rest_if_elapsed(session, record_date=active_date)
                try:
                    refresh()
                except Exception:
                    pass

    try:
        page.run_task(training_clock_loop)
    except Exception:
        pass

    def on_page_resize(e=None):
        # Rebuild progress bars after dragging the window border.
        try:
            refresh()
        except Exception:
            pass

    try:
        page.on_resize = on_page_resize
    except Exception:
        pass


    # Auto load today if saved; otherwise blank default.
    load_record_for_date(date.today().isoformat(), autosave=False, show=False)
    refresh()
    profile_controller.open_onboarding()

if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(main)
