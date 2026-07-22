"""Pure presentation helpers for achievement results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


HIDDEN_LOCKED_TITLE = "隐藏成就"
HIDDEN_LOCKED_DESCRIPTION = "达成条件后揭晓"


def achievement_view_model(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a UI-safe achievement payload, masking locked hidden entries."""
    item = dict(result)
    locked_hidden = bool(item.get("hidden")) and not bool(item.get("unlocked"))
    item["revealed"] = not locked_hidden
    if locked_hidden:
        item["title"] = HIDDEN_LOCKED_TITLE
        item["description"] = HIDDEN_LOCKED_DESCRIPTION
    return item


def achievement_view_models(results: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
    return [achievement_view_model(item) for item in results]


__all__ = [
    "HIDDEN_LOCKED_DESCRIPTION",
    "HIDDEN_LOCKED_TITLE",
    "achievement_view_model",
    "achievement_view_models",
]
