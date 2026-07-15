"""Read-only run inspection and explicit derived-cache persistence."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .atomic import atomic_write_json
from .contracts import (
    ExecutionSidecar,
    ReportSidecar,
    RunManifest,
    execution_sidecar_from_dict,
    report_sidecar_from_dict,
    validate_run_id,
)
from .errors import ApplicationError, ContractError, FailedPrecondition, InvalidCLIUsage
from .evidence import AssociationResult, associate_execution
from .git import inspect_repository
from .paths import FlowPaths, resolve_paths
from .rollouts import validate_thread_id

SHOW_SCHEMA_VERSION = 1


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink():
        raise ContractError(f"{label} is redirected through a symlink")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ContractError(f"cannot read {label}: {path}") from error


@dataclass(frozen=True)
class RunBundle:
    run_dir: Path
    manifest: RunManifest
    plan_text: str
    handoff_text: str


def load_run_bundle(run_id: str, *, paths: FlowPaths) -> RunBundle:
    """Load immutable launch artifacts without probing the old Codex binary."""

    try:
        canonical_run_id = validate_run_id(run_id)
    except (TypeError, ValueError) as error:
        raise InvalidCLIUsage("run_id must be a canonical UUIDv4 string") from error
    run_dir = paths.run_path(canonical_run_id)
    if run_dir.is_symlink():
        raise ContractError("run directory is redirected through a symlink")
    expected = {
        "manifest": run_dir / "manifest.json",
        "plan": run_dir / "plan.md",
        "handoff": run_dir / "handoff.md",
        "execution": run_dir / "execution.json",
        "report": run_dir / "report.json",
        "audit": run_dir / "audit.json",
    }
    for field_name in ("manifest", "plan", "handoff"):
        if expected[field_name].is_symlink():
            raise ContractError(f"{field_name} artifact is redirected through a symlink")
    manifest_bytes = _read_bytes(expected["manifest"], "manifest.json")
    try:
        raw_document = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError("manifest.json is not valid UTF-8 JSON") from error
    try:
        manifest = RunManifest.from_dict(raw_document)
    except (TypeError, ValueError) as error:
        raise ContractError(f"manifest.json is invalid: {error}") from error
    if manifest.identity.run_id != canonical_run_id:
        raise ContractError("manifest identity run_id does not match the requested run ID")
    raw_artifacts = raw_document.get("artifacts")
    if not isinstance(raw_artifacts, Mapping):
        raise ContractError("manifest artifacts must be an object")
    for field_name, expected_path in expected.items():
        if raw_artifacts.get(field_name) != str(expected_path):
            raise ContractError(
                f"manifest artifact {field_name} must equal the canonical path {expected_path}"
            )
        if field_name in {"manifest", "plan", "handoff"} and getattr(
            manifest.artifacts, field_name
        ) != str(expected_path):
            raise ContractError(f"manifest artifact {field_name} was redirected")
    plan_bytes = _read_bytes(expected["plan"], "plan.md")
    handoff_bytes = _read_bytes(expected["handoff"], "handoff.md")
    try:
        plan_text = plan_bytes.decode("utf-8")
        handoff_text = handoff_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("plan.md and handoff.md must be valid UTF-8") from error
    if _sha256(plan_bytes) != manifest.plan_sha256:
        raise ContractError("plan.md SHA-256 does not match manifest plan_sha256")
    return RunBundle(run_dir, manifest, plan_text, handoff_text)


@dataclass(frozen=True)
class CacheInspection:
    status: str
    diagnostic: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"status": self.status}
        if self.diagnostic is not None:
            result["diagnostic"] = self.diagnostic
        return result


def _inspect_cache(
    path: Path,
    validator: Callable[[Mapping[str, Any]], Any],
    expected: Mapping[str, Any] | None,
) -> CacheInspection:
    if not path.exists() and not path.is_symlink():
        return CacheInspection("missing")
    if path.is_symlink():
        return CacheInspection("invalid", f"{path.name} is redirected through a symlink")
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
        validated = validator(decoded)
    except (
        ApplicationError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        return CacheInspection("invalid", f"{path.name} is invalid: {error}")
    if expected is None or validated.to_dict() != dict(expected):
        return CacheInspection("stale", f"{path.name} does not match live rollout evidence")
    return CacheInspection("valid")


def _repository_document(
    manifest: RunManifest, git_runner: Any | None
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        live = inspect_repository(manifest.repository.working_directory, runner=git_runner)
    except (ApplicationError, OSError) as error:
        return None, f"live repository inspection failed: {error}"
    baseline = asdict(manifest.repository)
    live_document = live.to_dict()
    comparison = {
        "repository_kind_changed": (
            manifest.repository.is_git_repository != live.is_git_repository
        ),
        "repository_root_changed": (
            manifest.repository.repository_root != live.repository_root
        ),
        "branch_changed": manifest.repository.branch != live.branch,
        "head_changed": manifest.repository.head != live.head,
        "dirty_changed": manifest.repository.dirty != live.dirty,
        "baseline_fingerprint_changed": (
            manifest.repository.baseline_fingerprint != live.baseline_fingerprint
        ),
    }
    return {
        "baseline": baseline,
        "live": live_document,
        "comparison": comparison,
        "warnings": list(live.warnings),
    }, None


def _persist_sidecars(bundle: RunBundle, association: AssociationResult) -> tuple[str, ...]:
    associated = association.association
    if associated is None:
        raise FailedPrecondition(
            "--persist-derived requires exactly one live execution rollout association"
        )
    execution_path = bundle.run_dir / "execution.json"
    report_path = bundle.run_dir / "report.json"
    for path in (execution_path, report_path):
        if path.is_symlink():
            raise ContractError(f"refusing to replace symlinked derived sidecar: {path}")
        if path.parent != bundle.run_dir:
            raise ContractError(f"derived sidecar is outside the exact run directory: {path}")
    persisted: list[str] = []
    try:
        atomic_write_json(execution_path, associated.execution.to_dict(), overwrite=True)
        persisted.append(str(execution_path))
        if associated.report is not None:
            atomic_write_json(
                report_path, associated.report.sidecar.to_dict(), overwrite=True
            )
            persisted.append(str(report_path))
    except OSError as error:
        raise FailedPrecondition(f"could not persist derived sidecar atomically: {error}") from error
    return tuple(persisted)


def _run_document(
    bundle: RunBundle,
    *,
    codex_home: Path,
    git_runner: Any | None,
    persist_derived: bool,
) -> dict[str, Any]:
    association = associate_execution(bundle.manifest, codex_home)
    associated = association.association
    repository, repository_error = _repository_document(bundle.manifest, git_runner)
    diagnostics = list(association.diagnostics)
    if repository_error is not None:
        diagnostics.append(repository_error)
    expected_execution = None if associated is None else associated.execution.to_dict()
    expected_report = (
        None
        if associated is None or associated.report is None
        else associated.report.sidecar.to_dict()
    )
    execution_cache = _inspect_cache(
        bundle.run_dir / "execution.json",
        execution_sidecar_from_dict,
        expected_execution,
    )
    report_cache = _inspect_cache(
        bundle.run_dir / "report.json",
        report_sidecar_from_dict,
        expected_report,
    )
    for cache in (execution_cache, report_cache):
        if cache.diagnostic is not None:
            diagnostics.append(cache.diagnostic)
    persisted: tuple[str, ...] = ()
    if persist_derived:
        persisted = _persist_sidecars(bundle, association)
        execution_cache = CacheInspection("valid")
        if associated is not None and associated.report is not None:
            report_cache = CacheInspection("valid")
    report = None if associated is None or associated.report is None else associated.report.payload
    latest = None if associated is None else associated.latest_assistant_result
    states = {
        "launched": True,
        "associated": associated is not None,
        "reported": report is not None,
        "reviewable": associated is not None and repository is not None,
        "blocked": report is not None and report.status == "blocked",
    }
    return {
        "run_id": bundle.manifest.identity.run_id,
        "created_at": bundle.manifest.created_at,
        "source_thread": bundle.manifest.source_thread.thread_id,
        "working_directory": bundle.manifest.repository.working_directory,
        "context_mode": bundle.manifest.handoff.context_mode,
        "model": bundle.manifest.handoff.model,
        "reasoning_effort": bundle.manifest.handoff.reasoning_effort,
        "states": states,
        "execution": None if associated is None else associated.execution.to_dict(),
        "report": None if report is None else report.to_dict(),
        "latest_assistant_result": None if latest is None else latest.to_dict(),
        "repository": repository,
        "derived_caches": {
            "execution": execution_cache.to_dict(),
            "report": report_cache.to_dict(),
        },
        "persisted_derived": list(persisted),
        "diagnostics": sorted(set(diagnostics)),
    }


def show_run(
    run_id: str,
    *,
    environ: Mapping[str, str] | None = None,
    paths: FlowPaths | None = None,
    git_runner: Any | None = None,
    persist_derived: bool = False,
) -> dict[str, Any]:
    """Build the exact-run JSON document, writing only when explicitly asked."""

    env = os.environ if environ is None else environ
    resolved = resolve_paths(env) if paths is None else paths
    bundle = load_run_bundle(run_id, paths=resolved)
    return {
        "schema_version": SHOW_SCHEMA_VERSION,
        "query": {"run_id": bundle.manifest.identity.run_id},
        "run": _run_document(
            bundle,
            codex_home=resolved.codex_home,
            git_runner=git_runner,
            persist_derived=persist_derived,
        ),
    }


def show_runs_by_source(
    source_thread: str,
    cwd: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
    paths: FlowPaths | None = None,
    git_runner: Any | None = None,
) -> dict[str, Any]:
    """Summarize and conservatively select runs for an exact source/CWD."""

    try:
        canonical_thread = validate_thread_id(source_thread)
    except (TypeError, ValueError, ContractError) as error:
        raise InvalidCLIUsage("source thread must be a canonical UUID") from error
    requested_cwd = str(Path(cwd).expanduser().resolve(strict=False))
    env = os.environ if environ is None else environ
    resolved = resolve_paths(env) if paths is None else paths
    matches: list[RunBundle] = []
    diagnostics: list[str] = []
    if resolved.runs.is_dir():
        try:
            entries = sorted(resolved.runs.iterdir(), key=lambda path: path.name)
        except OSError as error:
            raise ContractError(f"cannot enumerate run storage {resolved.runs}: {error}") from error
        for entry in entries:
            if not entry.is_dir() or entry.is_symlink():
                continue
            try:
                run_id = validate_run_id(entry.name)
                bundle = load_run_bundle(run_id, paths=resolved)
            except (TypeError, ValueError, ApplicationError) as error:
                diagnostics.append(f"ignored invalid run directory {entry.name}: {error}")
                continue
            manifest = bundle.manifest
            if (
                manifest.source_thread.thread_id == canonical_thread
                and manifest.repository.working_directory == requested_cwd
            ):
                matches.append(bundle)
    matches.sort(
        key=lambda bundle: (
            bundle.manifest.created_at,
            bundle.manifest.identity.run_id,
        ),
        reverse=True,
    )
    candidates: list[dict[str, Any]] = []
    for bundle in matches:
        association = associate_execution(bundle.manifest, resolved.codex_home)
        associated = association.association
        repository, repository_error = _repository_document(bundle.manifest, git_runner)
        candidate_diagnostics = list(association.diagnostics)
        if repository_error is not None:
            candidate_diagnostics.append(repository_error)
        report = (
            None
            if associated is None or associated.report is None
            else associated.report.payload
        )
        candidates.append(
            {
                "run_id": bundle.manifest.identity.run_id,
                "created_at": bundle.manifest.created_at,
                "source_thread": bundle.manifest.source_thread.thread_id,
                "working_directory": bundle.manifest.repository.working_directory,
                "context_mode": bundle.manifest.handoff.context_mode,
                "model": bundle.manifest.handoff.model,
                "reasoning_effort": bundle.manifest.handoff.reasoning_effort,
                "states": {
                    "launched": True,
                    "associated": associated is not None,
                    "reported": report is not None,
                    "reviewable": associated is not None and repository is not None,
                    "blocked": report is not None and report.status == "blocked",
                },
                "diagnostics": sorted(set(candidate_diagnostics)),
            }
        )
    candidate_run_ids = [candidate["run_id"] for candidate in candidates]
    if not candidates:
        selection = {
            "status": "none",
            "run_id": None,
            "candidate_run_ids": [],
            "reason": "no matching runs",
        }
    elif len(candidates) > 1:
        selection = {
            "status": "ambiguous",
            "run_id": None,
            "candidate_run_ids": candidate_run_ids,
            "reason": "multiple matching runs require explicit selection",
        }
    elif candidates[0]["states"]["reviewable"]:
        selection = {
            "status": "selected",
            "run_id": candidates[0]["run_id"],
            "candidate_run_ids": candidate_run_ids,
            "reason": "the only matching run is reviewable",
        }
    else:
        selection = {
            "status": "none",
            "run_id": None,
            "candidate_run_ids": candidate_run_ids,
            "reason": "the only matching run is not reviewable",
        }
    return {
        "schema_version": SHOW_SCHEMA_VERSION,
        "query": {"source_thread": canonical_thread, "cwd": requested_cwd},
        "selection": selection,
        "candidates": candidates,
        "diagnostics": sorted(set(diagnostics)),
    }


def to_json(document: Mapping[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


__all__ = [
    "RunBundle",
    "SHOW_SCHEMA_VERSION",
    "load_run_bundle",
    "show_run",
    "show_runs_by_source",
    "to_json",
]
