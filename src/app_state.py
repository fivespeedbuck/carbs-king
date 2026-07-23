"""Typed runtime state shared by feature controllers and the app shell."""

from __future__ import annotations

import copy
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, TypedDict

from app_defaults import DEFAULT_MACRO_MULTIPLIERS


class TrainingData(TypedDict, total=False):
    total_duration_min: str | float
    total_calories_kcal: str | float
    fatigue_status: str
    summary_note: str
    targets: list[dict[str, Any]]
    carb_reminder_dismissed_signature: str
    session: dict[str, Any] | None
    sessions: list[dict[str, Any]]


class SleepData(TypedDict, total=False):
    bed_time: str
    wake_time: str
    naps: list[dict[str, str]]


class DataPageData(TypedDict, total=False):
    period_days: int
    active_tab: str
    chart_kind: str
    metric_key: str | None
    selected_trend_date: str | None
    body_part_filter: str
    selected_date: str | None
    calendar_month: str | None
    action_trend_open: bool
    selected_exercise: str | None
    raw_expanded: bool


@dataclass
class ProfileState:
    weight: str = "62.5"
    bodyfat: str = "13"
    height: str = "170"
    age: str = "30"
    sex: str = "男"
    activity_habit: str = "规律训练"
    waist_cm: str = ""
    arm_cm: str = ""
    chest_cm: str = ""
    hip_cm: str = ""
    thigh_cm: str = ""
    calf_cm: str = ""
    macro_mode: str = "auto"
    macro_multipliers: dict[str, dict[str, float]] = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS)
    )
    auto_macro_multipliers: dict[str, dict[str, float]] = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_MACRO_MULTIPLIERS)
    )
    initialized: bool = False


@dataclass
class DailyState:
    selected_date: str = field(default_factory=lambda: date.today().isoformat())
    day_type: str = "高碳日"
    measurement: dict[str, Any] | None = None
    circumference: dict[str, Any] | None = None
    meals: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    training: TrainingData = field(default_factory=lambda: TrainingData(
        total_duration_min="",
        total_calories_kcal="",
        fatigue_status="状态一般",
        summary_note="",
        targets=[],
        carb_reminder_dismissed_signature="",
        session=None,
        sessions=[],
    ))
    water: list[int] = field(default_factory=list)
    supplements: list[dict[str, Any]] = field(default_factory=list)
    sleep: SleepData = field(default_factory=lambda: SleepData(bed_time="", wake_time="", naps=[]))


@dataclass
class NavigationState:
    current_view: str = "today"
    selected_meal: str = "汇总"
    advice_expanded: bool = False
    history_trend_expanded: bool = False
    achievements_expanded: bool = False


@dataclass
class TrainingUiState:
    exercise_index: int = 0
    set_index: int = 0
    last_complete_click_at: float = 0.0


@dataclass
class AppState(MutableMapping[str, Any]):
    """Typed state with a mapping adapter for the persisted v50.1 field names.

    Typed attributes own the data. The mapping API is the stable boundary used
    by record serializers and feature controllers, and never creates a second
    state store.
    """

    profile: ProfileState = field(default_factory=ProfileState)
    daily: DailyState = field(default_factory=DailyState)
    navigation: NavigationState = field(default_factory=NavigationState)
    training_ui: TrainingUiState = field(default_factory=TrainingUiState)
    data_page: DataPageData = field(default_factory=lambda: DataPageData(
        period_days=7,
        active_tab="趋势",
        chart_kind="weight",
        metric_key="weight_kg",
        selected_trend_date=None,
        body_part_filter="全部",
        selected_date=date.today().isoformat(),
        action_trend_open=False,
        selected_exercise=None,
        raw_expanded=False,
    ))

    @classmethod
    def default(cls, meals: list[str] | tuple[str, ...]) -> "AppState":
        state = cls()
        state.daily.meals = {meal: [] for meal in meals}
        return state

    def _bindings(self) -> dict[str, tuple[Any, str]]:
        return {
            "date": (self.daily, "selected_date"),
            "weight": (self.profile, "weight"),
            "bodyfat": (self.profile, "bodyfat"),
            "measurement": (self.daily, "measurement"),
            "circumference": (self.daily, "circumference"),
            "height": (self.profile, "height"),
            "age": (self.profile, "age"),
            "sex": (self.profile, "sex"),
            "activity_habit": (self.profile, "activity_habit"),
            "waist_cm": (self.profile, "waist_cm"),
            "arm_cm": (self.profile, "arm_cm"),
            "chest_cm": (self.profile, "chest_cm"),
            "hip_cm": (self.profile, "hip_cm"),
            "thigh_cm": (self.profile, "thigh_cm"),
            "calf_cm": (self.profile, "calf_cm"),
            "macro_mode": (self.profile, "macro_mode"),
            "macro_multipliers": (self.profile, "macro_multipliers"),
            "auto_macro_multipliers": (self.profile, "auto_macro_multipliers"),
            "profile_inited": (self.profile, "initialized"),
            "day_type": (self.daily, "day_type"),
            "meals": (self.daily, "meals"),
            "training": (self.daily, "training"),
            "water": (self.daily, "water"),
            "supplements": (self.daily, "supplements"),
            "sleep": (self.daily, "sleep"),
            "current_view": (self.navigation, "current_view"),
            "selected_meal": (self.navigation, "selected_meal"),
            "advice_expanded": (self.navigation, "advice_expanded"),
            "history_trend_expanded": (self.navigation, "history_trend_expanded"),
            "achievements_expanded": (self.navigation, "achievements_expanded"),
            "training_exercise_index": (self.training_ui, "exercise_index"),
            "training_set_index": (self.training_ui, "set_index"),
            "last_complete_click_at": (self.training_ui, "last_complete_click_at"),
            "data_page": (self, "data_page"),
        }

    def __getitem__(self, key: str) -> Any:
        owner, attribute = self._bindings()[key]
        return getattr(owner, attribute)

    def __setitem__(self, key: str, value: Any) -> None:
        owner, attribute = self._bindings()[key]
        setattr(owner, attribute, value)

    def __delitem__(self, key: str) -> None:
        raise TypeError("AppState fields cannot be deleted")

    def __iter__(self) -> Iterator[str]:
        return iter(self._bindings())

    def __len__(self) -> int:
        return len(self._bindings())


__all__ = [
    "AppState", "DailyState", "DataPageData", "NavigationState", "ProfileState",
    "SleepData", "TrainingData", "TrainingUiState",
]
