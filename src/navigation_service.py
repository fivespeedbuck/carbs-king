"""Pure bottom-navigation swipe rules."""

from __future__ import annotations


MAIN_NAV_VIEWS = ("today", "training", "diet", "data", "me")


def reset_transient_navigation_state(state: dict, current: str, target: str) -> None:
    """Close transient profile UI when leaving it without touching user data."""
    if current == "me" and target != "me":
        state["achievements_expanded"] = False
        state.pop("selected_achievement", None)

__all__ = [
    "MAIN_NAV_VIEWS",
    "reset_transient_navigation_state",
]
