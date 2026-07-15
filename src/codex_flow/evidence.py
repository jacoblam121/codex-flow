"""Exact, line-ordered execution rollout and report evidence recovery."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import (
    AssistantResultPointer,
    ExecutionSidecar,
    ReportPayload,
    ReportSidecar,
    RunManifest,
    report_payload_from_dict,
    validate_run_id,
)
from .errors import ContractError
from .rollouts import JsonlReader, JsonlRecord, validate_thread_id

_ROLLOUT_NAME_RE = re.compile(
    r"(?:^|[-_])(?P<thread>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.jsonl$"
)
_RUN_MARKER_RE = re.compile(
    r'^<codex_flow_run run_id="(?P<run_id>[0-9a-f]{8}-[0-9a-f]{4}-'
    r'[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})" version="1" />$'
)
_REPORT_OPEN_RE = re.compile(
    r'<codex_flow_report run_id="(?P<run_id>[0-9a-f]{8}-[0-9a-f]{4}-'
    r'[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})">'
)
_REPORT_OPEN_PREFIX = "<codex_flow_report"
_REPORT_CLOSE = "</codex_flow_report>"


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _canonical_timestamp(value: Any) -> str | None:
    parsed = _timestamp(value)
    if parsed is None or not isinstance(value, str):
        return None
    # Sidecar contracts accept microseconds or fewer and all characterized
    # rollout timestamps use that range.
    fractional = value.removesuffix("Z").partition(".")[2]
    if fractional and len(fractional) > 6:
        return None
    return value


def _rollout_thread(path: Path) -> str | None:
    match = _ROLLOUT_NAME_RE.search(path.name)
    if match is None or not path.name.startswith("rollout-"):
        return None
    try:
        return validate_thread_id(match.group("thread"))
    except (TypeError, ValueError):
        return None


def discover_execution_rollouts(codex_home: str | Path) -> tuple[Path, ...]:
    """Return all canonical rollout filenames without selecting by recency."""

    sessions = Path(codex_home).expanduser().resolve(strict=False) / "sessions"
    if not sessions.is_dir():
        return ()
    candidates: list[Path] = []
    try:
        for path in sessions.rglob("*.jsonl"):
            if path.is_symlink() or not path.is_file() or _rollout_thread(path) is None:
                continue
            candidates.append(path.resolve(strict=False))
    except OSError:
        return ()
    return tuple(sorted(candidates))


@dataclass(frozen=True)
class CanonicalAssistantResult:
    line_number: int
    content_index: int
    text: str

    @property
    def pointer(self) -> AssistantResultPointer:
        return AssistantResultPointer(
            line_number=self.line_number,
            content_index=self.content_index,
            sha256=_sha256(self.text),
        )

    def to_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        result = self.pointer.to_dict()
        if include_text:
            result["text"] = self.text
        return result


@dataclass(frozen=True)
class RecoveredReport:
    payload: ReportPayload
    sidecar: ReportSidecar


@dataclass(frozen=True)
class AssociatedExecution:
    execution: ExecutionSidecar
    latest_assistant_result: CanonicalAssistantResult | None
    report: RecoveredReport | None
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class AssociationResult:
    association: AssociatedExecution | None
    ambiguous: bool
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class _Marker:
    run_id: str
    line_number: int
    timestamp: str
    turn_id: str
    task_started_line: int
    turn_context_line: int


@dataclass(frozen=True)
class _RolloutCandidate:
    path: Path
    thread_id: str
    session_timestamp: str
    forked_from_id: str | None
    marker: _Marker
    segment_end_before_line: int | None
    observed_end_line: int
    records: tuple[JsonlRecord, ...]
    diagnostics: tuple[str, ...]


def _canonical_user_marker(record: JsonlRecord) -> tuple[str, str] | None:
    value = _mapping(record.value)
    payload = _mapping(value.get("payload")) if value else None
    if (
        value is None
        or value.get("type") != "response_item"
        or payload is None
        or payload.get("type") != "message"
        or payload.get("role") != "user"
    ):
        return None
    content = payload.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return None
    part = _mapping(content[0])
    if (
        part is None
        or part.get("type") != "input_text"
        or not isinstance(part.get("text"), str)
    ):
        return None
    first_line = part["text"].splitlines()[0] if part["text"].splitlines() else ""
    match = _RUN_MARKER_RE.fullmatch(first_line)
    if match is None:
        return None
    try:
        run_id = validate_run_id(match.group("run_id"))
    except (TypeError, ValueError):
        return None
    metadata = _mapping(payload.get("internal_chat_message_metadata_passthrough"))
    turn_id = metadata.get("turn_id") if metadata else None
    if not isinstance(turn_id, str):
        return None
    try:
        return run_id, validate_thread_id(turn_id)
    except (TypeError, ValueError):
        return None


def _task_started(record: JsonlRecord) -> tuple[str, str | None] | None:
    value = _mapping(record.value)
    payload = _mapping(value.get("payload")) if value else None
    if value is None or value.get("type") != "event_msg" or payload is None:
        return None
    if payload.get("type") != "task_started" or not isinstance(payload.get("turn_id"), str):
        return None
    try:
        turn_id = validate_thread_id(payload["turn_id"])
    except (TypeError, ValueError):
        return None
    mode = payload.get("collaboration_mode_kind")
    return turn_id, mode if isinstance(mode, str) else None


def _turn_context(record: JsonlRecord) -> tuple[str, Mapping[str, Any]] | None:
    value = _mapping(record.value)
    payload = _mapping(value.get("payload")) if value else None
    if value is None or value.get("type") != "turn_context" or payload is None:
        return None
    if not isinstance(payload.get("turn_id"), str):
        return None
    try:
        return validate_thread_id(payload["turn_id"]), payload
    except (TypeError, ValueError):
        return None


def _paired_marker(
    marker_record: JsonlRecord,
    marker_run_id: str,
    marker_turn_id: str,
    records: tuple[JsonlRecord, ...],
    manifest: RunManifest,
) -> tuple[_Marker | None, str | None]:
    prior = [record for record in records if record.line_number < marker_record.line_number]
    tasks = [
        (record, task)
        for record in prior
        if (task := _task_started(record)) is not None
    ]
    if not tasks:
        return None, f"rollout line {marker_record.line_number}: marker has no matching task_started"
    task_record, task = tasks[-1]
    if task[0] != marker_turn_id:
        return None, f"rollout line {marker_record.line_number}: marker and task_started turn IDs differ"
    contexts = [
        (record, context)
        for record in prior
        if record.line_number > task_record.line_number
        and (context := _turn_context(record)) is not None
    ]
    if not contexts:
        return None, f"rollout line {marker_record.line_number}: marker has no matching turn_context"
    context_record, (context_turn_id, context) = contexts[-1]
    if context_turn_id != marker_turn_id:
        return None, f"rollout line {marker_record.line_number}: marker and turn_context turn IDs differ"
    collaboration = _mapping(context.get("collaboration_mode"))
    if task[1] != "default" or collaboration is None or collaboration.get("mode") != "default":
        return None, f"rollout line {marker_record.line_number}: marker task is not in Default mode"
    if context.get("cwd") != manifest.repository.working_directory:
        return None, f"rollout line {marker_record.line_number}: turn_context CWD does not match the manifest"
    recorded_model = context.get("model")
    if recorded_model is not None and recorded_model != manifest.handoff.model:
        return None, f"rollout line {marker_record.line_number}: turn_context model does not match the manifest"
    raw = _mapping(marker_record.value)
    marker_timestamp = _canonical_timestamp(raw.get("timestamp") if raw else None)
    if marker_timestamp is None:
        return None, f"rollout line {marker_record.line_number}: marker timestamp is missing or malformed"
    return (
        _Marker(
            run_id=marker_run_id,
            line_number=marker_record.line_number,
            timestamp=marker_timestamp,
            turn_id=marker_turn_id,
            task_started_line=task_record.line_number,
            turn_context_line=context_record.line_number,
        ),
        None,
    )


def _candidate_for_rollout(
    path: Path, manifest: RunManifest
) -> tuple[_RolloutCandidate | None, tuple[str, ...]]:
    diagnostics: list[str] = []
    thread_id = _rollout_thread(path)
    if thread_id is None:
        return None, ()
    reader = JsonlReader(path)
    records = tuple(reader)
    canonical_markers = [
        (record, marker[0], marker[1])
        for record in records
        if (marker := _canonical_user_marker(record)) is not None
    ]
    if not any(run_id == manifest.identity.run_id for _, run_id, _ in canonical_markers):
        return None, ()
    if reader.malformed_line_numbers:
        return None, tuple(reader.warnings)
    if not records or records[0].line_number != 1:
        return None, (f"rollout {path}: first JSONL line is missing or malformed",)
    first = _mapping(records[0].value)
    payload = _mapping(first.get("payload")) if first else None
    if first is None or first.get("type") != "session_meta" or payload is None:
        return None, (f"rollout {path}: first record is not session_meta",)
    if payload.get("id") != thread_id or payload.get("session_id") != thread_id:
        return None, (f"rollout {path}: current session_meta does not match the filename thread",)
    if payload.get("thread_source") not in {"user", "root"}:
        return None, (f"rollout {path}: current session owner is not a root interactive thread",)
    if payload.get("cwd") != manifest.repository.working_directory:
        return None, (f"rollout {path}: current session CWD does not match the manifest",)
    recorded_model = payload.get("model")
    if recorded_model is not None and recorded_model != manifest.handoff.model:
        return None, (f"rollout {path}: current session model does not match the manifest",)
    raw_fork = payload.get("forked_from_id")
    if raw_fork is not None:
        try:
            forked_from_id = validate_thread_id(raw_fork)
        except (TypeError, ValueError):
            return None, (f"rollout {path}: current fork origin is malformed",)
    else:
        forked_from_id = None
    if manifest.handoff.context_mode == "plan" and forked_from_id is not None:
        return None, (f"rollout {path}: plan execution unexpectedly has a fork origin",)
    if manifest.handoff.context_mode == "fork" and forked_from_id != manifest.source_thread.thread_id:
        return None, (f"rollout {path}: fork origin does not match the manifest source thread",)
    session_timestamp = _canonical_timestamp(first.get("timestamp"))
    launch_time = _timestamp(manifest.created_at)
    session_time = _timestamp(session_timestamp)
    if session_timestamp is None or launch_time is None or session_time is None:
        return None, (f"rollout {path}: launch or current session timestamp is malformed",)
    if session_time < launch_time:
        return None, (f"rollout {path}: current session predates launch",)

    qualifying: list[_Marker] = []
    for record, run_id, turn_id in canonical_markers:
        if run_id != manifest.identity.run_id:
            continue
        paired, error = _paired_marker(record, run_id, turn_id, records, manifest)
        if error is not None:
            diagnostics.append(error)
            continue
        assert paired is not None
        marker_time = _timestamp(paired.timestamp)
        if marker_time is None or marker_time < session_time:
            diagnostics.append(
                f"rollout line {record.line_number}: marker timestamp predates the current session"
            )
            continue
        qualifying.append(paired)
    if not qualifying:
        return None, tuple(diagnostics)
    if len(qualifying) > 1:
        diagnostics.append(f"rollout {path}: multiple qualifying markers make association ambiguous")
        return None, tuple(diagnostics)
    marker = qualifying[0]

    boundary: int | None = None
    for record, _, turn_id in canonical_markers:
        if record.line_number <= marker.line_number:
            continue
        tasks = [
            (prior, task)
            for prior in records
            if prior.line_number < record.line_number
            and (task := _task_started(prior)) is not None
        ]
        if tasks and tasks[-1][1][0] == turn_id:
            candidate_boundary = tasks[-1][0].line_number
            if candidate_boundary <= marker.line_number:
                diagnostics.append(
                    f"rollout line {record.line_number}: next run marker shares the current task"
                )
                return None, tuple(diagnostics)
            boundary = candidate_boundary
            break
    return (
        _RolloutCandidate(
            path=path,
            thread_id=thread_id,
            session_timestamp=session_timestamp,
            forked_from_id=forked_from_id,
            marker=marker,
            segment_end_before_line=boundary,
            observed_end_line=records[-1].line_number,
            records=records,
            diagnostics=tuple(diagnostics),
        ),
        tuple(diagnostics),
    )


def _assistant_results(candidate: _RolloutCandidate) -> tuple[CanonicalAssistantResult, ...]:
    results: list[CanonicalAssistantResult] = []
    for record in candidate.records:
        if record.line_number < candidate.marker.line_number:
            continue
        if (
            candidate.segment_end_before_line is not None
            and record.line_number >= candidate.segment_end_before_line
        ):
            continue
        value = _mapping(record.value)
        payload = _mapping(value.get("payload")) if value else None
        if (
            value is None
            or value.get("type") != "response_item"
            or payload is None
            or payload.get("type") != "message"
            or payload.get("role") != "assistant"
            or payload.get("phase") != "final_answer"
        ):
            continue
        content = payload.get("content")
        if not isinstance(content, list) or len(content) != 1:
            continue
        part = _mapping(content[0])
        if (
            part is None
            or part.get("type") != "output_text"
            or not isinstance(part.get("text"), str)
        ):
            continue
        results.append(CanonicalAssistantResult(record.line_number, 0, part["text"]))
    return tuple(results)


def _recover_report(
    manifest: RunManifest,
    candidate: _RolloutCandidate,
    results: tuple[CanonicalAssistantResult, ...],
) -> tuple[RecoveredReport | None, tuple[str, ...]]:
    diagnostics: list[str] = []
    valid: list[RecoveredReport] = []
    for result in results:
        text = result.text
        position = 0
        envelope_index = 0
        saw_open = False
        while (start := text.find(_REPORT_OPEN_PREFIX, position)) >= 0:
            saw_open = True
            match = _REPORT_OPEN_RE.match(text, start)
            current_index = envelope_index
            envelope_index += 1
            if match is None:
                diagnostics.append(
                    f"rollout line {result.line_number} envelope {current_index}: malformed report opener"
                )
                position = start + len(_REPORT_OPEN_PREFIX)
                continue
            close = text.find(_REPORT_CLOSE, match.end())
            if close < 0:
                diagnostics.append(
                    f"rollout line {result.line_number} envelope {current_index}: truncated report envelope"
                )
                position = match.end()
                continue
            body = text[match.end() : close]
            envelope_text = text[start : close + len(_REPORT_CLOSE)]
            if _REPORT_OPEN_PREFIX in body or _REPORT_CLOSE in body:
                diagnostics.append(
                    f"rollout line {result.line_number} envelope {current_index}: nested report envelope"
                )
                position = close + len(_REPORT_CLOSE)
                continue
            try:
                envelope_run_id = validate_run_id(match.group("run_id"))
            except (TypeError, ValueError):
                diagnostics.append(
                    f"rollout line {result.line_number} envelope {current_index}: malformed report run ID"
                )
                position = close + len(_REPORT_CLOSE)
                continue
            if envelope_run_id != manifest.identity.run_id:
                diagnostics.append(
                    f"rollout line {result.line_number} envelope {current_index}: report belongs to another run"
                )
                position = close + len(_REPORT_CLOSE)
                continue
            try:
                decoded = json.loads(body)
                payload = report_payload_from_dict(decoded)
            except (json.JSONDecodeError, ContractError, TypeError, ValueError) as error:
                diagnostics.append(
                    f"rollout line {result.line_number} envelope {current_index}: invalid report payload: {error}"
                )
                position = close + len(_REPORT_CLOSE)
                continue
            sidecar = ReportSidecar(
                schema_version=1,
                run_id=manifest.identity.run_id,
                execution_thread_id=candidate.thread_id,
                rollout_path=str(candidate.path),
                assistant_result=result.pointer,
                envelope_index=current_index,
                envelope_sha256=_sha256(envelope_text),
                report=payload,
            )
            valid.append(RecoveredReport(payload, sidecar))
            position = close + len(_REPORT_CLOSE)
        if _REPORT_CLOSE in text and not saw_open:
            diagnostics.append(
                f"rollout line {result.line_number}: report closing delimiter has no opener"
            )
    return (valid[-1] if valid else None), tuple(diagnostics)


def associate_execution(
    manifest: RunManifest,
    codex_home: str | Path,
    *,
    rollout_paths: tuple[Path, ...] | None = None,
) -> AssociationResult:
    """Associate exactly one live rollout with a launch manifest."""

    paths = discover_execution_rollouts(codex_home) if rollout_paths is None else rollout_paths
    candidates: list[_RolloutCandidate] = []
    diagnostics: list[str] = []
    marker_ambiguity = False
    for path in paths:
        candidate, candidate_diagnostics = _candidate_for_rollout(
            Path(path).expanduser().resolve(strict=False), manifest
        )
        diagnostics.extend(candidate_diagnostics)
        marker_ambiguity = marker_ambiguity or any(
            "ambiguous" in diagnostic for diagnostic in candidate_diagnostics
        )
        if candidate is not None:
            candidates.append(candidate)
    if marker_ambiguity:
        diagnostics.append(
            "relevant rollout marker evidence is globally ambiguous; refusing association"
        )
        return AssociationResult(None, True, tuple(sorted(set(diagnostics))))
    if len(candidates) > 1:
        diagnostics.append(
            "multiple qualifying execution rollouts make association ambiguous: "
            + ", ".join(str(candidate.path) for candidate in candidates)
        )
        return AssociationResult(None, True, tuple(sorted(set(diagnostics))))
    if not candidates:
        diagnostics.append("no rollout satisfies the exact execution association contract")
        return AssociationResult(None, False, tuple(sorted(set(diagnostics))))
    candidate = candidates[0]
    results = _assistant_results(candidate)
    latest = results[-1] if results else None
    report, report_diagnostics = _recover_report(manifest, candidate, results)
    diagnostics.extend(report_diagnostics)
    execution = ExecutionSidecar(
        schema_version=1,
        run_id=manifest.identity.run_id,
        execution_thread_id=candidate.thread_id,
        rollout_path=str(candidate.path),
        session_meta_line=1,
        session_timestamp=candidate.session_timestamp,
        forked_from_id=candidate.forked_from_id,
        marker_turn_id=candidate.marker.turn_id,
        marker_line=candidate.marker.line_number,
        marker_timestamp=candidate.marker.timestamp,
        task_started_line=candidate.marker.task_started_line,
        turn_context_line=candidate.marker.turn_context_line,
        segment_start_line=candidate.marker.line_number,
        segment_end_before_line=candidate.segment_end_before_line,
        observed_end_line=candidate.observed_end_line,
        latest_assistant_result=None if latest is None else latest.pointer,
    )
    associated = AssociatedExecution(
        execution=execution,
        latest_assistant_result=latest,
        report=report,
        diagnostics=tuple(sorted(set(diagnostics))),
    )
    return AssociationResult(associated, False, associated.diagnostics)


__all__ = [
    "AssociatedExecution",
    "AssociationResult",
    "CanonicalAssistantResult",
    "RecoveredReport",
    "associate_execution",
    "discover_execution_rollouts",
]
