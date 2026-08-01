"""Profile feature controller for onboarding, profile, macros, achievements, and backup entry points."""

from __future__ import annotations

import asyncio
import datetime
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import flet as ft
import flet_audio as fta

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
from app_version import BUILD_NUMBER, VERSION_NAME
from app_utils import to_float
from apk_update_download import (
    ApkUpdateError,
    default_apk_destination,
    download_apk,
    open_android_installer,
)
from backup_controller import BackupController
from controller_runtime import ControllerRuntime
from form_views import FormViewContext, build_dialog, build_full_form_sheet
from exercise_library import EXERCISE_CATEGORIES, exercise_catalog, search_exercises
from goal_challenge_definitions import (
    BODY_METRICS, CUSTOM_CHALLENGE_CATALOG, LANE_LABELS, TYPE_LABELS, TYPE_LANES, level_info,
)
from goal_challenge_service import (
    add_challenge,
    challenge_progress,
    consume_pending_celebrations,
    consume_pending_failures,
    create_challenge,
    delete_active_challenges,
    filter_recommendations_by_lane,
    mark_failed_retried,
    normalize_challenge_state,
    recalculate_state,
    recommendation_progress,
    visible_recommendations,
)
from nutrition_service import NutritionService
from profile_views import build_achievement_wall, build_completed_challenges, build_goal_challenge_panel
from profile_backup_views import build_backup_panel
from profile_details_views import build_profile_details, build_profile_metrics
from profile_feature_views import build_background_rest_panel, build_training_recycle_panel
from profile_macro_views import build_carb_cycle_goal_section, build_macro_panel
from profile_theme_views import build_theme_panel
from profile_update_views import build_update_panel
from repositories import AppRepositories
from training_experience_service import exercise_usage_stats, sort_exercises
from training_recycle_service import load_recycled_training_sessions, remove_recycled_training_session
from update_service import fetch_latest_release, update_available
from training_picker_views import (
    build_category_sidebar, build_exercise_card, build_exercise_help, build_sort_row,
)
from ui_components import (
    GREEN, PRIMARY, PRIMARY_SOFT, SURFACE, TEXT, YELLOW, labeled_plain_field, make_button,
    mobile_dropdown, set_input_focused, small_text, three_field_grid, two_field_grid,
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
    rest_notifier: Any = None
    restore_training_session: Callable[[str, dict[str, Any]], None] = lambda *_: None


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
    rest_notifier = deps.rest_notifier
    restore_training_session = deps.restore_training_session
    celebration_state = {"scheduled": False, "dialog": None}
    failure_state = {"scheduled": False, "dialog": None}
    challenge_completion_audio = {"service": None}
    try:
        challenge_completion_audio["service"] = fta.Audio(src="assets/training_complete.mp3", volume=1.0)
        page.services.append(challenge_completion_audio["service"])
    except (AttributeError, RuntimeError, TypeError):
        challenge_completion_audio["service"] = None
    challenge_ui = {"delete_mode": False, "selected": set()}
    fallback_challenges: dict[str, Any] = {}
    update_ui: dict[str, Any] = {
        "status": "idle", "latest": None, "error": "", "download_path": "",
        "downloaded_bytes": 0, "total_bytes": 0,
    }

    def request_rest_permission(kind: str):
        method = getattr(rest_notifier, f"request_{kind}_permission", None)
        if not callable(method):
            snack("当前环境不支持该 Android 权限入口")
            return
        try:
            method()
        except Exception as exc:
            snack(f"打开权限设置失败：{exc}")

    def rest_permission_status() -> dict[str, bool]:
        method = getattr(rest_notifier, "background_permission_status", None)
        if not callable(method):
            return {"android": False, "notification": False, "exact_alarm": False, "overlay": False}
        try:
            return method()
        except Exception:
            return {"android": True, "notification": False, "exact_alarm": False, "overlay": False}

    def open_training_recycle_bin(event=None):
        dialog_width = responsive_width()
        list_holder = ft.Column(spacing=8, scroll=_SCROLL_HIDDEN, expand=True)
        recycle_dlg = None

        def rebuild():
            entries = load_recycled_training_sessions()
            list_holder.controls.clear()
            if not entries:
                list_holder.controls.append(small_text("回收站为空。删除的训练会在这里保留 15 天。"))
                page.update()
                return
            for entry in entries:
                session = entry.get("session", {}) if isinstance(entry.get("session"), dict) else {}
                date_text = str(entry.get("original_date") or session.get("date") or "未知日期")
                names = [
                    str(item.get("name") or "").strip()
                    for item in session.get("exercises", [])
                    if isinstance(item, dict) and str(item.get("name") or "").strip()
                ]
                entry_id = str(entry.get("id") or "")

                def restore(e=None, recycle_id=entry_id):
                    item = next(
                        (
                            candidate
                            for candidate in load_recycled_training_sessions()
                            if str(candidate.get("id") or "") == recycle_id
                        ),
                        None,
                    )
                    if item is None:
                        snack("该记录已过期或不存在")
                        rebuild()
                        return
                    session_data = item.get("session") if isinstance(item.get("session"), dict) else None
                    target_date = str(item.get("original_date") or "").strip()
                    if not session_data or not target_date:
                        snack("恢复失败：记录不完整")
                        return
                    restore_training_session(target_date, session_data)
                    remove_recycled_training_session(recycle_id)
                    rebuild()
                    refresh()
                    snack(f"已恢复到 {target_date} 的当日已练")

                def request_erase(e=None, recycle_id=entry_id):
                    confirm_dlg = None

                    def close_confirm(_=None):
                        close_control(confirm_dlg)

                    def erase(_=None):
                        removed = remove_recycled_training_session(recycle_id)
                        close_confirm()
                        rebuild()
                        snack("训练记录已彻底删除" if removed else "该记录已不存在")

                    confirm_dlg = build_dialog(
                        "彻底删除？",
                        ft.Container(
                            content=small_text("彻底删除后无法恢复。"),
                            width=dialog_width,
                        ),
                        [
                            make_button("取消", on_click=close_confirm, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                            make_button("彻底删除", on_click=erase, bgcolor="#FDECEC", color="#D93025", expand=True),
                        ],
                        on_close=close_confirm,
                    )
                    open_control(confirm_dlg)

                list_holder.controls.append(ft.Container(
                    content=ft.Column([
                        ft.Text(date_text, size=15, weight="bold", color=TEXT),
                        small_text(" + ".join(names) or "训练记录"),
                        small_text(f"删除于 {str(entry.get('deleted_at') or '')[:16]} · 15 天后自动清除"),
                        ft.Row([
                            make_button("恢复", on_click=restore, bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                            make_button("彻底删除", on_click=request_erase, bgcolor="#FDECEC", color="#D93025", expand=True),
                        ], spacing=8),
                    ], spacing=6),
                    bgcolor="#FFFFFF",
                    border_radius=8,
                    padding=10,
                ))
            page.update()

        recycle_dlg = build_full_form_sheet(
            FormViewContext(close_control=close_control, scroll_mode=_SCROLL_HIDDEN),
            "训练回收站",
            [list_holder],
            lambda e: close_control(recycle_dlg),
            save_label="关闭",
            footer_controls=[make_button("关闭", on_click=lambda e: close_control(recycle_dlg), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True)],
        )
        rebuild()
        open_control(recycle_dlg)

    def start_update_check(event=None):
        if update_ui["status"] == "checking":
            return
        update_ui.update({"status": "checking", "error": ""})

        async def run_check():
            try:
                release = await asyncio.to_thread(
                    fetch_latest_release,
                    use_cache=event is None,
                )
                update_ui["latest"] = release
                update_ui["status"] = "available" if update_available(release) else "current"
            except Exception as exc:
                update_ui["status"] = "error"
                update_ui["error"] = f"检查失败：{str(exc)[:80]}"
            try:
                refresh()
            except (AttributeError, RuntimeError):
                pass

        try:
            page.run_task(run_check)
        except (AttributeError, RuntimeError, TypeError):
            update_ui["status"] = "error"
            update_ui["error"] = "当前运行环境无法启动更新检查"
        if event is not None:
            refresh()

    def open_update_download(event=None):
        if update_ui.get("status") == "downloading":
            return
        release = update_ui.get("latest")
        release = release if isinstance(release, dict) else {}
        url = str(release.get("apk_url") or "")
        if not url:
            snack("没有可用的安装包下载地址")
            return

        destination = default_apk_destination(str(release.get("apk_name") or "carbs_king.apk"))
        update_ui.update({
            "status": "downloading", "error": "", "download_path": "",
            "downloaded_bytes": 0, "total_bytes": int(release.get("size") or 0),
        })

        async def download():
            loop = asyncio.get_running_loop()

            def on_progress(downloaded: int, total: int) -> None:
                def apply_progress() -> None:
                    update_ui["downloaded_bytes"] = downloaded
                    update_ui["total_bytes"] = total or int(release.get("size") or 0)
                    try:
                        refresh()
                    except (AttributeError, RuntimeError):
                        pass
                loop.call_soon_threadsafe(apply_progress)

            try:
                artifact = await asyncio.to_thread(
                    download_apk,
                    url,
                    destination,
                    expected_size=int(release.get("size") or 0),
                    expected_sha256=str(release.get("sha256") or ""),
                    on_progress=on_progress,
                )
                update_ui.update({
                    "status": "downloaded", "download_path": str(artifact.path),
                    "downloaded_bytes": artifact.bytes_downloaded,
                    "total_bytes": artifact.total_bytes,
                })
                open_update_installer()
            except (ApkUpdateError, OSError, ValueError) as exc:
                update_ui.update({"status": "error", "error": f"下载失败：{str(exc)[:80]}"})
            finally:
                try:
                    refresh()
                except (AttributeError, RuntimeError):
                    pass

        try:
            page.run_task(download)
        except (AttributeError, RuntimeError, TypeError):
            update_ui.update({"status": "error", "error": "当前运行环境无法启动下载"})
        refresh()

    def open_update_installer(event=None):
        path = str(update_ui.get("download_path") or "")
        if not path:
            snack("安装包尚未下载完成")
            return
        try:
            result = open_android_installer(Path(path))
            update_ui["status"] = "install_permission" if result == "permission" else "installing"
        except ApkUpdateError as exc:
            update_ui.update({"status": "downloaded", "error": str(exc)})
            snack(str(exc))
        refresh()

    def play_challenge_completion_audio():
        audio = challenge_completion_audio["service"]
        if audio is None:
            return

        async def play_audio():
            try:
                await audio.play()
            except Exception:
                pass

        try:
            page.run_task(play_audio)
        except (AttributeError, RuntimeError):
            pass

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
            "age_reference_year": int(state.get("age_reference_year") or datetime.date.today().year),
            "theme_color": str(state.get("theme_color", "green")),
            "sex": state.get("sex", ""),
            "activity_habit": state.get("activity_habit", ""),
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
        completed_by_id = {
            str(item.get("id")): item
            for item in stored.get("completed", [])
            if isinstance(item, dict) and item.get("id")
        }
        challenges = [completed_by_id[identity] for identity in pending if identity in completed_by_id]
        if not challenges:
            return
        if any(int(challenge.get("level", -1) or -1) >= 4 for challenge in challenges):
            play_challenge_completion_audio()
        highest_challenge = max(
            challenges,
            key=lambda challenge: int(challenge.get("level", -1) or -1),
        )
        dialog = None

        def confirm(event=None):
            updated, consumed = consume_pending_celebrations(load_challenges())
            save_challenges(updated)
            close_control(dialog)
            celebration_state["dialog"] = None
            snack("挑战成果已收下" if len(consumed) == 1 else f"已收下 {len(consumed)} 项挑战成果")
            refresh()

        def dismissed(event=None):
            if celebration_state["dialog"] is dialog:
                celebration_state["dialog"] = None

        def dismiss(event=None):
            close_control(dialog)
            dismissed()

        progress_lines = [
            f"完成了：{str(challenge.get('declaration') or challenge.get('title') or '目标挑战').strip()}"
            for challenge in challenges
        ]
        dialog = build_achievement_celebration(
            {
                "title": (
                    str(challenges[0].get("title") or "目标挑战")
                    if len(challenges) == 1
                    else f"{len(challenges)} 项挑战已完成"
                ),
                "description": "\n".join(progress_lines),
                "level_color": str(highest_challenge.get("level_color") or YELLOW),
            },
            on_confirm=confirm,
            on_dismiss=dismissed,
            headline="挑战达成",
            confirm_label="收下挑战成果",
            message="Yeah Buddy! Light Weight Baby!",
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

    def show_failure_dialog(items=None, *, acknowledge_pending=False):
        if failure_state["dialog"] is not None or state.get("current_view") != "me":
            return
        stored = load_challenges()
        failed_by_id = {
            str(item.get("id")): item
            for item in stored.get("failed", [])
            if isinstance(item, dict) and item.get("id")
        }
        if items is None:
            pending = stored.get("pending_failures", [])
            failures = [failed_by_id[identity] for identity in pending if identity in failed_by_id]
            acknowledge_pending = True
        else:
            failures = [
                failed_by_id.get(str(item.get("id")), item)
                for item in items
                if isinstance(item, dict) and item.get("id")
            ]
            pending_ids = {str(identity) for identity in stored.get("pending_failures", [])}
            acknowledge_pending = any(str(item.get("id")) in pending_ids for item in failures)
        if not failures:
            return
        dialog = None

        def acknowledge():
            if not acknowledge_pending:
                return list(failures)
            updated, consumed = consume_pending_failures(load_challenges())
            save_challenges(updated)
            return consumed

        def retry(event=None):
            consumed = acknowledge()
            close_control(dialog)
            failure_state["dialog"] = None
            if consumed:
                open_retry_challenge(consumed[0])

        def keep(event=None):
            acknowledge()
            close_control(dialog)
            failure_state["dialog"] = None
            refresh()

        def dismiss_failure(event=None):
            close_control(dialog)
            failure_state["dialog"] = None

        failure_lines = [
            f"{item.get('title') or '目标挑战'}：{item.get('failure_reason') or '目标未完成'}"
            for item in failures
        ]
        failure_color = "#6F7774"
        failure_list_height = min(190, max(72, 44 + len(failure_lines) * 42))
        dialog = dialog_base(
            "挑战失败",
            ft.Container(
                content=ft.Column([
                    ft.Text("恭喜，你成功证明了计划不会自己完成。", size=16, weight="bold", color=failure_color),
                    ft.Text("计划写得挺狠，执行得挺软。", size=14, color=TEXT),
                    ft.Text("嘴硬没用，记录不会替你训练。", size=14, color=TEXT),
                    ft.Container(
                        content=ft.Column([small_text(line) for line in failure_lines], spacing=5, scroll=_SCROLL_HIDDEN),
                        bgcolor="#F0F2F1", border_radius=8, padding=10, height=failure_list_height,
                    ),
                ], spacing=10, tight=True),
                width=min(286, max(250, responsive_width() - 36)),
            ),
            [
                make_button("先挂着丢人", on_click=keep, bgcolor="#EEF0EF", color=failure_color, expand=True),
                make_button("不服，编辑后重来", on_click=retry, expand=True),
            ],
            on_close=dismiss_failure,
        )
        failure_state["dialog"] = dialog
        open_control(dialog)

    def show_pending_failure_dialog():
        show_failure_dialog()

    def schedule_challenge_failure():
        if failure_state["scheduled"] or failure_state["dialog"] is not None:
            return
        failure_state["scheduled"] = True

        async def show_after_render():
            await asyncio.sleep(0)
            failure_state["scheduled"] = False
            show_pending_failure_dialog()

        try:
            page.run_task(show_after_render)
        except (AttributeError, RuntimeError):
            failure_state["scheduled"] = False
            show_pending_failure_dialog()

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

    def open_new_challenge(initial_lane=None, preset=None, retry_source=None, event=None):
        if len(load_challenges().get("active", [])) >= 3:
            snack("最多只能同时进行 3 个挑战")
            return
        dialog_width = responsive_width()
        selected_mode = {"value": "recommended"}
        selected_custom = {"spec": None}
        sheet = None
        tabs = ft.Row(spacing=8)
        recommended_holder = ft.Container(expand=True)
        custom_holder = ft.Container(expand=True, visible=False)
        footer_cancel = make_button("取消", bgcolor=PRIMARY_SOFT, color=GREEN, expand=True)
        footer_custom = make_button("创建自定义挑战", expand=True)
        footer_custom.visible = False
        preset = dict(preset or {})
        retry_source = dict(retry_source or {})
        if initial_lane and not preset:
            lane_defaults = {"food": "nutrition_streak", "training": "training_sessions", "recovery": "water_streak"}
            preset["challenge_type"] = lane_defaults.get(initial_lane, "training_sessions")
            preset["lane"] = initial_lane
        lane_options = [ft.dropdown.Option(key, label) for key, label in LANE_LABELS.items()]
        recommendation_lane_options = [ft.dropdown.Option("all", "全部赛道"), *lane_options]
        default_lane = str(preset.get("lane") or initial_lane or "training")
        recommended_lane_box = mobile_dropdown("选择赛道", "all", recommendation_lane_options, width=dialog_width)

        def close_sheet(e=None):
            close_control(sheet)

        footer_cancel.on_click = close_sheet

        def save_created(challenge):
            try:
                updated, saved = add_challenge(load_challenges(), challenge, records, now=iso_now())
                if retry_source.get("id"):
                    updated = mark_failed_retried(updated, str(retry_source["id"]), now=iso_now())
                save_challenges(updated)
            except ValueError as exc:
                snack("最多只能同时进行 3 个挑战" if "最多三项" in str(exc) else str(exc))
                return False
            close_sheet()
            refresh()
            return True

        def create_from_template(template):
            selected_lane = str(recommended_lane_box.value or "all")
            creation_lane = str(template.get("lane") or "training") if selected_lane == "all" else selected_lane
            try:
                challenge = create_challenge(
                    template,
                    now=iso_now(),
                    lane=creation_lane,
                )
            except ValueError as exc:
                snack(str(exc))
                return
            save_created(challenge)

        level_colors = ("#2E9B62", "#2878C8", "#7651B8", "#E0822B", "#C73B3B")
        recommendation_profile = {
            "weight": state.get("weight", ""),
            "bodyfat": state.get("bodyfat", ""),
            "height": state.get("height", ""),
            "age": state.get("age", ""),
            "sex": state.get("sex", ""),
            "activity_habit": state.get("activity_habit", ""),
            "macro_goal": state.get("macro_goal", "减脂"),
            "circumference": state.get("circumference"),
        }
        recommendation_templates = visible_recommendations(
            load_challenges(), records, profile=recommendation_profile
        )

        def build_recommendation_controls(selected_lane="all"):
            recommendation_controls = [
                small_text("推荐会结合身体资料、运动频率和碳循环目标；只有点击创建后才会追踪和庆祝。"),
                recommended_lane_box,
            ]
            selected_lane = str(selected_lane or "all")
            filtered = filter_recommendations_by_lane(recommendation_templates, selected_lane)
            grouped: dict[str, list[dict[str, Any]]] = {}
            for template in filtered:
                grouped.setdefault(str(template.get("group") or "推荐挑战"), []).append(template)
            for group, templates in grouped.items():
                recommendation_controls.append(ft.Text(group, size=15, weight="bold", color=TEXT))
                for template in templates:
                    progress = recommendation_progress(template, records)
                    raw_level = max(0, int(template.get("level", 0)))
                    level = min(4, raw_level)
                    level_name = level_info(raw_level)["name"]
                    config = template.get("config", {})
                    rationale = str(config.get("rationale") or "") if isinstance(config, dict) else ""
                    details = [
                        ft.Row([
                            ft.Text(str(template.get("title") or "目标挑战"), size=14, weight="bold", color=TEXT, expand=True, max_lines=2, overflow="ellipsis"),
                            ft.Text(level_name, size=11, weight="bold", color=level_colors[level]),
                        ], spacing=6),
                    ]
                    if rationale:
                        details.append(small_text(rationale))
                    details.extend([
                        small_text(
                            f"历史进度 {progress['current']:g} / {progress['target']:g} "
                            f"{progress['unit']} · {progress['percent']:g}%"
                        ),
                        ft.ProgressBar(value=progress["percent"] / 100, color=level_colors[level], bgcolor="#E4EAE8", height=6),
                        small_text("点击创建并同步历史进度"),
                    ])
                    recommendation_controls.append(ft.Container(
                        content=ft.Column(details, spacing=6),
                        padding=10,
                        bgcolor=SURFACE,
                        border=ft.Border.all(1, level_colors[level]),
                        border_radius=8,
                        on_click=lambda e, template=template: create_from_template(template),
                    ))
            if not filtered:
                recommendation_controls.append(small_text("这个赛道当前没有可推荐项目；完善资料或完成上一等级后会自动更新。"))
            recommended_holder.content = ft.Column(recommendation_controls, spacing=9, scroll=_SCROLL_HIDDEN, expand=True)

        def change_recommendation_lane(event=None):
            event_value = getattr(getattr(event, "control", None), "value", None)
            selected_lane = str(event_value or recommended_lane_box.value or "all")
            recommended_lane_box.value = selected_lane
            build_recommendation_controls(selected_lane)
            try:
                page.update()
            except Exception:
                pass

        recommended_lane_box.on_change = change_recommendation_lane
        build_recommendation_controls("all")

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
        unit_box = mobile_dropdown("单位", preset.get("unit", "次"), [ft.dropdown.Option(value) for value in ("次", "天", "组", "kg", "lbs", "%", "cm")], expand=True)
        # Flet Web renders Dropdown's outlined surface taller than TextField at
        # the same declared height.  Calibrate the compact unit selector so its
        # visible border aligns with the adjacent numeric target field.
        unit_box.field.height = 46
        today = datetime.date.today()
        start_box, start_field = labeled_plain_field("开始日期（YYYY-MM-DD）", preset.get("start_date", today.isoformat()), expand=True)
        end_box, end_field = labeled_plain_field("结束日期（YYYY-MM-DD）", preset.get("end_date", (today + datetime.timedelta(days=30)).isoformat()), expand=True)
        selected_action = {
            "id": str(preset.get("action_id") or ""),
            "name": str(preset.get("action_name") or preset.get("action_id") or ""),
        }
        selected_action_text = ft.Text(selected_action["name"] or "未选择动作", size=14, weight="bold", color=TEXT)
        action_selection_holder = ft.Container(
            content=ft.Row([small_text("已选动作"), selected_action_text], alignment="spaceBetween"),
            padding=10, bgcolor="#F8FAFC", border_radius=8,
        )
        action_picker_button = make_button("从动作库选择动作", bgcolor=PRIMARY_SOFT, color=GREEN, expand=True)
        min_weight_box, min_weight_field = labeled_plain_field("重量门槛 kg", str(preset.get("min_weight", "")), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        duration_box, duration_field = labeled_plain_field("单次最低时长 min", str(preset.get("min_duration_min", 40)), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        start_hour_box, start_hour_field = labeled_plain_field("开始小时（0-23）", str(preset.get("start_hour", 6)), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        end_hour_box, end_hour_field = labeled_plain_field("结束小时（1-24）", str(preset.get("end_hour", 10)), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        date_rule_box = mobile_dropdown(
            "特殊日期类型", preset.get("date_rule", "weekend"),
            [ft.dropdown.Option("weekend", "周末"), ft.dropdown.Option("weekday", "工作日"), ft.dropdown.Option("dates", "指定日期")],
            expand=True,
        )
        special_dates_box, special_dates_field = labeled_plain_field(
            "指定日期（逗号分隔）", ",".join(preset.get("special_dates", [])) if isinstance(preset.get("special_dates"), list) else "", expand=True
        )
        daily_box, daily_field = labeled_plain_field("每日饮水阈值 ml", str(preset.get("daily_target", 2000)), keyboard_type=_KEYBOARD_NUMBER, expand=True)
        indicator_box = mobile_dropdown("饮食达标指标", preset.get("indicator", "protein"), [ft.dropdown.Option("protein", "蛋白质目标"), ft.dropdown.Option("carb_cycle", "碳循环目标")], expand=True)
        metric_box = mobile_dropdown("身体指标", preset.get("metric", "weight"), [ft.dropdown.Option(key, label) for key, (label, _) in BODY_METRICS.items()], expand=True)
        direction_box = mobile_dropdown("目标方向", preset.get("direction", "at_most"), [ft.dropdown.Option("at_most", "不高于"), ft.dropdown.Option("at_least", "不低于")], expand=True)

        def open_action_picker(e=None):
            catalog = exercise_catalog()
            categories = tuple(
                category for category in EXERCISE_CATEGORIES
                if any(item.get("category") == category for item in catalog)
            )
            picker_state = {
                "category": "胸" if "胸" in categories else categories[0],
                "subgroup": "全部",
                "equipment": "全部",
                "sort": "frequent",
            }
            search = ft.TextField(label="搜索动作名称、器械或目标肌群", autofocus=True)
            category_rows = ft.Column(spacing=3, width=82, scroll=_SCROLL_HIDDEN)
            subgroup_row = ft.Row(spacing=6, scroll=_SCROLL_HIDDEN)
            equipment_row = ft.Row(spacing=6, scroll=_SCROLL_HIDDEN)
            sort_row = ft.Row(spacing=6)
            results = ft.GridView(
                max_extent=280,
                child_aspect_ratio=2.0,
                spacing=8,
                run_spacing=8,
                expand=True,
                build_controls_on_demand=True,
                cache_extent=180,
            )
            picker = None
            usage_stats = exercise_usage_stats(records)

            def choose_action(exercise):
                selected_action["id"] = str(exercise.get("id") or exercise.get("name") or "")
                selected_action["name"] = str(exercise.get("name") or "")
                selected_action_text.value = selected_action["name"] or "未选择动作"
                close_control(picker)
                try:
                    page.update()
                except Exception:
                    pass

            def open_help(exercise):
                help_dialog = dialog_base(
                    str(exercise.get("name") or "动作说明"),
                    build_exercise_help(exercise, responsive_width(), _SCROLL_HIDDEN),
                    [make_button("知道了", on_click=lambda event: close_control(help_dialog), expand=True)],
                )
                open_control(help_dialog)

            def choose_category(category):
                picker_state.update({"category": category, "subgroup": "全部", "equipment": "全部"})
                rebuild_picker()

            def choose_subgroup(subgroup):
                picker_state.update({"subgroup": subgroup, "equipment": "全部"})
                rebuild_picker()

            def choose_equipment(equipment):
                picker_state["equipment"] = equipment
                rebuild_picker()

            def choose_sort(mode):
                picker_state["sort"] = mode
                rebuild_picker()

            def rebuild_picker(event=None):
                category_rows.controls = build_category_sidebar(categories, picker_state["category"], choose_category)
                category_items = [item for item in catalog if item.get("category") == picker_state["category"]]
                subgroups = list(dict.fromkeys(str(item.get("subgroup") or "整体") for item in category_items))
                if picker_state["subgroup"] not in {"全部", *subgroups}:
                    picker_state["subgroup"] = "全部"
                subgroup_row.controls = [
                    make_button(
                        label,
                        on_click=lambda click, value=label: choose_subgroup(value),
                        bgcolor=PRIMARY if picker_state["subgroup"] == label else PRIMARY_SOFT,
                        color="#FFFFFF" if picker_state["subgroup"] == label else GREEN,
                    )
                    for label in ("全部", *subgroups)
                ]
                subgroup_items = category_items if picker_state["subgroup"] == "全部" else [
                    item for item in category_items
                    if str(item.get("subgroup") or "整体") == picker_state["subgroup"]
                ]
                equipments = list(dict.fromkeys(str(item.get("equipment") or "其他") for item in subgroup_items))
                if picker_state["equipment"] not in {"全部", *equipments}:
                    picker_state["equipment"] = "全部"
                equipment_row.controls = [
                    make_button(
                        label,
                        on_click=lambda click, value=label: choose_equipment(value),
                        bgcolor=PRIMARY if picker_state["equipment"] == label else PRIMARY_SOFT,
                        color="#FFFFFF" if picker_state["equipment"] == label else GREEN,
                    )
                    for label in ("全部", *equipments)
                ]
                sort_row.controls = build_sort_row(choose_sort, picker_state["sort"]).controls
                query = str(getattr(getattr(event, "control", None), "value", search.value) or "").strip()
                matches = search_exercises(query, None if query else picker_state["category"], catalog)
                if not query and picker_state["subgroup"] != "全部":
                    matches = [
                        item for item in matches
                        if str(item.get("subgroup") or "整体") == picker_state["subgroup"]
                    ]
                if not query and picker_state["equipment"] != "全部":
                    matches = [
                        item for item in matches
                        if str(item.get("equipment") or "其他") == picker_state["equipment"]
                    ]
                matches = sort_exercises(matches, usage_stats, picker_state["sort"])[:24]
                results.controls.clear()
                for exercise in matches:
                    usage = usage_stats.get(str(exercise.get("name") or "").casefold(), {})
                    results.controls.append(build_exercise_card(
                        exercise,
                        usage,
                        lambda click, item=exercise: open_help(item),
                        lambda click, item=exercise: choose_action(item),
                    ))
                if not matches:
                    results.controls.append(small_text("没有匹配动作，请换一个关键词。"))
                try:
                    page.update()
                except Exception:
                    pass

            search.on_change = rebuild_picker
            content_width = responsive_width()
            browser_panel = ft.Row([
                ft.Container(content=category_rows, width=88, padding=ft.Padding(left=0, top=0, right=4, bottom=0)),
                ft.VerticalDivider(width=1, color="#D9E6E1"),
                ft.Column(
                    [subgroup_row, equipment_row, sort_row, results],
                    width=max(190, content_width - 100),
                    spacing=8,
                ),
            ], width=content_width, height=560, spacing=8)
            picker = build_full_form_sheet(
                FormViewContext(close_control=close_control, scroll_mode=_SCROLL_HIDDEN),
                f"选择动作 · {len(catalog)} 个",
                [search, browser_panel],
                lambda event: None,
                "选择动作",
                footer_controls=[
                    make_button("取消", on_click=lambda event: close_control(picker), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
                ],
            )
            rebuild_picker()
            open_control(picker)

        action_picker_button.on_click = open_action_picker

        def update_custom_fields(e=None):
            challenge_type = str(type_box.value or "training_sessions")
            spec = selected_custom.get("spec") or {}
            action_selection_holder.visible = bool(spec.get("action_required")) or challenge_type == "max_weight"
            action_picker_button.visible = action_selection_holder.visible
            min_weight_box.visible = bool(spec.get("min_weight_required")) or challenge_type == "heavy_sets"
            duration_box.visible = bool(spec.get("duration_required")) or challenge_type in {"effective_training_days", "effective_training_streak", "cardio_sessions"}
            start_hour_box.visible = bool(spec.get("time_window_required")) or challenge_type == "time_window_sessions"
            end_hour_box.visible = start_hour_box.visible
            date_rule_box.visible = bool(spec.get("date_rule_required")) or challenge_type == "special_day_sessions"
            special_dates_box.visible = date_rule_box.visible and str(date_rule_box.value or "") == "dates"
            daily_box.visible = challenge_type == "water_streak"
            indicator_box.visible = challenge_type == "nutrition_streak"
            metric_box.visible = challenge_type == "body_target"
            direction_box.visible = challenge_type == "body_target"
            units = {
                "training_volume": "kg", "max_weight": "kg", "training_sessions": "次",
                "training_days": "天", "training_streak": "天", "exercise_reps": "次", "training_sets": "组",
                "heavy_sets": "组", "effective_training_days": "天", "effective_training_streak": "天",
                "cardio_sessions": "次", "time_window_sessions": "次", "special_day_sessions": "次", "water_streak": "天",
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
        date_rule_box.on_change = update_custom_fields
        custom_form_holder = ft.Container(expand=True, visible=False)
        custom_catalog_holder = ft.Container(expand=True)
        custom_spec_title = ft.Text("", size=18, weight="bold", color=TEXT)
        custom_spec_description = small_text("")
        custom_form_holder.content = ft.Column([
            make_button("← 返回自定义类型", on_click=lambda e: show_custom_catalog(), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True),
            custom_spec_title,
            custom_spec_description,
            small_text("自定义挑战为金色，不参与推荐等级链。"),
            title_box,
            declaration_box,
            lane_box,
            two_field_grid(target_box, unit_box, viewport_width=dialog_width),
            ft.Row([start_box, end_box], spacing=8),
            action_selection_holder,
            action_picker_button,
            min_weight_box,
            duration_box,
            ft.Row([start_hour_box, end_hour_box], spacing=8),
            date_rule_box,
            special_dates_box,
            daily_box,
            indicator_box,
            metric_box,
            direction_box,
        ], spacing=9, scroll=_SCROLL_HIDDEN, expand=True)

        def show_custom_catalog():
            selected_custom["spec"] = None
            custom_catalog_holder.visible = True
            custom_form_holder.visible = False
            footer_custom.visible = False
            try:
                page.update()
            except Exception:
                pass

        def open_custom_spec(spec, *, preserve_values=False):
            selected_custom["spec"] = dict(spec)
            if not preserve_values:
                selected_action.update({"id": "", "name": ""})
                selected_action_text.value = "未选择动作"
            type_box.value = str(spec.get("challenge_type") or "training_sessions")
            default_unit = str(spec.get("unit") or "次")
            allowed_units = ("kg", "lbs") if default_unit == "kg" else (default_unit,)
            unit_box.field.options = [ft.dropdown.Option(value) for value in allowed_units]
            unit_box.field.disabled = len(allowed_units) == 1
            unit_box.value = str(preset.get("unit") or default_unit) if preserve_values else default_unit
            if not preserve_values:
                title_field.value = str(spec.get("title") or "自定义挑战").split(" (")[0]
            custom_spec_title.value = str(spec.get("title") or "自定义挑战")
            custom_spec_description.value = str(spec.get("description") or "")
            custom_catalog_holder.visible = False
            custom_form_holder.visible = True
            footer_custom.visible = selected_mode["value"] == "custom"
            update_custom_fields()

        catalog_controls = []
        for category in CUSTOM_CHALLENGE_CATALOG:
            catalog_controls.append(ft.Text(str(category["group"]), size=17, weight="bold", color=TEXT))
            for spec in category["items"]:
                catalog_controls.append(ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(str(spec["title"]), size=15, color=TEXT),
                            small_text(str(spec["description"])),
                        ], spacing=3, expand=True),
                        ft.Text("›", size=28, color="#A8B0AD"),
                    ], spacing=8),
                    padding=14,
                    bgcolor=SURFACE,
                    border=ft.Border.all(1, "#E0E5E3"),
                    border_radius=10,
                    on_click=lambda e, spec=spec: open_custom_spec(spec),
                ))
        custom_catalog_holder.content = ft.Column(catalog_controls, spacing=10, scroll=_SCROLL_HIDDEN, expand=True)
        custom_holder.content = ft.Column([custom_catalog_holder, custom_form_holder], spacing=0, expand=True)
        show_custom_catalog()

        def select_mode(value):
            selected_mode["value"] = value
            recommended_holder.visible = value == "recommended"
            custom_holder.visible = value == "custom"
            footer_custom.visible = value == "custom" and selected_custom.get("spec") is not None
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
            spec = selected_custom.get("spec") or {}
            challenge_type = str(type_box.value or "")
            action_id = str(selected_action.get("id") or "").strip()
            if spec.get("action_required") and not action_id:
                snack("请选择一个训练动作")
                return
            payload = {
                "title": str(title_field.value or "").strip(),
                "declaration": str(declaration_field.value or "").strip(),
                "challenge_type": challenge_type,
                "lane": str(lane_box.value or "training"),
                "target": to_float(target_field.value, 0),
                "unit": str(unit_box.value or ""),
                "start_date": str(start_field.value or "").strip(),
                "end_date": str(end_field.value or "").strip(),
                "action_id": action_id,
                "action_name": str(selected_action.get("name") or ""),
                "min_weight": to_float(min_weight_field.value, 0),
                "min_duration_min": to_float(duration_field.value, 0),
                "start_hour": to_float(start_hour_field.value, 0),
                "end_hour": to_float(end_hour_field.value, 24),
                "date_rule": str(date_rule_box.value or "weekend"),
                "special_dates": [item.strip() for item in str(special_dates_field.value or "").replace("，", ",").split(",") if item.strip()],
                "daily_target": to_float(daily_field.value, 0),
                "indicator": str(indicator_box.value or "protein"),
                "metric": str(metric_box.value or "weight"),
                "direction": (
                    str(direction_box.value or "at_most")
                    if challenge_type == "body_target"
                    else "at_least"
                ),
            }
            if retry_source:
                for key in ("template_id", "chain_id", "group", "level", "level_name", "level_color", "config"):
                    if key in retry_source:
                        payload[key] = retry_source[key]
            try:
                challenge = create_challenge(payload, now=iso_now())
            except ValueError as exc:
                snack(str(exc))
                return
            save_created(challenge)

        footer_custom.on_click = save_custom
        if retry_source:
            footer_custom.content.controls[-1].value = "重新挑战"
            select_mode("custom")
            challenge_type = str(preset.get("challenge_type") or "training_sessions")
            action_id = str(preset.get("action_id") or "")
            matching_specs = [
                spec
                for category in CUSTOM_CHALLENGE_CATALOG
                for spec in category["items"]
                if str(spec.get("challenge_type") or "") == challenge_type
            ]
            retry_spec = next(
                (
                    spec for spec in matching_specs
                    if bool(spec.get("action_required")) == bool(action_id)
                ),
                matching_specs[0] if matching_specs else {
                    "title": TYPE_LABELS.get(challenge_type, "自定义挑战"),
                    "description": "编辑目标后重新开始挑战",
                    "challenge_type": challenge_type,
                    "unit": str(preset.get("unit") or "次"),
                },
            )
            open_custom_spec(retry_spec, preserve_values=True)
        else:
            select_mode("recommended")
        sheet = build_full_form_sheet(
            FormViewContext(close_control=close_control, scroll_mode=_SCROLL_HIDDEN),
            "编辑后重新挑战" if retry_source else "新建挑战",
            [tabs, recommended_holder, custom_holder],
            save_custom,
            "创建自定义挑战",
            footer_controls=[footer_cancel, footer_custom],
        )
        open_control(sheet)

    def open_retry_challenge(item):
        source = dict(item or {})
        if not source.get("id"):
            return
        nested = source.get("config", {}) if isinstance(source.get("config"), dict) else {}
        preset = {**nested, **source}
        today = datetime.date.today()
        try:
            old_start = datetime.date.fromisoformat(str(source.get("start_date") or ""))
            old_end = datetime.date.fromisoformat(str(source.get("end_date") or ""))
            duration_days = max(1, (old_end - old_start).days + 1)
        except ValueError:
            duration_days = 31
        preset["start_date"] = today.isoformat()
        preset["end_date"] = (today + datetime.timedelta(days=duration_days - 1)).isoformat()
        open_new_challenge(
            initial_lane=str(source.get("lane") or "training"),
            preset=preset,
            retry_source=source,
        )

    def open_challenge_detail(item):
        progress = challenge_progress(item, records, today=datetime.date.today().isoformat())
        try:
            end_date = datetime.date.fromisoformat(str(item.get("end_date") or ""))
            remaining = max(0, (end_date - datetime.date.today()).days)
            remaining_text = f"剩余 {remaining} 天"
        except ValueError:
            remaining_text = "持续记录中"
        declaration = str(item.get("declaration") or "").strip()
        content = ft.Column([
            ft.Row([
                ft.Text(str(item.get("level_name") or "自定义"), size=12, weight="bold", color=str(item.get("level_color") or YELLOW)),
                small_text(TYPE_LABELS.get(str(item.get("challenge_type") or ""), "目标挑战")),
            ], alignment="spaceBetween"),
            ft.Text(str(item.get("title") or "目标挑战"), size=20, weight="bold", color=TEXT),
            small_text(declaration) if declaration else ft.Container(height=0),
            ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"{progress['current']:g} {progress['unit']}", size=20, weight="bold", color=TEXT),
                        small_text("当前进度"),
                    ], horizontal_alignment="center", spacing=4),
                    padding=12, bgcolor="#F8FAFC", border_radius=8, expand=True,
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"{progress['target']:g} {progress['unit']}", size=20, weight="bold", color=TEXT),
                        small_text("目标值"),
                    ], horizontal_alignment="center", spacing=4),
                    padding=12, bgcolor="#F8FAFC", border_radius=8, expand=True,
                ),
            ], spacing=8),
            ft.Row([
                ft.Text(f"{progress['percent']:g}%", size=17, weight="bold", color=PRIMARY),
                small_text(remaining_text),
            ], alignment="spaceBetween"),
            ft.ProgressBar(value=max(0, min(1, progress["percent"] / 100)), color=PRIMARY, bgcolor="#E4EAE8", height=7),
            small_text(f"{item.get('start_date', '')} 至 {item.get('end_date', '')}"),
            small_text(f"所属赛道：{LANE_LABELS.get(str(item.get('lane') or ''), '未分类')}"),
        ], spacing=8, tight=True)
        dialog = dialog_base(
            "挑战详情",
            content,
            [make_button("关闭", on_click=lambda e: close_control(dialog), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True)],
            on_close=lambda e=None: close_control(dialog),
        )
        open_control(dialog)

    def render_challenge_panel():
        if repositories.goal_challenges is None:
            return render_legacy_compatibility_wall()
        stored, _ = sync_challenges()

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

        pending_ids = set(stored.get("pending_celebrations", []))
        pending_success = [
            item for item in stored.get("completed", [])
            if str(item.get("id") or "") in pending_ids
        ]
        visible_failed = [
            item for item in stored.get("failed", [])
            if not item.get("retried_at")
        ]

        def open_panel_item(item):
            identity = str(item.get("id") or "")
            if item.get("awaiting_confirmation") or identity in pending_ids:
                show_next_challenge_celebration()
            elif item.get("status") == "failed":
                show_failure_dialog([item])
            else:
                open_challenge_detail(item)

        return build_goal_challenge_panel(
            stored.get("active", []),
            on_new=lambda e=None: open_new_challenge(),
            on_completed=open_completed_challenges,
            on_delete_toggle=toggle_delete,
            delete_mode=challenge_ui["delete_mode"],
            selected_ids=challenge_ui["selected"],
            on_select=select_delete,
            on_delete_confirm=remove_selected_challenges,
            on_open=open_panel_item,
            pending_success=pending_success,
            failed=visible_failed,
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

        def persist_body_profile(event=None):
            """Save the body/profile field that just finished editing."""
            set_input_focused(False)
            assign_visible_fields()
            state["age_reference_year"] = datetime.date.today().year
            save_profile_from_state()
            save_current()
            field = getattr(event, "control", None)
            labels = {
                id(weight_field): "体重已保存",
                id(bodyfat_field): "体脂已保存",
                id(height_field): "身高已保存",
                id(age_field): "年龄已保存",
            }
            snack(labels.get(id(field), "资料已保存"))

        weight_field.on_blur = persist_body_profile
        bodyfat_field.on_blur = persist_body_profile
        height_field.on_blur = persist_body_profile
        age_field.on_blur = persist_body_profile

        def set_sex(value):
            persist_visible_profile(sex_value=value)
            refresh()

        def set_activity(value):
            persist_visible_profile(habit_value=value)
            refresh()

        def set_theme(value):
            state["theme_color"] = value
            save_profile_from_state()
            try:
                from theme_service import apply_theme
                apply_theme(page, value)
                page.update()
            except Exception:
                pass

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

        if update_ui["status"] == "idle":
            start_update_check()

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
            theme_panel=build_theme_panel(state.get("theme_color", "green"), set_theme),
            feature_panels=[
                build_background_rest_panel(
                    rest_permission_status(),
                    on_notification=lambda e: request_rest_permission("notification"),
                    on_exact_alarm=lambda e: request_rest_permission("exact_alarm"),
                    on_overlay=lambda e: request_rest_permission("overlay"),
                ),
                build_training_recycle_panel(
                    len(load_recycled_training_sessions()), open_training_recycle_bin
                ),
            ],
            backup_panel=build_backup_panel(export_handler, import_backup_handler, clear_personal_data),
            update_panel=build_update_panel(
                current_version=VERSION_NAME,
                current_build=BUILD_NUMBER,
                status=str(update_ui.get("status") or "idle"),
                latest=update_ui.get("latest"),
                error=str(update_ui.get("error") or ""),
                on_check=start_update_check,
                on_download=open_update_download,
                on_install=open_update_installer,
                downloaded_bytes=int(update_ui.get("downloaded_bytes") or 0),
                total_bytes=int(update_ui.get("total_bytes") or 0),
            ),
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
            state["age_reference_year"] = datetime.date.today().year
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
        state.profile.theme_color = str(current_profile.get("theme_color", state.profile.theme_color))
        try:
            from theme_service import apply_theme
            apply_theme(page, state.profile.theme_color)
        except Exception:
            pass
        try:
            state.profile.age_reference_year = int(current_profile.get("age_reference_year") or datetime.date.today().year)
        except (TypeError, ValueError):
            state.profile.age_reference_year = datetime.date.today().year
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
