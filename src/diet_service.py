"""State contracts for the diet information architecture."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any, Final, Literal


DietView = Literal["today_diet", "food_library"]

TODAY_DIET_VIEW: Final[DietView] = "today_diet"
FOOD_LIBRARY_VIEW: Final[DietView] = "food_library"
SUPPLEMENT_LIBRARY_VIEW: Final[str] = "supplement_library"

DIET_VIEWS: Final[tuple[DietView, ...]] = (
    TODAY_DIET_VIEW,
    FOOD_LIBRARY_VIEW,
)

DIET_VIEW_LABELS: Final[dict[DietView, str]] = {
    TODAY_DIET_VIEW: "今日饮食",
    FOOD_LIBRARY_VIEW: "食物库",
}

LEGACY_DIET_VIEW_MAP: Final[dict[str, DietView]] = {
    "diet": TODAY_DIET_VIEW,
    "foods": FOOD_LIBRARY_VIEW,
    "supplements": TODAY_DIET_VIEW,
    TODAY_DIET_VIEW: TODAY_DIET_VIEW,
    FOOD_LIBRARY_VIEW: FOOD_LIBRARY_VIEW,
    SUPPLEMENT_LIBRARY_VIEW: TODAY_DIET_VIEW,
}

RECOVERY_SUPPLEMENT_SURFACES: Final[tuple[str, ...]] = ("today_supplements", "supplement_library")
ME_PAGE_BLOCKED_SUPPLEMENT_ACTIONS: Final[frozenset[str]] = frozenset({
    "set_view:supplements",
    "render_supp_library",
    "open_supp_library_dialog",
    "delete_supp",
})


class PersistedSupplementList(list[dict[str, Any]]):
    """List-compatible supplement library that persists every structural mutation."""

    def __init__(self, values: Iterable[dict[str, Any]], on_change: Callable[[list[dict[str, Any]]], None]):
        super().__init__(values)
        self._on_change = on_change

    def _persist(self) -> None:
        self._on_change(self)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._persist()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._persist()

    def append(self, value):
        super().append(value)
        self._persist()

    def extend(self, values):
        super().extend(values)
        self._persist()

    def insert(self, index, value):
        super().insert(index, value)
        self._persist()

    def pop(self, index=-1):
        value = super().pop(index)
        self._persist()
        return value

    def remove(self, value):
        super().remove(value)
        self._persist()

    def clear(self):
        super().clear()
        self._persist()

    def reverse(self):
        super().reverse()
        self._persist()

    def sort(self, *args, **kwargs):
        super().sort(*args, **kwargs)
        self._persist()


@dataclass(frozen=True, slots=True)
class DietViewState:
    """Single source of truth for the diet shell's mutually exclusive subview."""

    active_view: DietView = TODAY_DIET_VIEW

    @property
    def active_label(self) -> str:
        return DIET_VIEW_LABELS[self.active_view]

    def visibility(self) -> dict[DietView, bool]:
        return {view: view == self.active_view for view in DIET_VIEWS}

    def is_active(self, view: str) -> bool:
        return normalize_diet_view(view) == self.active_view


def normalize_diet_view(view: str | None) -> DietView:
    """Map legacy app-level routes to the new diet subview ids."""

    return LEGACY_DIET_VIEW_MAP.get(str(view or ""), TODAY_DIET_VIEW)


def select_diet_view(state: DietViewState | None, view: str | None) -> DietViewState:
    """Return a new state with exactly one active diet subview."""

    current = state or DietViewState()
    return replace(current, active_view=normalize_diet_view(view))


def diet_route_for_view(view: str | None) -> str:
    """Return the current app route expected by main.py until it is wired to the shell."""

    active = normalize_diet_view(view)
    if active == FOOD_LIBRARY_VIEW:
        return "foods"
    return "diet"


def recovery_owns_supplement_surfaces(surfaces: tuple[str, ...] = RECOVERY_SUPPLEMENT_SURFACES) -> bool:
    return tuple(surfaces) == RECOVERY_SUPPLEMENT_SURFACES


def recovery_exposes_only_today_supplements(surfaces: tuple[str, ...] = RECOVERY_SUPPLEMENT_SURFACES) -> bool:
    """Backward-compatible alias for the pre-consolidation contract."""
    return recovery_owns_supplement_surfaces(surfaces)


def me_page_allows_action(action_id: str) -> bool:
    """Keep supplement management out of the Me page contract."""

    return action_id not in ME_PAGE_BLOCKED_SUPPLEMENT_ACTIONS
