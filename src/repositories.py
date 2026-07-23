"""Repository contracts and JSON-backed application repositories."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar

from app_defaults import DEFAULT_FOODS, DEFAULT_SUPPLEMENTS
from storage_service import (
    ACHIEVEMENT_FILE,
    FOOD_FILE,
    PROFILE_FILE,
    RECORD_FILE,
    SUPP_FILE,
    load_json,
    save_json,
)


T = TypeVar("T")


class Repository(Protocol[T]):
    def load(self) -> T: ...
    def save(self, value: T) -> None: ...


@dataclass(frozen=True)
class JsonRepository(Generic[T]):
    path: Path
    default_factory: Callable[[], T]
    normalize: Callable[[Any], T]

    def load(self) -> T:
        default = self.default_factory()
        return self.normalize(load_json(self.path, default))

    def save(self, value: T) -> None:
        save_json(self.path, value)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


@dataclass(frozen=True)
class AppRepositories:
    records: Repository[dict[str, Any]]
    foods: Repository[list[dict[str, Any]]]
    supplements: Repository[list[dict[str, Any]]]
    profile: Repository[dict[str, Any]]
    achievements: Repository[dict[str, Any]]


def build_default_repositories() -> AppRepositories:
    return AppRepositories(
        records=JsonRepository(RECORD_FILE, dict, _dict),
        foods=JsonRepository(FOOD_FILE, lambda: copy.deepcopy(DEFAULT_FOODS), _dict_list),
        supplements=JsonRepository(SUPP_FILE, lambda: copy.deepcopy(DEFAULT_SUPPLEMENTS), _dict_list),
        profile=JsonRepository(PROFILE_FILE, dict, _dict),
        achievements=JsonRepository(ACHIEVEMENT_FILE, dict, _dict),
    )


__all__ = ["AppRepositories", "JsonRepository", "Repository", "build_default_repositories"]
