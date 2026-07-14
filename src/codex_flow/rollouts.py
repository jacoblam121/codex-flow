"""Defensive discovery and extraction of native Codex rollout evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ContractError, UnsupportedCapability

_THREAD_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ROLLOUT_NAME_RE = re.compile(
    r"(?:^|[-_])(?P<thread>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.jsonl$",
    re.IGNORECASE,
)
_PLAN_OPEN = "<proposed_plan>"
_PLAN_CLOSE = "</proposed_plan>"
_PLAN_OPEN_PREFIX = "<proposed_plan"
_PLAN_CLOSE_PREFIX = "</proposed_plan"


def validate_thread_id(thread_id: str) -> str:
    """Validate and canonicalize a Codex thread UUID."""

    if not isinstance(thread_id, str) or not _THREAD_ID_RE.fullmatch(thread_id):
        raise ContractError("thread ID must be a canonical UUID")
    return thread_id.lower()


@dataclass(frozen=True)
class JsonlRecord:
    line_number: int
    value: Any

    @property
    def record_type(self) -> str | None:
        if isinstance(self.value, Mapping) and isinstance(self.value.get("type"), str):
            return self.value["type"]
        return None


class JsonlReader:
    """A reusable, line-numbered, streaming JSONL reader.

    Invalid UTF-8, blank lines, invalid JSON, and valid JSON primitives are
    handled without reading the rest of the file into memory. Only malformed
    lines are counted; callers decide whether a warning is conclusive for the
    evidence they are collecting.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.malformed_line_numbers: list[int] = []
        self.warnings: list[str] = []

    @property
    def malformed_line_count(self) -> int:
        return len(self.malformed_line_numbers)

    def _malformed(self, line_number: int, reason: str) -> None:
        self.malformed_line_numbers.append(line_number)
        self.warnings.append(f"rollout line {line_number}: malformed {reason}")

    def __iter__(self) -> Iterator[JsonlRecord]:
        try:
            stream = self.path.open("rb")
        except OSError as error:
            raise ContractError(f"cannot read rollout {self.path}: {error}") from error
        with stream:
            for line_number, raw_line in enumerate(stream, start=1):
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError:
                    self._malformed(line_number, "UTF-8")
                    continue
                line = line.rstrip("\r\n")
                if not line.strip():
                    self._malformed(line_number, "JSONL line")
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    self._malformed(line_number, "JSON")
                    continue
                yield JsonlRecord(line_number, value)


@dataclass(frozen=True)
class Evidence:
    line_number: int
    record_type: str

    def to_dict(self) -> dict[str, Any]:
        return {"line_number": self.line_number, "record_type": self.record_type}


@dataclass(frozen=True)
class SessionOwner:
    thread_id: str
    thread_source: str
    rollout_cwd: str | None
    evidence: Evidence


@dataclass(frozen=True)
class ModeEvidence:
    value: str
    raw_value: Any
    evidence: Evidence | None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"value": self.value}
        if self.raw_value is not None:
            result["raw_value"] = self.raw_value
        if self.evidence is not None:
            result["evidence"] = self.evidence.to_dict()
        return result


@dataclass(frozen=True)
class PlanEvidence:
    text: str | None
    source: str
    structured: Evidence | None = None
    tagged: Evidence | None = None

    @property
    def evidence_line(self) -> int | None:
        lines = [
            evidence.line_number
            for evidence in (self.structured, self.tagged)
            if evidence is not None
        ]
        return max(lines) if lines else None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "text": self.text,
            "source": self.source,
        }
        if self.structured is not None:
            result["structured"] = self.structured.to_dict()
        if self.tagged is not None:
            result["tagged"] = self.tagged.to_dict()
        return result


@dataclass(frozen=True)
class PlanDetails:
    text: str | None
    sha256: str | None
    title: str | None
    preview: str | None
    source: str
    structured: Evidence | None
    tagged: Evidence | None

    @property
    def evidence_line(self) -> int | None:
        lines = [
            evidence.line_number
            for evidence in (self.structured, self.tagged)
            if evidence is not None
        ]
        return max(lines) if lines else None

    def to_dict(self) -> dict[str, Any]:
        evidence: dict[str, Any] = {}
        if self.structured is not None:
            evidence["structured"] = self.structured.to_dict()
        if self.tagged is not None:
            evidence["tagged"] = self.tagged.to_dict()
        return {
            "text": self.text,
            "sha256": self.sha256,
            "title": self.title,
            "preview": self.preview,
            "source": self.source,
            "evidence": evidence,
        }


@dataclass(frozen=True)
class RolloutAnalysis:
    thread_id: str
    rollout_path: str
    owner: SessionOwner
    mode: ModeEvidence
    plan: PlanDetails
    malformed_line_count: int
    malformed_line_numbers: tuple[int, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "rollout_path": self.rollout_path,
            "owner": {
                "thread_source": self.owner.thread_source,
                "rollout_cwd": self.owner.rollout_cwd,
                "evidence": self.owner.evidence.to_dict(),
            },
            "mode": self.mode.to_dict(),
            "plan_diagnostics": {
                "malformed_line_count": self.malformed_line_count,
                "malformed_line_numbers": list(self.malformed_line_numbers),
            },
        }


def discover_rollout(thread_id: str, codex_home: str | Path) -> Path:
    """Find exactly one rollout whose filename terminates in ``thread_id``."""

    canonical_thread_id = validate_thread_id(thread_id)
    sessions = Path(codex_home).expanduser().resolve(strict=False) / "sessions"
    try:
        candidates = sorted(
            path.resolve(strict=False)
            for path in sessions.rglob("*.jsonl")
            if path.is_file()
            and path.name.startswith("rollout-")
            and (
                match := _ROLLOUT_NAME_RE.search(path.name)
            ) is not None
            and match.group("thread").lower() == canonical_thread_id
        )
    except OSError as error:
        raise ContractError(f"cannot search rollout directory {sessions}: {error}") from error
    if not candidates:
        raise ContractError(
            f"no rollout filename ending in thread ID {canonical_thread_id} was found beneath {sessions}"
        )
    if len(candidates) > 1:
        joined = ", ".join(str(path) for path in candidates)
        raise ContractError(
            f"multiple exact rollout filename matches for thread ID {canonical_thread_id}: {joined}"
        )
    return candidates[0]


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


@dataclass(frozen=True)
class _PlanEnvelope:
    """A complete outer envelope, retaining its normalized body exactly."""

    body: str


@dataclass(frozen=True)
class _AssistantFinal:
    evidence: Evidence
    text: str | None
    envelope: _PlanEnvelope | None
    error: str | None = None


def _outer_plan_envelope(text: str) -> tuple[_PlanEnvelope | None, str | None]:
    """Recognize only an outer envelope, without interpreting its body."""

    normalized = _normalize_text(text)
    outside_removed = normalized.strip()
    starts_open = outside_removed.startswith(_PLAN_OPEN_PREFIX)
    if not starts_open:
        return None, None
    if not outside_removed.startswith(_PLAN_OPEN) or not outside_removed.endswith(_PLAN_CLOSE):
        return None, "plan envelope is truncated or malformed"
    body = outside_removed[len(_PLAN_OPEN) : -len(_PLAN_CLOSE)]
    if not body:
        return None, "the proposed plan is empty"
    return _PlanEnvelope(body), None


def _tagged_only_body(envelope: _PlanEnvelope) -> tuple[str | None, str | None]:
    """Validate a fallback envelope where no structured text can disambiguate it."""

    if _PLAN_OPEN in envelope.body or _PLAN_CLOSE in envelope.body:
        return None, "plan tags are nested or repeated"
    body = envelope.body
    if body.startswith("\n"):
        body = body[1:]
    if body.endswith("\n"):
        body = body[:-1]
    if not body:
        return None, "the proposed plan is empty"
    return body, None


def _matching_wrapper_variant(body: str, structured_text: str) -> bool:
    """Compare only the four permitted combinations of wrapper newlines."""

    variants = {body}
    leading = body.startswith("\n")
    trailing = body.endswith("\n")
    if leading:
        variants.add(body[1:])
    if trailing:
        variants.add(body[:-1])
    if leading and trailing:
        variants.add(body[1:-1])
    return structured_text in variants


def _display_title(text: str) -> str:
    for line in text.split("\n"):
        if line.strip():
            candidate = line.strip()
            candidate = re.sub(r"^#{1,6}(?:[ \t]+|$)", "", candidate).strip()
            return candidate
    return ""


def _display_preview(text: str, limit: int = 180) -> str:
    preview = " ".join(text.split("\n"))
    if len(preview) <= limit:
        return preview
    return preview[: limit - 3] + "..."


def _invalid_evidence(
    warnings: list[str], invalid_lines: list[int], line_number: int, message: str
) -> None:
    invalid_lines.append(line_number)
    warnings.append(f"rollout line {line_number}: {message}")


def analyze_rollout(path: str | Path, thread_id: str) -> RolloutAnalysis:
    """Stream one exact rollout and extract mode and approved-plan evidence."""

    canonical_thread_id = validate_thread_id(thread_id)
    rollout_path = Path(path).expanduser().resolve(strict=False)
    reader = JsonlReader(rollout_path)
    owner: SessionOwner | None = None
    latest_mode: ModeEvidence | None = None
    structured_plans: list[tuple[str, Evidence]] = []
    assistant_finals: list[_AssistantFinal] = []
    invalid_owner_lines: list[int] = []
    invalid_mode_lines: list[int] = []
    invalid_plan_lines: list[int] = []
    extra_warnings: list[str] = []

    for record in reader:
        value = _as_mapping(record.value)
        if value is None:
            continue
        record_type = record.record_type
        payload = _as_mapping(value.get("payload"))

        if record_type == "session_meta" and owner is None:
            if payload is None:
                _invalid_evidence(
                    extra_warnings,
                    invalid_owner_lines,
                    record.line_number,
                    "session_meta payload is not an object",
                )
                continue
            payload_id = payload.get("id")
            if not isinstance(payload_id, str) or not _THREAD_ID_RE.fullmatch(payload_id):
                _invalid_evidence(
                    extra_warnings,
                    invalid_owner_lines,
                    record.line_number,
                    "session_meta id is missing or malformed",
                )
                continue
            if payload_id.lower() != canonical_thread_id:
                raise ContractError(
                    "the first valid session_meta id does not agree with "
                    f"filename/requested thread {canonical_thread_id}"
                )
            thread_source = payload.get("thread_source")
            if thread_source == "subagent":
                raise UnsupportedCapability(
                    f"rollout {rollout_path} is a subagent rollout; source thread must be root interactive"
                )
            if thread_source not in {"user", "root"}:
                raise UnsupportedCapability(
                    f"rollout {rollout_path} has unsupported thread_source {thread_source!r}"
                )
            session_id = payload.get("session_id")
            if not isinstance(session_id, str) or not _THREAD_ID_RE.fullmatch(session_id):
                _invalid_evidence(
                    extra_warnings,
                    invalid_owner_lines,
                    record.line_number,
                    "root session_meta session_id is missing or malformed",
                )
                continue
            if session_id.lower() != canonical_thread_id:
                raise ContractError(
                    "the root session_meta session_id does not agree with "
                    f"filename/requested thread {canonical_thread_id}"
                )
            rollout_cwd = payload.get("cwd")
            if rollout_cwd is not None and not isinstance(rollout_cwd, str):
                _invalid_evidence(
                    extra_warnings,
                    invalid_owner_lines,
                    record.line_number,
                    "session_meta cwd is not a string",
                )
                rollout_cwd = None
            owner = SessionOwner(
                thread_id=canonical_thread_id,
                thread_source=thread_source,
                rollout_cwd=rollout_cwd,
                evidence=Evidence(record.line_number, "session_meta"),
            )
            continue

        if record_type == "turn_context":
            if payload is None:
                _invalid_evidence(
                    extra_warnings,
                    invalid_mode_lines,
                    record.line_number,
                    "turn_context payload is not an object",
                )
                continue
            collaboration_mode = _as_mapping(payload.get("collaboration_mode"))
            mode_value = collaboration_mode.get("mode") if collaboration_mode else None
            if not collaboration_mode or not isinstance(mode_value, str) or not mode_value:
                _invalid_evidence(
                    extra_warnings,
                    invalid_mode_lines,
                    record.line_number,
                    "turn_context collaboration_mode.mode is missing or malformed",
                )
                continue
            normalized_mode = mode_value if mode_value in {"plan", "default"} else "unknown"
            latest_mode = ModeEvidence(
                normalized_mode,
                mode_value if normalized_mode == "unknown" else None,
                Evidence(record.line_number, "turn_context"),
            )
            continue

        if record_type == "event_msg":
            if payload is None or payload.get("type") != "item_completed":
                continue
            item = _as_mapping(payload.get("item"))
            if item is None or item.get("type") != "Plan":
                continue
            text_value = item.get("text")
            if not isinstance(text_value, str) or not text_value:
                _invalid_evidence(
                    extra_warnings,
                    invalid_plan_lines,
                    record.line_number,
                    "structured Plan text is missing or malformed",
                )
                continue
            structured_plans.append(
                (_normalize_text(text_value), Evidence(record.line_number, "event_msg"))
            )
            continue

        if record_type == "response_item":
            if payload is None or payload.get("type") != "message":
                continue
            if payload.get("role") != "assistant" or payload.get("phase") != "final_answer":
                continue
            final_evidence = Evidence(record.line_number, "response_item")
            content = payload.get("content")
            if not isinstance(content, list):
                _invalid_evidence(
                    extra_warnings,
                    invalid_plan_lines,
                    record.line_number,
                    "tagged final content is missing or malformed",
                )
                assistant_finals.append(
                    _AssistantFinal(final_evidence, None, None, "tagged final content is missing or malformed")
                )
                continue
            output_parts = [part for part in content if isinstance(part, Mapping) and part.get("type") == "output_text"]
            if not output_parts:
                _invalid_evidence(
                    extra_warnings,
                    invalid_plan_lines,
                    record.line_number,
                    "tagged final has no output_text content part",
                )
                assistant_finals.append(
                    _AssistantFinal(final_evidence, None, None, "tagged final has no output_text content part")
                )
                continue
            if len(output_parts) != 1 or not isinstance(output_parts[0].get("text"), str):
                _invalid_evidence(
                    extra_warnings,
                    invalid_plan_lines,
                    record.line_number,
                    "tagged final output_text is ambiguous or malformed",
                )
                assistant_finals.append(
                    _AssistantFinal(
                        final_evidence,
                        None,
                        None,
                        "tagged final output_text is ambiguous or malformed",
                    )
                )
                continue
            output_text = _normalize_text(output_parts[0]["text"])
            envelope, tag_error = _outer_plan_envelope(output_text)
            if tag_error is not None:
                _invalid_evidence(
                    extra_warnings,
                    invalid_plan_lines,
                    record.line_number,
                    tag_error,
                )
            assistant_finals.append(
                _AssistantFinal(
                    final_evidence,
                    output_text,
                    envelope,
                    tag_error,
                )
            )

    if owner is None:
        raise ContractError(
            f"rollout {rollout_path} has no valid session_meta owner for thread {canonical_thread_id}"
        )

    latest_mode = latest_mode or ModeEvidence("missing", None, None)
    warnings = sorted(set(reader.warnings + extra_warnings))

    mode_malformed_lines = sorted(
        set(reader.malformed_line_numbers) | set(invalid_mode_lines)
    )
    if latest_mode.evidence is not None and mode_malformed_lines:
        later = [line for line in mode_malformed_lines if line > latest_mode.evidence.line_number]
        if later:
            raise ContractError(
                "malformed rollout data after the latest native mode at line "
                f"{latest_mode.evidence.line_number} prevents proving the latest mode "
                f"(lines {', '.join(map(str, later))})"
            )

    latest_structured = structured_plans[-1] if structured_plans else None
    selected: PlanEvidence
    if latest_structured is not None:
        structured_text, structured_evidence = latest_structured
        corresponding_final = next(
            (
                final
                for final in assistant_finals
                if final.evidence.line_number > structured_evidence.line_number
            ),
            None,
        )
        if corresponding_final is not None:
            if corresponding_final.error is not None:
                raise ContractError(
                    "the first assistant final after the latest structured Plan is malformed: "
                    f"{corresponding_final.error}"
                )
            if corresponding_final.envelope is not None and not _matching_wrapper_variant(
                corresponding_final.envelope.body, structured_text
            ):
                raise ContractError(
                    "the latest structured Plan and its corresponding tagged final differ; "
                    "refusing to select a later or older plan"
                )
            if corresponding_final.envelope is not None:
                selected = PlanEvidence(
                    structured_text,
                    "structured+tagged",
                    structured=structured_evidence,
                    tagged=corresponding_final.evidence,
                )
            else:
                selected = PlanEvidence(
                    structured_text,
                    "structured-only",
                    structured=structured_evidence,
                )
                warnings.append(
                    "using the latest structured Plan; its corresponding assistant final was not a plan envelope"
                )
        else:
            selected = PlanEvidence(
                structured_text,
                "structured-only",
                structured=structured_evidence,
            )
            warnings.append("using the latest structured Plan without a matching tagged final")
    else:
        tagged_fallbacks: list[tuple[str, Evidence]] = []
        for final in assistant_finals:
            if final.error is not None:
                continue
            if final.envelope is None:
                continue
            tagged_text, tag_error = _tagged_only_body(final.envelope)
            if tag_error is not None:
                _invalid_evidence(
                    extra_warnings,
                    invalid_plan_lines,
                    final.evidence.line_number,
                    tag_error,
                )
                continue
            tagged_fallbacks.append((tagged_text, final.evidence))
        if tagged_fallbacks:
            tagged_text, tagged_evidence = tagged_fallbacks[-1]
            selected = PlanEvidence(tagged_text, "tagged-only", tagged=tagged_evidence)
            warnings.append("using a tagged assistant final as a compatibility plan fallback")
        else:
            selected = PlanEvidence(None, "missing")

    if selected.text is None and invalid_plan_lines:
        lines = ", ".join(map(str, sorted(invalid_plan_lines)))
        raise ContractError(
            f"malformed or ambiguous plan evidence at rollout lines {lines}; "
            "a valid plan cannot be selected"
        )

    plan_malformed_lines = sorted(
        set(reader.malformed_line_numbers) | set(invalid_plan_lines)
    )
    if selected.evidence_line is not None:
        later_malformed = [
            line for line in plan_malformed_lines if line > selected.evidence_line
        ]
        if later_malformed:
            raise ContractError(
                "malformed rollout data after the latest plan evidence at line "
                f"{selected.evidence_line} prevents proving the latest plan "
                f"(lines {', '.join(map(str, later_malformed))})"
            )

    if selected.text is None:
        plan = PlanDetails(None, None, None, None, "missing", None, None)
    else:
        canonical_text = _normalize_text(selected.text)
        plan = PlanDetails(
            canonical_text,
            hashlib.sha256(canonical_text.encode("utf-8")).hexdigest(),
            _display_title(canonical_text),
            _display_preview(canonical_text),
            selected.source,
            selected.structured,
            selected.tagged,
        )

    return RolloutAnalysis(
        thread_id=canonical_thread_id,
        rollout_path=str(rollout_path),
        owner=owner,
        mode=latest_mode,
        plan=plan,
        malformed_line_count=reader.malformed_line_count,
        malformed_line_numbers=tuple(sorted(reader.malformed_line_numbers)),
        warnings=tuple(sorted(set(warnings))),
    )


__all__ = [
    "Evidence",
    "JsonlReader",
    "JsonlRecord",
    "ModeEvidence",
    "PlanDetails",
    "RolloutAnalysis",
    "SessionOwner",
    "analyze_rollout",
    "discover_rollout",
    "validate_thread_id",
]
