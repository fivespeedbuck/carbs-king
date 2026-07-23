"""Application-level dependency container owned by the app shell."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app_state import AppState
from repositories import AppRepositories


@dataclass
class AppContext:
    page: Any
    state: AppState
    repositories: AppRepositories
    rest_notifier: Any
    training_clock_refs: dict[str, Any] = field(
        default_factory=lambda: {"elapsed": None, "rest": None, "dashboard": None}
    )
    exercise_drag_state: dict[str, Any] = field(
        default_factory=lambda: {"id": None, "active": False}
    )


__all__ = ["AppContext"]
