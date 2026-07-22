"""JSON-compatible domain models for strength training."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping
from uuid import uuid4


TRAINING_SCHEMA_VERSION = 1


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _text(value: Any, default: str = "") -> str:
    return default if value is None else str(value)


def _float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _float(value)
    return None if number is None else int(number)


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False
    if value is None:
        return default
    return bool(value)


@dataclass(slots=True)
class Exercise:
    name: str
    body_part: str
    id: str = field(default_factory=lambda: new_id("exercise"))
    kind: str = "strength"
    equipment: str = ""
    target_muscles: list[str] = field(default_factory=list)
    cues: list[str] = field(default_factory=list)
    mistakes: list[str] = field(default_factory=list)
    default_weight_kg: float | None = None
    default_reps: int = 10
    default_sets: int = 4
    favorite: bool = False
    archived: bool = False
    notes: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Exercise:
        return cls(
            id=_text(data.get("id")) or new_id("exercise"),
            name=_text(data.get("name")),
            body_part=_text(data.get("body_part")),
            kind=_text(data.get("kind"), "strength") or "strength",
            equipment=_text(data.get("equipment")),
            target_muscles=[_text(item) for item in data.get("target_muscles", []) if _text(item)] if isinstance(data.get("target_muscles", []), list) else [],
            cues=[_text(item) for item in data.get("cues", []) if _text(item)] if isinstance(data.get("cues", []), list) else [],
            mistakes=[_text(item) for item in data.get("mistakes", []) if _text(item)] if isinstance(data.get("mistakes", []), list) else [],
            default_weight_kg=_float(data.get("default_weight_kg")),
            default_reps=_int(data.get("default_reps")) or 10,
            default_sets=_int(data.get("default_sets")) or 4,
            favorite=_bool(data.get("favorite")),
            archived=_bool(data.get("archived")),
            notes=_text(data.get("notes")),
            created_at=_text(data.get("created_at")),
        )


@dataclass(slots=True)
class SetPlan:
    order: int
    target_reps: int | None = None
    target_weight_kg: float | None = None
    warmup: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], order: int = 1) -> SetPlan:
        return cls(
            order=_int(data.get("order")) or order,
            target_reps=_int(data.get("target_reps", data.get("reps"))),
            target_weight_kg=_float(data.get("target_weight_kg", data.get("weight_kg"))),
            warmup=_bool(data.get("warmup")),
            note=_text(data.get("note")),
        )


@dataclass(slots=True)
class TemplateExercise:
    exercise_id: str
    name: str
    body_part: str
    order: int
    sets: list[SetPlan] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], order: int = 1) -> TemplateExercise:
        raw_sets = data.get("sets", [])
        if not isinstance(raw_sets, list):
            raw_sets = []
        return cls(
            exercise_id=_text(data.get("exercise_id")),
            name=_text(data.get("name")),
            body_part=_text(data.get("body_part")),
            order=_int(data.get("order")) or order,
            sets=[SetPlan.from_dict(item, index) for index, item in enumerate(raw_sets, 1) if isinstance(item, Mapping)],
            note=_text(data.get("note")),
        )


@dataclass(slots=True)
class TrainingTemplate:
    name: str
    id: str = field(default_factory=lambda: new_id("template"))
    exercises: list[TemplateExercise] = field(default_factory=list)
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrainingTemplate:
        raw_exercises = data.get("exercises", [])
        if not isinstance(raw_exercises, list):
            raw_exercises = []
        return cls(
            id=_text(data.get("id")) or new_id("template"),
            name=_text(data.get("name")),
            exercises=[
                TemplateExercise.from_dict(item, index)
                for index, item in enumerate(raw_exercises, 1)
                if isinstance(item, Mapping)
            ],
            notes=_text(data.get("notes")),
            created_at=_text(data.get("created_at")),
            updated_at=_text(data.get("updated_at")),
        )


@dataclass(slots=True)
class TrainingSet:
    order: int
    id: str = field(default_factory=lambda: new_id("set"))
    weight_kg: float | None = None
    reps: int | None = None
    completed: bool = False
    warmup: bool = False
    rir: float | None = None
    rpe: float | None = None
    note: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], order: int = 1) -> TrainingSet:
        return cls(
            id=_text(data.get("id")) or new_id("set"),
            order=_int(data.get("order")) or order,
            weight_kg=_float(data.get("weight_kg", data.get("weight"))),
            reps=_int(data.get("reps")),
            completed=_bool(data.get("completed")),
            warmup=_bool(data.get("warmup", data.get("is_warmup"))),
            rir=_float(data.get("rir")),
            rpe=_float(data.get("rpe")),
            note=_text(data.get("note")),
            completed_at=_text(data.get("completed_at")),
        )


@dataclass(slots=True)
class SessionExercise:
    name: str
    body_part: str
    order: int
    id: str = field(default_factory=lambda: new_id("session_exercise"))
    exercise_id: str = ""
    sets: list[TrainingSet] = field(default_factory=list)
    note: str = ""
    legacy_detail: str = ""
    legacy_intensity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], order: int = 1) -> SessionExercise:
        raw_sets = data.get("sets", [])
        if not isinstance(raw_sets, list):
            raw_sets = []
        return cls(
            id=_text(data.get("id")) or new_id("session_exercise"),
            exercise_id=_text(data.get("exercise_id")),
            name=_text(data.get("name")),
            body_part=_text(data.get("body_part")),
            order=_int(data.get("order")) or order,
            sets=[TrainingSet.from_dict(item, index) for index, item in enumerate(raw_sets, 1) if isinstance(item, Mapping)],
            note=_text(data.get("note")),
            legacy_detail=_text(data.get("legacy_detail")),
            legacy_intensity=_text(data.get("legacy_intensity")),
        )


@dataclass(slots=True)
class TrainingSession:
    date: str
    id: str = field(default_factory=lambda: new_id("session"))
    status: str = "planned"
    started_at: str = ""
    ended_at: str = ""
    total_duration_min: float | None = None
    exercises: list[SessionExercise] = field(default_factory=list)
    summary_note: str = ""
    fatigue_status: str = ""
    legacy_calories_kcal: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrainingSession:
        raw_exercises = data.get("exercises", [])
        if not isinstance(raw_exercises, list):
            raw_exercises = []
        return cls(
            id=_text(data.get("id")) or new_id("session"),
            date=_text(data.get("date")),
            status=_text(data.get("status"), "planned") or "planned",
            started_at=_text(data.get("started_at")),
            ended_at=_text(data.get("ended_at")),
            total_duration_min=_float(data.get("total_duration_min")),
            exercises=[
                SessionExercise.from_dict(item, index)
                for index, item in enumerate(raw_exercises, 1)
                if isinstance(item, Mapping)
            ],
            summary_note=_text(data.get("summary_note")),
            fatigue_status=_text(data.get("fatigue_status")),
            legacy_calories_kcal=_float(data.get("legacy_calories_kcal", data.get("total_calories_kcal"))),
        )


@dataclass(slots=True)
class TrainingData:
    schema_version: int = TRAINING_SCHEMA_VERSION
    exercises: list[Exercise] = field(default_factory=list)
    templates: list[TrainingTemplate] = field(default_factory=list)
    sessions: list[TrainingSession] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrainingData:
        raw_exercises = data.get("exercises", [])
        raw_templates = data.get("templates", [])
        raw_sessions = data.get("sessions", [])
        return cls(
            schema_version=_int(data.get("schema_version")) or TRAINING_SCHEMA_VERSION,
            exercises=[Exercise.from_dict(item) for item in raw_exercises if isinstance(item, Mapping)]
            if isinstance(raw_exercises, list) else [],
            templates=[TrainingTemplate.from_dict(item) for item in raw_templates if isinstance(item, Mapping)]
            if isinstance(raw_templates, list) else [],
            sessions=[TrainingSession.from_dict(item) for item in raw_sessions if isinstance(item, Mapping)]
            if isinstance(raw_sessions, list) else [],
        )
