"""Profile feature controller for onboarding, profile, macros, achievements, and backup entry points."""

from __future__ import annotations

import asyncio
import datetime
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from achievement_service import (
    acknowledge_achievement_celebration,
    achievement_unlock_times,
    evaluate_achievements,
    pending_achievement_results,
    register_achievement_unlocks,
)
from achievement_views import build_achievement_celebration, sort_achievement_views
from app_defaults import CIRCUMFERENCE_FIELDS, DEFAULT_MACRO_MULTIPLIERS
from app_state import AppState
from app_utils import to_float
from backup_controller import BackupController
from controller_runtime import ControllerRuntime
from form_views import FormViewContext, build_dialog, build_full_form_sheet
from nutrition_service import NutritionService
from profile_views import build_achievement_wall
from profile_backup_views import build_backup_panel
from profile_details_views import build_profile_details, build_profile_metrics
from profile_macro_views import build_macro_panel
from repositories import AppRepositories
from ui_components import (
    GREEN, PRIMARY, PRIMARY_SOFT, TEXT, labeled_plain_field, make_button,
    small_text, three_field_grid, two_field_grid,
)


@dataclass(frozen=True)
class ProfileControllerDependencies:
    state: AppState
    repositories: AppRepositories
    records: dict[str, Any]
    runtime: ControllerRuntime
    nutrition: NutritionService
    backup: BackupController
    persist_daily: Callable[..., None]
    load_profile: Callable[[], dict[str, Any]]
    keyboard_number: Any
    scroll_hidden: Any


@dataclass
class ProfileController:
    render_page: Callable[[], ft.Control]
    open_onboarding: Callable[[], None]
    persist_profile: Callable[[], None]
    reload_profile: Callable[[], None]


def create_profile_controller(deps: ProfileControllerDependencies) -> ProfileController:
    state = deps.state
    repositories = deps.repositories
    records = deps.records
    runtime = deps.runtime
    page = runtime.page
    refresh = runtime.refresh
    snack = runtime.snack
    open_control = runtime.open_control
    close_control = runtime.close_control
    responsive_width = runtime.responsive_width
    get_targets = deps.nutrition.targets
    get_multipliers = deps.nutrition.multipliers
    save_current = deps.persist_daily
    load_profile = deps.load_profile
    export_handler = deps.backup.export_handler
    import_backup_handler = deps.backup.import_backup
    clear_personal_data = deps.backup.clear_personal_data
    _KEYBOARD_NUMBER = deps.keyboard_number
    _SCROLL_HIDDEN = deps.scroll_hidden
    celebration_state = {"scheduled": False, "dialog": None}

    def iso_now():
        return datetime.datetime.now().isoformat(timespec="seconds")

    def dialog_base(title, content, actions=None, on_close=None):
        return build_dialog(title, content, actions=actions, on_close=on_close)

    def save_profile_from_state():
        auto_multipliers = get_multipliers("auto")
        state["auto_macro_multipliers"] = json.loads(json.dumps(auto_multipliers))
        profile_data = {
            "weight": state.get("weight", "62.5"),
            "bodyfat": state.get("bodyfat", "13"),
            "height": state.get("height", "170"),
            "age": state.get("age", "30"),
            "sex": state.get("sex", "男"),
            "activity_habit": state.get("activity_habit", "规律训练"),
            "waist_cm": state.get("waist_cm", ""),
            "arm_cm": state.get("arm_cm", ""),
            "chest_cm": state.get("chest_cm", ""),
            "hip_cm": state.get("hip_cm", ""),
            "thigh_cm": state.get("thigh_cm", ""),
            "calf_cm": state.get("calf_cm", ""),
            "macro_mode": state.get("macro_mode", "auto"),
            "macro_multipliers": json.loads(json.dumps(state.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))),
            "custom_macro_multipliers": json.loads(json.dumps(state.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))),
            "auto_macro_multipliers": json.loads(json.dumps(auto_multipliers)),
            "body_updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "profile_inited": bool(state.get("profile_inited", False)),
        }
        repositories.profile.save(profile_data)

    def show_next_achievement_celebration():
        if celebration_state["dialog"] is not None or state.get("current_view") != "me":
            return
        raw_results = evaluate_achievements(records)
        stored = repositories.achievements.load()
        pending = pending_achievement_results(raw_results, stored)
        if not pending:
            return
        achievement = pending[0]
        dialog = None

        def confirm(event=None):
            updated = acknowledge_achievement_celebration(
                repositories.achievements.load(), achievement.get("id")
            )
            repositories.achievements.save(updated)
            close_control(dialog)
            celebration_state["dialog"] = None
            schedule_achievement_celebration()

        def dismissed(event=None):
            if celebration_state["dialog"] is dialog:
                celebration_state["dialog"] = None
                schedule_achievement_celebration()

        dialog = build_achievement_celebration(
            achievement,
            on_confirm=confirm,
            on_dismiss=dismissed,
        )
        celebration_state["dialog"] = dialog
        open_control(dialog)

    def schedule_achievement_celebration():
        if celebration_state["scheduled"] or celebration_state["dialog"] is not None:
            return
        celebration_state["scheduled"] = True

        async def show_after_render():
            await asyncio.sleep(0)
            celebration_state["scheduled"] = False
            show_next_achievement_celebration()

        try:
            page.run_task(show_after_render)
        except (AttributeError, RuntimeError):
            celebration_state["scheduled"] = False
            show_next_achievement_celebration()

    def render_badge_wall():
        raw_results = evaluate_achievements(records)
        stored = repositories.achievements.load()
        updated = register_achievement_unlocks(raw_results, stored, iso_now())
        if updated != stored:
            repositories.achievements.save(updated)
        results = sort_achievement_views(raw_results, achievement_unlock_times(updated))
        expanded = bool(state.get("achievements_expanded", False))

        def toggle_achievements(e=None):
            state["achievements_expanded"] = not expanded
            refresh()

        wall = build_achievement_wall(results, expanded=expanded, on_toggle=toggle_achievements)
        if pending_achievement_results(raw_results, updated):
            schedule_achievement_celebration()
        return wall

    def render_me():
        targets = get_targets()

        weight_box, weight_field = labeled_plain_field("体重 kg", state.get("weight", "62.5"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        bodyfat_box, bodyfat_field = labeled_plain_field("体脂 %", state.get("bodyfat", "13"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        height_box, height_field = labeled_plain_field("身高 cm", state.get("height", "170"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        age_box, age_field = labeled_plain_field("年龄", state.get("age", "30"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        circumference_boxes = []
        circumference_fields = {}
        for key, label in CIRCUMFERENCE_FIELDS:
            box, field = labeled_plain_field(
                f"{label} cm", state.get(key, ""), keyboard_type=_KEYBOARD_NUMBER, expand=True,
            )
            circumference_boxes.append(box)
            circumference_fields[key] = field

        def assign_visible_fields(*, sex_value=None, habit_value=None):
            state["weight"] = weight_field.value or state.get("weight", "62.5")
            state["bodyfat"] = bodyfat_field.value or state.get("bodyfat", "13")
            state["height"] = height_field.value or state.get("height", "170")
            state["age"] = age_field.value or state.get("age", "30")
            state["sex"] = sex_value if sex_value is not None else state.get("sex", "男")
            state["activity_habit"] = habit_value if habit_value is not None else state.get("activity_habit", "规律训练")
            for key, field in circumference_fields.items():
                state[key] = str(field.value or "").strip()
            state["profile_inited"] = True

        def persist_visible_profile(*, sex_value=None, habit_value=None):
            assign_visible_fields(sex_value=sex_value, habit_value=habit_value)
            save_profile_from_state()
            save_current()

        def save_profile_fields(e=None):
            persist_visible_profile()
            refresh()
            snack("资料已保存，未新增围度记录")

        def record_current_measurement(e=None):
            current = state.get("circumference")
            circumference = dict(current) if isinstance(current, dict) else {}
            circumference["measured_at"] = iso_now()
            entered = 0
            for key, field in circumference_fields.items():
                raw = str(field.value or "").strip()
                if not raw:
                    continue
                value = to_float(raw, -1)
                if not 1 <= value <= 300:
                    snack("围度应在 1-300 cm 之间")
                    return
                circumference[key] = round(value, 2)
                entered += 1
            if entered == 0:
                snack("请至少填写一项围度")
                return
            assign_visible_fields()
            state["circumference"] = circumference
            save_profile_from_state()
            save_current()
            refresh()
            snack("本次围度已记录")

        def set_sex(value):
            persist_visible_profile(sex_value=value)
            refresh()

        def set_activity(value):
            persist_visible_profile(habit_value=value)
            refresh()

        def set_macro_mode(mode):
            state["macro_mode"] = mode
            save_profile_from_state()
            save_current()
            refresh()
            snack("已切换为自动计算" if mode == "auto" else "已切换为自定义倍数")

        def open_macro_settings_dialog(e=None):
            dialog_width = responsive_width()
            fields = {}
            rows = []
            multipliers = state.setdefault("macro_multipliers", json.loads(json.dumps(DEFAULT_MACRO_MULTIPLIERS)))

            def macro_multiplier_field(label, value):
                return labeled_plain_field(
                    label,
                    value=value,
                    keyboard_type=_KEYBOARD_NUMBER,
                    expand=True,
                )

            for day_type in ["高碳日", "中碳日", "低碳日"]:
                current = multipliers.setdefault(day_type, dict(DEFAULT_MACRO_MULTIPLIERS[day_type]))
                carb_box, carb_field = macro_multiplier_field("碳水×体重", f"{to_float(current.get('carb'), DEFAULT_MACRO_MULTIPLIERS[day_type]['carb']):g}")
                protein_box, protein_field = macro_multiplier_field("蛋白×去脂", f"{to_float(current.get('protein'), DEFAULT_MACRO_MULTIPLIERS[day_type]['protein']):g}")
                fat_box, fat_field = macro_multiplier_field("脂肪×体重", f"{to_float(current.get('fat'), DEFAULT_MACRO_MULTIPLIERS[day_type]['fat']):g}")
                fields[day_type] = {"carb": carb_field, "protein": protein_field, "fat": fat_field}
                rows.extend([
                    ft.Text(day_type, size=14, weight="bold", color=PRIMARY),
                    three_field_grid(carb_box, protein_box, fat_box, viewport_width=dialog_width),
                ])

            dlg = None

            def confirm(event=None):
                updated = {}
                for day_type, macro_fields in fields.items():
                    values = {macro: to_float(field.value, 0) for macro, field in macro_fields.items()}
                    if any(value <= 0 or value > 10 for value in values.values()):
                        snack("倍数需大于 0 且不超过 10")
                        return
                    updated[day_type] = values
                state["macro_multipliers"] = updated
                state["macro_mode"] = "custom"
                save_profile_from_state()
                save_current()
                close_control(dlg)
                refresh()
                snack("自定义倍数已保存")

            content = ft.Column([
                small_text("自定义值为目标区间中心；碳水、脂肪按体重计算，蛋白质按去脂体重计算。"),
                *rows,
            ], width=dialog_width, height=430, spacing=9, scroll=_SCROLL_HIDDEN)
            dlg = dialog_base(
                "自定义高中低碳倍数",
                content,
                [ft.Container(content=make_button("保存并启用", on_click=confirm, expand=True), width=dialog_width)],
                on_close=lambda event: close_control(dlg),
            )
            open_control(dlg)

        selected_mode = state.get("macro_mode", "auto")
        displayed_multipliers = get_multipliers(selected_mode)
        multiplier_rows = []
        for day_type in ["高碳日", "中碳日", "低碳日"]:
            values = displayed_multipliers.get(day_type, DEFAULT_MACRO_MULTIPLIERS[day_type])
            multiplier_rows.append(ft.Row([
                small_text(day_type),
                ft.Text(
                    f"碳 {to_float(values.get('carb')):g}｜蛋 {to_float(values.get('protein')):g}｜脂 {to_float(values.get('fat')):g}",
                    size=12,
                    weight="bold",
                    color=TEXT,
                ),
            ], alignment="spaceBetween"))

        macro_box = build_macro_panel(
            multiplier_rows,
            auto_selected=selected_mode == "auto",
            on_edit=open_macro_settings_dialog,
            on_mode_change=set_macro_mode,
        )
        return build_profile_details(
            [weight_box, bodyfat_box, height_box, age_box, *circumference_boxes],
            sex=state.get("sex", "男"),
            activity_habit=state.get("activity_habit", "规律训练"),
            on_save=save_profile_fields,
            on_record_measurement=record_current_measurement,
            on_sex_change=set_sex,
            on_activity_change=set_activity,
            metrics=build_profile_metrics(targets),
            macro_panel=macro_box,
            backup_panel=build_backup_panel(export_handler, import_backup_handler, clear_personal_data),
            viewport_width=responsive_width(),
        )

    def open_first_profile_dialog():
        if state.get("profile_inited"):
            return

        dialog_width = responsive_width()
        weight_box, weight_field = labeled_plain_field("体重 kg", state.get("weight", "62.5"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        bodyfat_box, bodyfat_field = labeled_plain_field("体脂 %", state.get("bodyfat", "13"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        height_box, height_field = labeled_plain_field("身高 cm", state.get("height", "170"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        age_box, age_field = labeled_plain_field("年龄", state.get("age", "30"), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        circumference_boxes = []
        circumference_fields = {}
        for key, label in CIRCUMFERENCE_FIELDS:
            box, field = labeled_plain_field(
                f"{label} cm", state.get(key, ""), keyboard_type=_KEYBOARD_NUMBER, expand=True,
            )
            circumference_boxes.append(box)
            circumference_fields[key] = field

        selected = {
            "sex": state.get("sex", "男"),
            "activity_habit": state.get("activity_habit", "规律训练"),
        }

        sex_row = ft.Row(spacing=8)
        act_row1 = ft.Row(spacing=8)
        act_row2 = ft.Row(spacing=8)

        def rebuild_buttons():
            sex_row.controls.clear()
            act_row1.controls.clear()
            act_row2.controls.clear()

            def btn(label, group):
                current = selected[group] == label
                return make_button(label, on_click=lambda e, l=label, g=group: choose(g, l), bgcolor=PRIMARY if current else PRIMARY_SOFT, color="#FFFFFF" if current else GREEN, expand=True)

            sex_row.controls.extend([btn("男", "sex"), btn("女", "sex")])
            act_row1.controls.extend([btn("久坐少动", "activity_habit"), btn("偶尔运动", "activity_habit")])
            act_row2.controls.extend([btn("规律训练", "activity_habit"), btn("高频训练", "activity_habit")])

        def choose(group, value):
            selected[group] = value
            rebuild_buttons()
            page.update()

        rebuild_buttons()
        dlg = None

        def confirm(e=None):
            state["weight"] = weight_field.value or state.get("weight", "62.5")
            state["bodyfat"] = bodyfat_field.value or state.get("bodyfat", "13")
            state["height"] = height_field.value or "170"
            state["age"] = age_field.value or "30"
            circumference = {"measured_at": iso_now()}
            for key, field in circumference_fields.items():
                raw = str(field.value or "").strip()
                state[key] = raw
                if not raw:
                    continue
                value = to_float(raw, -1)
                if not 1 <= value <= 300:
                    snack("围度应在 1-300 cm 之间")
                    return
                circumference[key] = round(value, 2)
            state["sex"] = selected["sex"]
            state["activity_habit"] = selected["activity_habit"]
            state["profile_inited"] = True
            state["circumference"] = circumference if len(circumference) > 1 else None
            save_profile_from_state()
            save_current()
            close_control(dlg)
            refresh()
            snack("个人信息已保存")

        content = ft.Column([
            small_text("基础资料用于计算 BMR（基础代谢率）、TDEE（每日总能量消耗）和碳循环目标。围度均为选填。"),
            two_field_grid(weight_box, bodyfat_box, viewport_width=dialog_width),
            two_field_grid(height_box, age_box, viewport_width=dialog_width),
            small_text("身体围度（可选）"),
            *[
                two_field_grid(*circumference_boxes[index:index + 2], viewport_width=dialog_width)
                for index in range(0, len(circumference_boxes), 2)
            ],
            small_text("性别"),
            sex_row,
            small_text("运动习惯"),
            act_row1,
            act_row2,
        ], width=dialog_width, height=460, spacing=10, scroll=_SCROLL_HIDDEN)

        dlg = build_full_form_sheet(
            FormViewContext(close_control=close_control, scroll_mode=_SCROLL_HIDDEN),
            "完善个人信息",
            list(content.controls),
            confirm,
            "开始使用",
        )
        open_control(dlg)

    def reload_profile():
        current_profile = load_profile()
        state.profile.weight = str(current_profile.get("weight", state.profile.weight))
        state.profile.bodyfat = str(current_profile.get("bodyfat", state.profile.bodyfat))
        state.profile.height = str(current_profile.get("height", state.profile.height))
        state.profile.age = str(current_profile.get("age", state.profile.age))
        state.profile.sex = str(current_profile.get("sex", state.profile.sex))
        state.profile.activity_habit = str(current_profile.get("activity_habit", state.profile.activity_habit))
        state.profile.waist_cm = str(current_profile.get("waist_cm", state.profile.waist_cm))
        state.profile.arm_cm = str(current_profile.get("arm_cm", state.profile.arm_cm))
        state.profile.chest_cm = str(current_profile.get("chest_cm", state.profile.chest_cm))
        state.profile.hip_cm = str(current_profile.get("hip_cm", state.profile.hip_cm))
        state.profile.thigh_cm = str(current_profile.get("thigh_cm", state.profile.thigh_cm))
        state.profile.calf_cm = str(current_profile.get("calf_cm", state.profile.calf_cm))
        state.profile.macro_mode = str(current_profile.get("macro_mode", state.profile.macro_mode))
        state.profile.macro_multipliers = json.loads(json.dumps(
            current_profile.get("custom_macro_multipliers", current_profile.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))
        ))
        state.profile.auto_macro_multipliers = json.loads(json.dumps(
            current_profile.get("auto_macro_multipliers", get_multipliers("auto"))
        ))

    def render_page():
        return ft.Column([render_badge_wall(), render_me(), ft.Container(height=12)], spacing=0)

    return ProfileController(
        render_page=render_page,
        open_onboarding=open_first_profile_dialog,
        persist_profile=save_profile_from_state,
        reload_profile=reload_profile,
    )


__all__ = ["ProfileController", "ProfileControllerDependencies", "create_profile_controller"]
