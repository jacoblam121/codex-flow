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
EXECUTION_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
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
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


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


def _strict_fields(
    document: Mapping[str, Any], required: set[str], name: str
) -> None:
    missing = required - set(document)
    unexpected = set(document) - required
    if missing:
        raise ValueError(f"{name} is missing required fields: {', '.join(sorted(missing))}")
    if unexpected:
        raise ValueError(f"{name} contains unsupported fields: {', '.join(sorted(unexpected))}")


def _line_number(value: Any, field_name: str, *, nullable: bool = False) -> int | None:
    if nullable and value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        suffix = " or null" if nullable else ""
        raise ValueError(f"{field_name} must be a positive integer{suffix}")
    return value


def _string_array(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    result: list[str] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, str) or not entry:
            raise ValueError(f"{field_name}[{index}] must be a non-empty string")
        result.append(entry)
    return tuple(result)


def validate_sha256(value: str, field_name: str = "sha256") -> str:
    """Validate a required lowercase SHA-256 hexadecimal digest."""

    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
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
        if self.context_mode not in {"plan", "fork"}:
            raise ValueError("context_mode must be plan or fork")
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

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True)
class RunManifest:
    """The immutable, versioned launch record foundation for later phases."""

    schema_version: int
    identity: RunIdentity
    source_thread: ThreadReference
    repository: RepositoryBaseline
    handoff: HandoffSelection
    codex_executable: str
    plan_sha256: str
    artifacts: ArtifactPaths
    created_at: str

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise FutureSchemaError(f"unsupported schema version: {self.schema_version}")
        _validate_timestamp(self.created_at)
        if not isinstance(self.codex_executable, str) or not self.codex_executable:
            raise ValueError("codex_executable must be a non-empty absolute path")
        codex_path = Path(self.codex_executable).expanduser()
        canonical_codex_path = str(codex_path.resolve(strict=False))
        if not codex_path.is_absolute() or self.codex_executable != canonical_codex_path:
            raise ValueError("codex_executable must be a canonical absolute path")
        validate_sha256(self.plan_sha256, "plan_sha256")

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


@dataclass(frozen=True)
class ReportValidation:
    """One command/result entry in a schema-v1 execution report."""

    command: str
    exit_code: int | None
    outcome: str

    def __post_init__(self) -> None:
        _nonempty(self.command, "validation.command")
        if self.exit_code is not None and (
            not isinstance(self.exit_code, int) or isinstance(self.exit_code, bool)
        ):
            raise ValueError("validation.exit_code must be an integer or null")
        _nonempty(self.outcome, "validation.outcome")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReportPayload:
    """Strict, versioned payload carried by a Codex Flow report envelope."""

    schema_version: int
    status: str
    summary: str
    files_changed: tuple[str, ...]
    validation: tuple[ReportValidation, ...]
    deviations: tuple[str, ...]
    unresolved_issues: tuple[str, ...]
    recommended_follow_up: tuple[str, ...]

    CURRENT_SCHEMA_VERSION: ClassVar[int] = REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            raise ValueError("report schema_version must be an integer")
        if self.schema_version > REPORT_SCHEMA_VERSION:
            raise FutureSchemaError(
                f"unsupported future report schema version: {self.schema_version}"
            )
        if self.schema_version != REPORT_SCHEMA_VERSION:
            raise ValueError(f"unsupported report schema version: {self.schema_version}")
        if self.status not in {"completed", "partial", "blocked"}:
            raise ValueError("report status must be completed, partial, or blocked")
        _nonempty(self.summary, "report summary")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "summary": self.summary,
            "files_changed": list(self.files_changed),
            "validation": [entry.to_dict() for entry in self.validation],
            "deviations": list(self.deviations),
            "unresolved_issues": list(self.unresolved_issues),
            "recommended_follow_up": list(self.recommended_follow_up),
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "ReportPayload":
        return report_payload_from_dict(document)


@dataclass(frozen=True)
class AssistantResultPointer:
    """Stable pointer to one canonical assistant final in a rollout."""

    line_number: int
    content_index: int
    sha256: str

    def __post_init__(self) -> None:
        _line_number(self.line_number, "assistant_result.line_number")
        if (
            not isinstance(self.content_index, int)
            or isinstance(self.content_index, bool)
            or self.content_index < 0
        ):
            raise ValueError("assistant_result.content_index must be a non-negative integer")
        validate_sha256(self.sha256, "assistant_result.sha256")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionSidecar:
    """Schema-v1 cache of live execution-rollout association evidence."""

    schema_version: int
    run_id: str
    execution_thread_id: str
    rollout_path: str
    session_meta_line: int
    session_timestamp: str
    forked_from_id: str | None
    marker_turn_id: str
    marker_line: int
    marker_timestamp: str
    task_started_line: int
    turn_context_line: int
    segment_start_line: int
    segment_end_before_line: int | None
    observed_end_line: int
    latest_assistant_result: AssistantResultPointer | None

    CURRENT_SCHEMA_VERSION: ClassVar[int] = EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != EXECUTION_SCHEMA_VERSION
        ):
            if isinstance(self.schema_version, int) and self.schema_version > EXECUTION_SCHEMA_VERSION:
                raise FutureSchemaError(
                    f"unsupported future execution schema version: {self.schema_version}"
                )
            raise ValueError(f"unsupported execution schema version: {self.schema_version}")
        object.__setattr__(self, "run_id", validate_run_id(self.run_id))
        object.__setattr__(self, "execution_thread_id", _validate_thread_id(self.execution_thread_id))
        rollout = Path(self.rollout_path).expanduser()
        canonical_rollout = str(rollout.resolve(strict=False))
        if not rollout.is_absolute() or self.rollout_path != canonical_rollout:
            raise ValueError("rollout_path must be a canonical absolute path")
        for field_name in (
            "session_meta_line",
            "marker_line",
            "task_started_line",
            "turn_context_line",
            "segment_start_line",
            "observed_end_line",
        ):
            _line_number(getattr(self, field_name), field_name)
        _line_number(self.segment_end_before_line, "segment_end_before_line", nullable=True)
        _validate_timestamp(self.session_timestamp)
        _validate_timestamp(self.marker_timestamp)
        if self.forked_from_id is not None:
            object.__setattr__(self, "forked_from_id", _validate_thread_id(self.forked_from_id))
        object.__setattr__(self, "marker_turn_id", _validate_thread_id(self.marker_turn_id))
        if self.segment_start_line != self.marker_line:
            raise ValueError("segment_start_line must equal marker_line")
        if self.segment_end_before_line is not None and self.segment_end_before_line <= self.marker_line:
            raise ValueError("segment_end_before_line must follow marker_line")
        if self.observed_end_line < self.marker_line:
            raise ValueError("observed_end_line must not precede marker_line")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return result

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "ExecutionSidecar":
        return execution_sidecar_from_dict(document)


@dataclass(frozen=True)
class ReportSidecar:
    """Schema-v1 cache of a validated report and exact rollout provenance."""

    schema_version: int
    run_id: str
    execution_thread_id: str
    rollout_path: str
    assistant_result: AssistantResultPointer
    envelope_index: int
    envelope_sha256: str
    report: ReportPayload

    CURRENT_SCHEMA_VERSION: ClassVar[int] = REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != REPORT_SCHEMA_VERSION
        ):
            if isinstance(self.schema_version, int) and self.schema_version > REPORT_SCHEMA_VERSION:
                raise FutureSchemaError(
                    f"unsupported future report sidecar schema version: {self.schema_version}"
                )
            raise ValueError(f"unsupported report sidecar schema version: {self.schema_version}")
        object.__setattr__(self, "run_id", validate_run_id(self.run_id))
        object.__setattr__(self, "execution_thread_id", _validate_thread_id(self.execution_thread_id))
        rollout = Path(self.rollout_path).expanduser()
        canonical_rollout = str(rollout.resolve(strict=False))
        if not rollout.is_absolute() or self.rollout_path != canonical_rollout:
            raise ValueError("rollout_path must be a canonical absolute path")
        if (
            not isinstance(self.envelope_index, int)
            or isinstance(self.envelope_index, bool)
            or self.envelope_index < 0
        ):
            raise ValueError("envelope_index must be a non-negative integer")
        validate_sha256(self.envelope_sha256, "envelope_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "execution_thread_id": self.execution_thread_id,
            "rollout_path": self.rollout_path,
            "assistant_result": self.assistant_result.to_dict(),
            "envelope_index": self.envelope_index,
            "envelope_sha256": self.envelope_sha256,
            "report": self.report.to_dict(),
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "ReportSidecar":
        return report_sidecar_from_dict(document)


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
        "codex_executable",
        "plan_sha256",
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
        codex_executable=document.get("codex_executable"),
        plan_sha256=document.get("plan_sha256"),
        artifacts=ArtifactPaths(**dict(_object(document, "artifacts"))),
        created_at=document.get("created_at"),
    )


def manifest_from_json(document: str) -> RunManifest:
    try:
        decoded = json.loads(document)
    except json.JSONDecodeError as error:
        raise ValueError("manifest is not valid JSON") from error
    return manifest_from_dict(decoded)


def report_payload_from_dict(document: Mapping[str, Any]) -> ReportPayload:
    """Validate the exact schema-v1 execution report payload."""

    if not isinstance(document, Mapping):
        raise ValueError("report payload must be a JSON object")
    required = {
        "schema_version",
        "status",
        "summary",
        "files_changed",
        "validation",
        "deviations",
        "unresolved_issues",
        "recommended_follow_up",
    }
    _strict_fields(document, required, "report payload")
    schema_version = document["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ValueError("report schema_version must be an integer")
    if schema_version > REPORT_SCHEMA_VERSION:
        raise FutureSchemaError(
            f"unsupported future report schema version: {schema_version}"
        )
    raw_validation = document["validation"]
    if not isinstance(raw_validation, list):
        raise ValueError("validation must be an array")
    validation: list[ReportValidation] = []
    validation_fields = {"command", "exit_code", "outcome"}
    for index, entry in enumerate(raw_validation):
        if not isinstance(entry, Mapping):
            raise ValueError(f"validation[{index}] must be an object")
        _strict_fields(entry, validation_fields, f"validation[{index}]")
        validation.append(
            ReportValidation(
                command=entry["command"],
                exit_code=entry["exit_code"],
                outcome=entry["outcome"],
            )
        )
    return ReportPayload(
        schema_version=schema_version,
        status=document["status"],
        summary=document["summary"],
        files_changed=_string_array(document["files_changed"], "files_changed"),
        validation=tuple(validation),
        deviations=_string_array(document["deviations"], "deviations"),
        unresolved_issues=_string_array(document["unresolved_issues"], "unresolved_issues"),
        recommended_follow_up=_string_array(
            document["recommended_follow_up"], "recommended_follow_up"
        ),
    )


def _assistant_pointer_from_dict(
    document: Mapping[str, Any], name: str = "assistant_result"
) -> AssistantResultPointer:
    if not isinstance(document, Mapping):
        raise ValueError(f"{name} must be an object")
    _strict_fields(document, {"line_number", "content_index", "sha256"}, name)
    return AssistantResultPointer(
        line_number=document["line_number"],
        content_index=document["content_index"],
        sha256=document["sha256"],
    )


def execution_sidecar_from_dict(document: Mapping[str, Any]) -> ExecutionSidecar:
    """Strictly decode an execution association cache."""

    if not isinstance(document, Mapping):
        raise ValueError("execution sidecar must be a JSON object")
    fields = {
        "schema_version",
        "run_id",
        "execution_thread_id",
        "rollout_path",
        "session_meta_line",
        "session_timestamp",
        "forked_from_id",
        "marker_turn_id",
        "marker_line",
        "marker_timestamp",
        "task_started_line",
        "turn_context_line",
        "segment_start_line",
        "segment_end_before_line",
        "observed_end_line",
        "latest_assistant_result",
    }
    _strict_fields(document, fields, "execution sidecar")
    raw_pointer = document["latest_assistant_result"]
    pointer = (
        None
        if raw_pointer is None
        else _assistant_pointer_from_dict(raw_pointer, "latest_assistant_result")
    )
    return ExecutionSidecar(
        schema_version=document["schema_version"],
        run_id=document["run_id"],
        execution_thread_id=document["execution_thread_id"],
        rollout_path=document["rollout_path"],
        session_meta_line=document["session_meta_line"],
        session_timestamp=document["session_timestamp"],
        forked_from_id=document["forked_from_id"],
        marker_turn_id=document["marker_turn_id"],
        marker_line=document["marker_line"],
        marker_timestamp=document["marker_timestamp"],
        task_started_line=document["task_started_line"],
        turn_context_line=document["turn_context_line"],
        segment_start_line=document["segment_start_line"],
        segment_end_before_line=document["segment_end_before_line"],
        observed_end_line=document["observed_end_line"],
        latest_assistant_result=pointer,
    )


def report_sidecar_from_dict(document: Mapping[str, Any]) -> ReportSidecar:
    """Strictly decode a validated report cache with provenance."""

    if not isinstance(document, Mapping):
        raise ValueError("report sidecar must be a JSON object")
    fields = {
        "schema_version",
        "run_id",
        "execution_thread_id",
        "rollout_path",
        "assistant_result",
        "envelope_index",
        "envelope_sha256",
        "report",
    }
    _strict_fields(document, fields, "report sidecar")
    return ReportSidecar(
        schema_version=document["schema_version"],
        run_id=document["run_id"],
        execution_thread_id=document["execution_thread_id"],
        rollout_path=document["rollout_path"],
        assistant_result=_assistant_pointer_from_dict(document["assistant_result"]),
        envelope_index=document["envelope_index"],
        envelope_sha256=document["envelope_sha256"],
        report=report_payload_from_dict(document["report"]),
    )
