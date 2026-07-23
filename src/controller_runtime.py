"""Small UI intent surface shared by feature controllers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ControllerRuntime:
    page: Any
    refresh: Callable[[], None]
    snack: Callable[..., None]
    navigate: Callable[[str], None]
    open_control: Callable[[Any], None]
    close_control: Callable[[Any], None]
    responsive_width: Callable[..., int]
    responsive_bar_width: Callable[[], int]


__all__ = ["ControllerRuntime"]
