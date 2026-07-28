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
from goal_challenge_definitions import BODY_METRICS, LANE_LABELS, TYPE_LABELS, TYPE_LANES
from goal_challenge_service import (
    add_challenge,
    consume_next_celebration,
    create_challenge,
    delete_active_challenges,
    normalize_challenge_state,
    recalculate_state,
    recommendation_progress,
    visible_recommendations,
)
from nutrition_service import NutritionService
from profile_views import build_achievement_wall, build_completed_challenges, build_goal_challenge_panel
from profile_backup_views import build_backup_panel
from profile_details_views import build_profile_details, build_profile_metrics
from profile_macro_views import build_carb_cycle_goal_section, build_macro_panel
from repositories import AppRepositories
from ui_components import (
    GREEN, PRIMARY, PRIMARY_SOFT, TEXT, YELLOW, labeled_plain_field, make_button,
    mobile_dropdown, small_text, three_field_grid, two_field_grid,
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
    challenge_ui = {"delete_mode": False, "selected": set()}
    fallback_challenges: dict[str, Any] = {}

    def iso_now():
        return datetime.datetime.now().isoformat(timespec="seconds")

    def dialog_base(title, content, actions=None, on_close=None):
        return build_dialog(title, content, actions=actions, on_close=on_close)

    def save_profile_from_state():
        auto_multipliers = get_multipliers("auto")
        state["auto_macro_multipliers"] = json.loads(json.dumps(auto_multipliers))
        profile_data = {
            "weight": state.get("weight", ""),
            "bodyfat": state.get("bodyfat", ""),
            "height": state.get("height", ""),
            "age": state.get("age", ""),
            "sex": state.get("sex", ""),
            "activity_habit": state.get("activity_habit", ""),
            "macro_goal": state.get("macro_goal", "减脂"),
            "waist_cm": state.get("waist_cm", ""),
            "arm_cm": state.get("arm_cm", ""),
            "chest_cm": state.get("chest_cm", ""),
            "hip_cm": state.get("hip_cm", ""),
            "thigh_cm": state.get("thigh_cm", ""),
            "calf_cm": state.get("calf_cm", ""),
            "macro_mode": state.get("macro_mode", "auto"),
            "macro_goal": state.get("macro_goal", "减脂"),
            "macro_multipliers": json.loads(json.dumps(state.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))),
            "custom_macro_multipliers": json.loads(json.dumps(state.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))),
            "auto_macro_multipliers": json.loads(json.dumps(auto_multipliers)),
            "body_updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "profile_inited": bool(state.get("profile_inited", False)),
        }
        repositories.profile.save(profile_data)

    def load_challenges():
        repository = repositories.goal_challenges
        raw = repository.load() if repository is not None else fallback_challenges
        return normalize_challenge_state(raw)

    def save_challenges(value):
        nonlocal fallback_challenges
        normalized = normalize_challenge_state(value)
        repository = repositories.goal_challenges
        if repository is not None:
            repository.save(normalized)
        else:
            fallback_challenges = normalized

    def sync_challenges():
        stored = load_challenges()
        updated, completed = recalculate_state(stored, records, now=iso_now())
        if updated != stored:
            save_challenges(updated)
        return updated, completed

    # Compatibility for injected legacy repositories used by older integrations.
    # The default app always has a separate goal_challenges repository, so this
    # branch is never part of the production user path.
    def render_legacy_compatibility_wall():
        raw_results = evaluate_achievements(records)
        stored = repositories.achievements.load()
        updated = register_achievement_unlocks(raw_results, stored, iso_now())
        if updated != stored:
            repositories.achievements.save(updated)
        results = sort_achievement_views(raw_results, achievement_unlock_times(updated))
        if pending_achievement_results(raw_results, updated):
            dialog_state = {"dialog": None}

            def show_legacy(event=None):
                pending = pending_achievement_results(raw_results, repositories.achievements.load())
                if not pending or dialog_state["dialog"] is not None:
                    return
                item = pending[0]
                dialog = None

                def confirm(e=None):
                    repositories.achievements.save(acknowledge_achievement_celebration(repositories.achievements.load(), item.get("id")))
                    close_control(dialog)
                    dialog_state["dialog"] = None
                    show_legacy()

                def dismiss(e=None):
                    dialog_state["dialog"] = None
                    show_legacy()

                dialog = build_achievement_celebration(item, on_confirm=confirm, on_dismiss=dismiss)
                dialog_state["dialog"] = dialog
                open_control(dialog)

            try:
                page.run_task(lambda: show_legacy())
            except Exception:
                show_legacy()
        return build_achievement_wall(results, expanded=False, on_toggle=lambda e=None: None)

    def show_next_challenge_celebration():
        if celebration_state["dialog"] is not None or state.get("current_view") != "me":
            return
        stored = load_challenges()
        pending = stored.get("pending_celebrations", [])
        if not pending:
            return
        challenge = next(
            (item for item in stored.get("completed", []) if item.get("id") == pending[0]),
            None,
        )
        if challenge is None:
            return
        dialog = None

        def confirm(event=None):
            updated, _ = consume_next_celebration(load_challenges())
            save_challenges(updated)
            close_control(dialog)
            celebration_state["dialog"] = None
            schedule_challenge_celebration()

        def dismissed(event=None):
            if celebration_state["dialog"] is dialog:
                celebration_state["dialog"] = None
                schedule_challenge_celebration()

        def dismiss(event=None):
            close_control(dialog)
            dismissed()

        dialog = build_achievement_celebration(
            {
                "title": str(challenge.get("title") or "目标挑战"),
                "description": (
                    f"最终进度：{float(challenge.get('completed_value', challenge.get('current', 0)) or 0):g} / "
                    f"{float(challenge.get('target', 0) or 0):g} {challenge.get('unit', '')}"
                ),
            },
            on_confirm=confirm,
            on_dismiss=dismissed,
            headline="挑战达成",
            confirm_label="收下挑战成果",
            message="这是一项由你主动设定并完成的挑战。继续保持，下一项目标也不远了。",
            on_close=dismiss,
        )
        celebration_state["dialog"] = dialog
        open_control(dialog)

    def schedule_challenge_celebration():
        if celebration_state["scheduled"] or celebration_state["dialog"] is not None:
            return
        celebration_state["scheduled"] = True

        async def show_after_render():
            await asyncio.sleep(0)
            celebration_state["scheduled"] = False
            show_next_challenge_celebration()

        try:
            page.run_task(show_after_render)
        except (AttributeError, RuntimeError):
            celebration_state["scheduled"] = False
            show_next_challenge_celebration()

    def open_completed_challenges(event=None):
        dialog = None
        dialog = build_completed_challenges(
            load_challenges().get("completed", []),
            on_close=lambda e=None: close_control(dialog),
            content_width=responsive_width(),
        )
        open_control(dialog)

    def remove_selected_challenges(event=None):
        selected = set(challenge_ui["selected"])
        if not selected:
            snack("请先选择要删除的挑战")
            return
        dialog = None

        def confirm(e=None):
            updated, count = delete_active_challenges(load_challenges(), selected)
            save_challenges(updated)
            challenge_ui["selected"].clear()
            challenge_ui["delete_mode"] = False
            close_control(dialog)
            refresh()
            snack(f"已删除 {count} 项进行中挑战")

        dialog = dialog_base(
            "确认删除挑战？",
            small_text(f"将永久删除已选择的 {len(selected)} 项进行中挑战，已完成记录不会受影响。"),
            [
                make_button("取消", on_click=lambda e: close_control(dialog), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                make_button("确认删除", on_click=confirm, bgcolor="#FCECEC", color="#B83A3A", expand=True),
            ],
        )
        open_control(dialog)

    def open_new_challenge(initial_lane=None, preset=None, event=None):
        dialog_width = responsive_width()
        selected_mode = {"value": "recommended"}
        sheet = None
        tabs = ft.Row(spacing=8)
        recommended_holder = ft.Container(expand=True)
        custom_holder = ft.Container(expand=True, visible=False)
        footer_cancel = make_button("取消", bgcolor=PRIMARY_SOFT, color=GREEN, expand=True)
        footer_custom = make_button("创建自定义挑战", expand=True)
        footer_custom.visible = False
        preset = dict(preset or {})
        if initial_lane and not preset:
            lane_defaults = {"food": "nutrition_streak", "training": "training_sessions", "recovery": "water_streak"}
            preset["challenge_type"] = lane_defaults.get(initial_lane, "training_sessions")
            preset["lane"] = initial_lane
        lane_options = [ft.dropdown.Option(key, label) for key, label in LANE_LABELS.items()]
        default_lane = str(preset.get("lane") or initial_lane or "training")
        recommended_lane_box = mobile_dropdown("创建到赛道", default_lane, lane_options, width=dialog_width)

        def close_sheet(e=None):
            close_control(sheet)

        footer_cancel.on_click = close_sheet

        def save_created(challenge):
            try:
                updated, saved = add_challenge(load_challenges(), challenge, records, now=iso_now())
                save_challenges(updated)
            except ValueError as exc:
                snack(str(exc))
                return False
            close_sheet()
            refresh()
            if saved.get("status") == "completed":
                schedule_challenge_celebration()
            return True

        def create_from_template(template):
            try:
                challenge = create_challenge(
                    template,
                    now=iso_now(),
                    lane=str(recommended_lane_box.value or template.get("lane") or "training"),
                )
            except ValueError as exc:
                snack(str(exc))
                return
            save_created(challenge)

        recommendation_controls = [
            small_text("推荐卡会显示真实历史背景进度；选择赛道后点击创建才会追踪和庆祝。"),
            recommended_lane_box,
        ]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for template in visible_recommendations(load_challenges()):
            grouped.setdefault(str(template.get("group") or "推荐挑战"), []).append(template)
        level_names = ("优秀", "精良", "史诗", "传说")
        level_colors = ("#2E9B62", "#2878C8", "#7651B8", "#E0822B")
        for group, templates in grouped.items():
            recommendation_controls.append(ft.Text(group, size=15, weight="bold", color=TEXT))
            for template in templates:
                progress = recommendation_progress(template, records)
                level = max(0, min(3, int(template.get("level", 0))))
                recommendation_controls.append(ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text(str(template.get("title") or "目标挑战"), size=14, weight="bold", color=TEXT, expand=True, max_lines=2, overflow="ellipsis"),
                            ft.Text(level_names[level], size=11, weight="bold", color=level_colors[level]),
                        ], spacing=6),
                        small_text(
                            f"历史进度 {progress['current']:g} / {progress['target']:g} "
                            f"{progress['unit']} · {progress['percent']:g}%"
                        ),
                        ft.ProgressBar(value=progress["percent"] / 100, color=level_colors[level], bgcolor="#E4EAE8", height=6),
                        small_text("点击创建并同步历史进度"),
                    ], spacing=6),
                    padding=10,
                    bgcolor="#F9FBFA",
                    border=ft.Border.all(1, level_colors[level]),
                    border_radius=8,
                    on_click=lambda e, template=template: create_from_template(template),
                ))
        if len(recommendation_controls) == 1:
            recommendation_controls.append(small_text("当前没有可推荐项目；完成上一等级后会显示下一等级。"))
        recommended_holder.content = ft.Column(recommendation_controls, spacing=9, scroll=_SCROLL_HIDDEN, expand=True)

        title_box, title_field = labeled_plain_field("挑战名称", preset.get("title", ""), expand=True)
        declaration_box, declaration_field = labeled_plain_field("挑战宣言（可选）", preset.get("declaration", ""), expand=True)
        type_box = mobile_dropdown(
            "挑战类型",
            preset.get("challenge_type", "training_sessions"),
            [ft.dropdown.Option(key, label) for key, label in TYPE_LABELS.items()],
            width=dialog_width,
        )
        lane_box = mobile_dropdown("所属赛道", default_lane, lane_options, expand=True)
        target_box, target_field = labeled_plain_field("目标值", str(preset.get("target", "")), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        unit_box = mobile_dropdown("单位", preset.get("unit", "次"), [ft.dropdown.Option(value) for value in ("次", "天", "kg", "lbs", "%", "cm")], expand=True)
        today = datetime.date.today()
        start_box, start_field = labeled_plain_field("开始日期（YYYY-MM-DD）", preset.get("start_date", today.isoformat()), expand=True)
        end_box, end_field = labeled_plain_field("结束日期（YYYY-MM-DD）", preset.get("end_date", (today + datetime.timedelta(days=30)).isoformat()), expand=True)
        action_box, action_field = labeled_plain_field("动作名称/ID", preset.get("action_id", ""), expand=True)
        daily_box, daily_field = labeled_plain_field("每日饮水阈值 ml", str(preset.get("daily_target", 2000)), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        indicator_box = mobile_dropdown("饮食达标指标", preset.get("indicator", "protein"), [ft.dropdown.Option("protein", "蛋白质目标"), ft.dropdown.Option("carb_cycle", "碳循环目标")], expand=True)
        metric_box = mobile_dropdown("身体指标", preset.get("metric", "weight"), [ft.dropdown.Option(key, label) for key, (label, _) in BODY_METRICS.items()], expand=True)
        direction_box = mobile_dropdown("目标方向", preset.get("direction", "at_most"), [ft.dropdown.Option("at_most", "不高于"), ft.dropdown.Option("at_least", "不低于")], expand=True)

        def update_custom_fields(e=None):
            challenge_type = str(type_box.value or "training_sessions")
            action_box.visible = challenge_type == "max_weight"
            daily_box.visible = challenge_type == "water_streak"
            indicator_box.visible = challenge_type == "nutrition_streak"
            metric_box.visible = challenge_type == "body_target"
            direction_box.visible = challenge_type == "body_target"
            units = {
                "training_volume": "kg", "max_weight": "kg", "training_sessions": "次",
                "training_days": "天", "training_streak": "天", "exercise_reps": "次", "water_streak": "天",
                "nutrition_streak": "天",
            }
            if challenge_type == "body_target":
                unit_box.value = BODY_METRICS.get(str(metric_box.value or "weight"), ("", "kg"))[1]
            elif e is not None:
                unit_box.value = units.get(challenge_type, "次")
            try:
                page.update()
            except Exception:
                pass

        type_box.on_change = update_custom_fields
        metric_box.on_change = update_custom_fields
        custom_holder.content = ft.Column([
            small_text("自定义挑战为金色，不参与推荐等级链。"),
            title_box,
            declaration_box,
            type_box,
            lane_box,
            ft.Row([target_box, unit_box], spacing=8),
            ft.Row([start_box, end_box], spacing=8),
            action_box,
            daily_box,
            indicator_box,
            metric_box,
            direction_box,
        ], spacing=9, scroll=_SCROLL_HIDDEN, expand=True)
        update_custom_fields()

        def select_mode(value):
            selected_mode["value"] = value
            recommended_holder.visible = value == "recommended"
            custom_holder.visible = value == "custom"
            footer_custom.visible = value == "custom"
            footer_cancel.expand = value != "custom"
            tabs.controls.clear()
            tabs.controls.extend([
                make_button("推荐挑战", on_click=lambda e: select_mode("recommended"), bgcolor=PRIMARY if value == "recommended" else PRIMARY_SOFT, color="#FFFFFF" if value == "recommended" else GREEN, expand=True),
                make_button("自定义挑战", on_click=lambda e: select_mode("custom"), bgcolor=PRIMARY if value == "custom" else PRIMARY_SOFT, color="#FFFFFF" if value == "custom" else GREEN, expand=True),
            ])
            try:
                page.update()
            except Exception:
                pass

        def save_custom(e=None):
            if selected_mode["value"] != "custom":
                select_mode("custom")
                snack("请填写自定义挑战信息")
                return
            challenge_type = str(type_box.value or "")
            payload = {
                "title": str(title_field.value or "").strip(),
                "declaration": str(declaration_field.value or "").strip(),
                "challenge_type": challenge_type,
                "lane": str(lane_box.value or "training"),
                "target": to_float(target_field.value, 0),
                "unit": str(unit_box.value or ""),
                "start_date": str(start_field.value or "").strip(),
                "end_date": str(end_field.value or "").strip(),
                "action_id": str(action_field.value or "").strip(),
                "daily_target": to_float(daily_field.value, 0),
                "indicator": str(indicator_box.value or "protein"),
                "metric": str(metric_box.value or "weight"),
                "direction": str(direction_box.value or "at_most"),
            }
            try:
                challenge = create_challenge(payload, now=iso_now())
            except ValueError as exc:
                snack(str(exc))
                return
            save_created(challenge)

        footer_custom.on_click = save_custom
        select_mode("recommended")
        sheet = build_full_form_sheet(
            FormViewContext(close_control=close_control, scroll_mode=_SCROLL_HIDDEN),
            "新建挑战",
            [tabs, recommended_holder, custom_holder],
            save_custom,
            "创建自定义挑战",
            footer_controls=[footer_cancel, footer_custom],
        )
        open_control(sheet)

    def render_challenge_panel():
        if repositories.goal_challenges is None:
            return render_legacy_compatibility_wall()
        stored, _ = sync_challenges()
        if stored.get("pending_celebrations"):
            schedule_challenge_celebration()

        def toggle_delete(e=None):
            challenge_ui["delete_mode"] = not challenge_ui["delete_mode"]
            challenge_ui["selected"].clear()
            refresh()

        def select_delete(identity):
            if identity in challenge_ui["selected"]:
                challenge_ui["selected"].remove(identity)
            else:
                challenge_ui["selected"].add(identity)
            refresh()

        return build_goal_challenge_panel(
            stored.get("active", []),
            on_new=lambda e=None: open_new_challenge(),
            on_completed=open_completed_challenges,
            on_delete_toggle=toggle_delete,
            delete_mode=challenge_ui["delete_mode"],
            selected_ids=challenge_ui["selected"],
            on_select=select_delete,
            on_delete_confirm=remove_selected_challenges,
        )

    def render_me():
        targets = get_targets()

        weight_box, weight_field = labeled_plain_field("体重 kg", state.get("weight", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        bodyfat_box, bodyfat_field = labeled_plain_field("体脂 %", state.get("bodyfat", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        height_box, height_field = labeled_plain_field("身高 cm", state.get("height", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        age_box, age_field = labeled_plain_field("年龄", state.get("age", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        def assign_visible_fields(*, sex_value=None, habit_value=None):
            state["weight"] = str(weight_field.value or "").strip()
            state["bodyfat"] = str(bodyfat_field.value or "").strip()
            state["height"] = str(height_field.value or "").strip()
            state["age"] = str(age_field.value or "").strip()
            state["sex"] = sex_value if sex_value is not None else state.get("sex", "")
            state["activity_habit"] = habit_value if habit_value is not None else state.get("activity_habit", "")
            state["profile_inited"] = bool(get_targets()["is_ready"])

        def persist_visible_profile(*, sex_value=None, habit_value=None):
            assign_visible_fields(sex_value=sex_value, habit_value=habit_value)
            save_profile_from_state()
            save_current()

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

        def set_macro_goal(goal):
            if state.get("macro_mode", "auto") != "auto":
                return
            if goal not in {"减脂", "保持", "增肌"}:
                return
            state["macro_goal"] = goal
            save_profile_from_state()
            save_current()
            refresh()
            snack(f"碳循环目标已切换为{goal}")

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
            values = displayed_multipliers.get(day_type)
            if not isinstance(values, dict):
                break
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
            current_goal=state.get("macro_goal", "减脂"),
            on_goal_change=set_macro_goal,
            profile_ready=bool(targets["is_ready"]),
            profile_message=str(targets.get("profile_message", "")),
        )
        circumference = state.get("circumference")
        circumference = dict(circumference) if isinstance(circumference, dict) else {}
        expanded = bool(state.get("profile_circumference_expanded", False))

        def toggle_circumference(e=None):
            state["profile_circumference_expanded"] = not expanded
            refresh()

        return build_profile_details(
            [weight_box, bodyfat_box, height_box, age_box],
            sex=state.get("sex", ""),
            activity_habit=state.get("activity_habit", ""),
            circumference_values=circumference,
            circumference_expanded=expanded,
            on_toggle_circumference=toggle_circumference,
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
        weight_box, weight_field = labeled_plain_field("体重 kg", state.get("weight", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        bodyfat_box, bodyfat_field = labeled_plain_field("体脂 %", state.get("bodyfat", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        height_box, height_field = labeled_plain_field("身高 cm", state.get("height", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        age_box, age_field = labeled_plain_field("年龄", state.get("age", ""), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        macro_goal = state.get("macro_goal", "减脂")
        if macro_goal not in {"减脂", "保持", "增肌"}:
            macro_goal = "减脂"
        selected = {
            "sex": state.get("sex", ""),
            "activity_habit": state.get("activity_habit", ""),
            "macro_goal": macro_goal,
        }

        sex_row = ft.Row(spacing=8)
        act_row1 = ft.Row(spacing=8)
        act_row2 = ft.Row(spacing=8)
        goal_holder = ft.Container()

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
            goal_holder.content = build_carb_cycle_goal_section(
                selected["macro_goal"], lambda value: choose("macro_goal", value)
            )

        def choose(group, value):
            selected[group] = value
            rebuild_buttons()
            page.update()

        rebuild_buttons()
        dlg = None

        def confirm(e=None):
            state["weight"] = str(weight_field.value or "").strip()
            state["bodyfat"] = str(bodyfat_field.value or "").strip()
            state["height"] = str(height_field.value or "").strip()
            state["age"] = str(age_field.value or "").strip()
            state["sex"] = selected["sex"]
            state["activity_habit"] = selected["activity_habit"]
            state["macro_goal"] = selected["macro_goal"]
            targets = get_targets()
            if not targets["is_ready"]:
                snack(str(targets["profile_message"]))
                return
            state["profile_inited"] = True
            save_profile_from_state()
            save_current()
            close_control(dlg)
            refresh()
            snack("个人信息已保存")

        content = ft.Column([
            small_text("基础资料用于计算 BMR（基础代谢率）、TDEE（每日总能量消耗）和碳循环目标。围度可在数据页单独记录。"),
            two_field_grid(weight_box, bodyfat_box, viewport_width=dialog_width),
            two_field_grid(height_box, age_box, viewport_width=dialog_width),
            small_text("性别"),
            sex_row,
            small_text("运动习惯"),
            act_row1,
            act_row2,
            goal_holder,
        ], width=dialog_width, height=520, spacing=10, scroll=_SCROLL_HIDDEN)

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
        saved_macro_goal = current_profile.get("macro_goal", state.profile.macro_goal)
        state.profile.macro_goal = saved_macro_goal if saved_macro_goal in {"减脂", "保持", "增肌"} else "减脂"
        state.profile.macro_multipliers = json.loads(json.dumps(
            current_profile.get("custom_macro_multipliers", current_profile.get("macro_multipliers", DEFAULT_MACRO_MULTIPLIERS))
        ))
        state.profile.auto_macro_multipliers = json.loads(json.dumps(
            current_profile.get("auto_macro_multipliers", get_multipliers("auto"))
        ))

    def render_page():
        return ft.Column([render_challenge_panel(), render_me(), ft.Container(height=12)], spacing=0)

    return ProfileController(
        render_page=render_page,
        open_onboarding=open_first_profile_dialog,
        persist_profile=save_profile_from_state,
        reload_profile=reload_profile,
    )


__all__ = ["ProfileController", "ProfileControllerDependencies", "create_profile_controller"]
