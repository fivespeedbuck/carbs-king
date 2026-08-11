"""Today dashboard orchestration and date navigation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import datetime
from datetime import date
from typing import Any

import flet as ft

from analytics_calendar_views import _render_calendar
from analytics_model import DataPageConfig, build_data_page_model
from analytics_service import summarize_daily_training
from app_state import AppState
from controller_runtime import ControllerRuntime
from dynamic_carb_adapter import normalize_training
from form_views import FormViewContext, build_dialog, build_full_form_sheet
from today_views import TODAY_SECTION_SPACING, TodayDashboardActions, TodayDashboardModel, build_date_toolbar, build_today_dashboard
from training_service import completed_set_count, find_active_daily_session, planned_set_count
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

    @staticmethod
    def completed_training_subtitle(training: Mapping[str, Any], record_date: str = "") -> str:
        summary = summarize_daily_training(training, record_date)
        parts: list[str] = []
        formal_sets = int(summary.get("formal_sets") or 0)
        volume_kg = float(summary.get("volume_kg") or 0)
        cardio_minutes = float(summary.get("cardio_duration_min") or 0)
        if formal_sets:
            parts.extend((f"{formal_sets} 组", f"容量 {volume_kg:g} kg"))
        if cardio_minutes:
            parts.append(f"有氧 {cardio_minutes:g} 分钟")
        return " · ".join(parts) or "训练已完成"

    def open_calendar_picker(self) -> None:
        calendar_state = {"month": str(self.deps.state["date"])[:7]}
        calendar_holder = ft.Column(spacing=0)
        calendar_sheet = None

        def redraw() -> None:
            model = build_data_page_model(
                self.deps.records,
                end_date=self.deps.today().isoformat(),
                config=DataPageConfig(
                    active_tab="月历",
                    selected_date=str(self.deps.state["date"]),
                    calendar_month=calendar_state["month"],
                ),
            )
            calendar_holder.controls = [
                _render_calendar(
                    model,
                    choose_date,
                    on_calendar_month_change=change_month,
                    compact=True,
                    show_legend=False,
                )
            ]
            update = getattr(self.deps.runtime.page, "update", None)
            if callable(update):
                update()

        def choose_date(chosen: str) -> None:
            self.deps.daily_records.load(chosen, show=True)
            self.deps.runtime.close_control(calendar_sheet)

        def change_month(month: str) -> None:
            calendar_state["month"] = month
            redraw()

        calendar_sheet = build_full_form_sheet(
            FormViewContext(close_control=self.deps.runtime.close_control, scroll_mode=ft.ScrollMode.HIDDEN),
            "选择日期",
            [calendar_holder],
            lambda e: self.deps.runtime.close_control(calendar_sheet),
            show_footer=False,
        )
        redraw()
        self.deps.runtime.open_control(calendar_sheet)

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
            subtitle = self.completed_training_subtitle(state.get("training", {}), str(state.get("date") or ""))
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
