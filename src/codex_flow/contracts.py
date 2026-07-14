"""Versioned JSON contracts shared by the later Codex Flow phases."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Mapping
from uuid import UUID

from .errors import FutureSchemaError

UTC = timezone.utc
SCHEMA_VERSION = 1
_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_THREAD_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)


def validate_run_id(run_id: str) -> str:
    """Validate and return a canonical UUIDv4 run ID.

    A strict canonical UUID shape keeps IDs safe to use as path components and
    as the only dynamic token passed across a future process boundary.
    """

    if not isinstance(run_id, str) or not _UUID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id must be a canonical UUIDv4 string")
    parsed = UUID(run_id)
    if parsed.version != 4:
        raise ValueError("run_id must be a UUIDv4 string")
    return str(parsed)


def _validate_thread_id(thread_id: str) -> str:
    if not isinstance(thread_id, str) or not _THREAD_ID_PATTERN.fullmatch(thread_id):
        raise ValueError("thread_id must be a canonical UUID string")
    return str(UUID(thread_id))


def utc_timestamp(value: datetime | None = None) -> str:
    """Return a UTC RFC 3339 timestamp ending in ``Z``."""

    current = datetime.now(UTC) if value is None else value
    if current.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return current.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _validate_timestamp(value: str) -> str:
    if not isinstance(value, str) or not _TIMESTAMP_PATTERN.fullmatch(value):
        raise ValueError("timestamps must be canonical UTC RFC 3339 strings ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("invalid UTC RFC 3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("timestamps must be UTC RFC 3339 strings")
    return value


def _absolute_path(value: str | Path) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def _nonempty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class RunIdentity:
    """A run ID and its optional repair lineage."""

    run_id: str
    parent_run_id: str | None = None
    root_run_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", validate_run_id(self.run_id))
        if self.parent_run_id is not None:
            object.__setattr__(self, "parent_run_id", validate_run_id(self.parent_run_id))
        if self.root_run_id is not None:
            object.__setattr__(self, "root_run_id", validate_run_id(self.root_run_id))


@dataclass(frozen=True)
class ThreadReference:
    """A root or execution thread reference without transcript content."""

    thread_id: str
    source_kind: str = "root"
    rollout_path: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _validate_thread_id(self.thread_id))
        if self.source_kind not in {"root", "subagent", "execution"}:
            raise ValueError("source_kind must be root, subagent, or execution")
        if self.rollout_path is not None:
            object.__setattr__(self, "rollout_path", _absolute_path(self.rollout_path))


@dataclass(frozen=True)
class RepositoryBaseline:
    """Repository and Git facts captured at handoff time."""

    working_directory: str
    repository_root: str | None = None
    branch: str | None = None
    head: str | None = None
    dirty: bool | None = None
    is_git_repository: bool = False
    original_working_directory: str | None = None
    baseline_fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "working_directory", _absolute_path(self.working_directory))
        if self.repository_root is not None:
            object.__setattr__(self, "repository_root", _absolute_path(self.repository_root))
        if self.original_working_directory is not None:
            _nonempty(self.original_working_directory, "original_working_directory")
        if not isinstance(self.is_git_repository, bool):
            raise ValueError("is_git_repository must be a boolean")
        if self.dirty is not None and not isinstance(self.dirty, bool):
            raise ValueError("dirty must be a boolean or null")
        if self.baseline_fingerprint is not None:
            if not isinstance(self.baseline_fingerprint, str) or not re.fullmatch(
                r"[0-9a-f]{64}", self.baseline_fingerprint
            ):
                raise ValueError("baseline_fingerprint must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True)
class HandoffSelection:
    """Context and model selection for an eventual handoff."""

    context_mode: str
    model: str
    reasoning_effort: str

    def __post_init__(self) -> None:
        _nonempty(self.context_mode, "context_mode")
        _nonempty(self.model, "model")
        _nonempty(self.reasoning_effort, "reasoning_effort")


@dataclass(frozen=True)
class ArtifactPaths:
    """Absolute paths for persisted handoff and review artifacts."""

    manifest: str
    plan: str | None = None
    handoff: str | None = None
    execution: str | None = None
    report: str | None = None
    audit: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "manifest",
            "plan",
            "handoff",
            "execution",
            "report",
            "audit",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _absolute_path(value))


@dataclass(frozen=True)
class RunManifest:
    """The immutable, versioned launch record foundation for later phases."""

    schema_version: int
    identity: RunIdentity
    source_thread: ThreadReference
    repository: RepositoryBaseline
    handoff: HandoffSelection
    artifacts: ArtifactPaths
    created_at: str

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise FutureSchemaError(f"unsupported schema version: {self.schema_version}")
        _validate_timestamp(self.created_at)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "RunManifest":
        return manifest_from_dict(document)

    @classmethod
    def from_json(cls, document: str) -> "RunManifest":
        return manifest_from_json(document)


def _object(document: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = document.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def manifest_from_dict(document: Mapping[str, Any]) -> RunManifest:
    """Decode a schema-v1 manifest and reject future schemas before guessing."""

    if not isinstance(document, Mapping):
        raise ValueError("manifest must be a JSON object")
    schema_version = document.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ValueError("schema_version must be an integer")
    if schema_version > SCHEMA_VERSION:
        raise FutureSchemaError(f"unsupported future schema version: {schema_version}")
    if schema_version < 1:
        raise ValueError(f"unsupported schema version: {schema_version}")
    allowed_fields = {
        "schema_version",
        "identity",
        "source_thread",
        "repository",
        "handoff",
        "artifacts",
        "created_at",
    }
    unexpected_fields = set(document) - allowed_fields
    if unexpected_fields:
        names = ", ".join(sorted(unexpected_fields))
        raise ValueError(f"manifest contains unsupported fields: {names}")
    return RunManifest(
        schema_version=schema_version,
        identity=RunIdentity(**dict(_object(document, "identity"))),
        source_thread=ThreadReference(**dict(_object(document, "source_thread"))),
        repository=RepositoryBaseline(**dict(_object(document, "repository"))),
        handoff=HandoffSelection(**dict(_object(document, "handoff"))),
        artifacts=ArtifactPaths(**dict(_object(document, "artifacts"))),
        created_at=document.get("created_at"),
    )


def manifest_from_json(document: str) -> RunManifest:
    try:
        decoded = json.loads(document)
    except json.JSONDecodeError as error:
        raise ValueError("manifest is not valid JSON") from error
    return manifest_from_dict(decoded)
