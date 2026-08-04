"""Today dashboard orchestration and date navigation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import datetime
from datetime import date
from typing import Any

import flet as ft

from app_state import AppState
from controller_runtime import ControllerRuntime
from dynamic_carb_adapter import normalize_training
from form_views import build_dialog
from today_views import TODAY_SECTION_SPACING, TodayDashboardActions, TodayDashboardModel, build_date_toolbar, build_today_dashboard
from training_service import completed_set_count, find_active_daily_session, planned_set_count, session_volume
from ui_components import GREEN, PRIMARY_SOFT, make_button


@dataclass(frozen=True)
class TodayControllerDependencies:
    state: AppState
    records: Mapping[str, Any]
    runtime: ControllerRuntime
    nutrition: Any
    training: Any
    recovery: Any
    daily_records: Any
    meals: Sequence[str]
    responsive_bar_width: Callable[[], int]
    training_clock_refs: dict[str, Any]
    today: Callable[[], date] = date.today


class TodayController:
    def __init__(self, deps: TodayControllerDependencies):
        self.deps = deps

    def format_date_label(self) -> str:
        selected = str(self.deps.state["date"])
        try:
            value = datetime.datetime.strptime(selected, "%Y-%m-%d")
            return f"{value.year}年{value.month:02d}月{value.day:02d}日"
        except Exception:
            return selected

    def shift_date(self, delta: int) -> None:
        selected = datetime.datetime.strptime(str(self.deps.state["date"]), "%Y-%m-%d")
        self.deps.daily_records.load((selected + datetime.timedelta(days=delta)).strftime("%Y-%m-%d"))

    def open_calendar_picker(self) -> None:
        picker = ft.DatePicker(
            locale=ft.Locale("zh", "CN"),
            help_text="选择日期",
            cancel_text="取消",
            confirm_text="确定",
        )

        def on_change(e=None):
            value = getattr(picker, "value", None)
            chosen = None
            if value:
                try:
                    chosen = value.date().isoformat()
                except Exception:
                    try:
                        chosen = value.isoformat()[:10]
                    except Exception:
                        pass
            if chosen:
                self.deps.daily_records.load(chosen, show=True)
            self.deps.runtime.close_control(picker)

        def on_dismiss(e=None):
            try:
                self.deps.runtime.close_control(picker)
            except Exception:
                pass

        try:
            picker.value = datetime.datetime.strptime(str(self.deps.state["date"]), "%Y-%m-%d")
        except Exception:
            pass
        picker.on_change = on_change
        picker.on_dismiss = on_dismiss
        self.deps.runtime.open_control(picker)

    def render_toolbar(self) -> ft.Control:
        return build_date_toolbar(
            self.format_date_label(),
            lambda e: self.shift_date(-1),
            lambda e: self.open_calendar_picker(),
            lambda e: self.shift_date(1),
            lambda e: self.deps.daily_records.load(self.deps.today().isoformat()),
            lambda e: self.deps.daily_records.save(True),
        )

    def render_dashboard(self) -> ft.Control:
        state = self.deps.state
        total = self.deps.nutrition.daily_total()
        targets = self.deps.nutrition.targets()
        evaluation = self.deps.nutrition.evaluate(total)
        active_date = self.deps.training.find_active_session_date()
        session = self.deps.training.session_model()
        status = session.status if session else "planned"
        completed = completed_set_count(session) if session else 0
        planned = planned_set_count(session) if session else 0
        training_facts = normalize_training(state.get("training", {}))
        training_state = str(training_facts.get("status") or "unknown")

        if active_date and active_date != state.get("date"):
            _, active_session = find_active_daily_session(self.deps.records)
            title = "继续跨日训练"
            subtitle = f"训练开始于 {active_date} · {self.deps.training.clock_text(self.deps.training.elapsed_seconds(active_session))}"
            icon = ft.Icons.PLAY_CIRCLE_FILLED
        elif status == "active":
            title = "继续训练"
            subtitle = f"已完成 {completed}/{planned} 组 · {self.deps.training.clock_text(self.deps.training.elapsed_seconds(self.deps.training.session_data()))}"
            icon = ft.Icons.PLAY_CIRCLE_FILLED
        elif status == "completed":
            title = "今日训练已完成"
            subtitle = f"{completed} 组 · 容量 {session_volume(session):g} kg"
            icon = ft.Icons.EMOJI_EVENTS
        elif training_state == "unknown":
            title = "今天准备训练吗？"
            subtitle = "点击选择今天训练或休息"
            icon = ft.Icons.HELP_OUTLINE
        elif training_state == "explicit_rest":
            title = "今日休息"
            subtitle = "当前按低碳日执行，仍可改为训练"
            icon = ft.Icons.SELF_IMPROVEMENT
        else:
            title = "开始今天的训练"
            subtitle = (
                "确认动作、组数和负重后更新今日目标"
                if training_state == "planned_pending"
                else "训练计划已确认"
            )
            icon = ft.Icons.FITNESS_CENTER

        def open_today_decision(_=None):
            if training_state not in {"unknown", "explicit_rest"}:
                self.deps.runtime.navigate("training")
                return
            decision = build_dialog(
                "今天准备训练吗？",
                ft.Text("选择训练后进入训练页添加动作；确认动作参数后，今日目标会自动更新。"),
                [
                    make_button(
                        "今天休息", on_click=lambda e: (
                            self.deps.runtime.close_control(decision), self.deps.training.mark_today_rest()
                        ), bgcolor=PRIMARY_SOFT, color=GREEN, expand=True,
                    ),
                    make_button(
                        "今天训练", on_click=lambda e: (
                            self.deps.runtime.close_control(decision), self.deps.training.prepare_today_training()
                        ), expand=True,
                    ),
                ],
                on_close=lambda e: self.deps.runtime.close_control(decision),
            )
            self.deps.runtime.open_control(decision)

        result = build_today_dashboard(
            TodayDashboardModel(
                kcal=total["kcal"],
                kcal_target=evaluation["kcal_target"],
                day_type=str(targets.get("day_label") or state["day_type"]),
                macros=total,
                targets=targets,
                training_title=title,
                training_subtitle=subtitle,
                training_icon=icon,
                training_clock_active=bool(active_date or status == "active"),
                meal_counts={meal: len(items) if isinstance(items, list) else 0 for meal, items in state.get("meals", {}).items()},
                water_ml=int(sum(state.get("water", []))),
                supplement_count=len(state.get("supplements", [])),
                sleep_text=self.deps.recovery.format_minutes(self.deps.recovery.sleep_total_minutes())
                if self.deps.recovery.sleep_total_minutes() else "未记录",
            ),
            TodayDashboardActions(
                open_training=lambda e: self.deps.training.resume_session_date(active_date)
                if active_date and active_date != state.get("date")
                else open_today_decision(e),
                open_meal=lambda meal: (state.update({"selected_meal": meal}), self.deps.runtime.navigate("diet")),
                open_recovery=lambda e: self.deps.runtime.navigate("daily_details"),
            ),
            self.deps.meals,
            self.deps.responsive_bar_width(),
        )
        self.deps.training_clock_refs["dashboard"] = result.training_clock
        return result.control

    def render_page(self) -> ft.Control:
        dashboard = self.render_dashboard()
        controls = getattr(dashboard, "controls", None)
        dashboard_controls = list(controls) if isinstance(controls, list) else [dashboard]
        return ft.Column([*dashboard_controls, self.render_toolbar()], spacing=TODAY_SECTION_SPACING)


__all__ = ["TodayController", "TodayControllerDependencies"]
