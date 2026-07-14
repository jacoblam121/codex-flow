"""Versioned, read-only Phase 01 preflight orchestration."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import FailedPrecondition, InvalidCLIUsage
from .git import inspect_repository
from .models import CommandRunner, ModelCatalog, load_model_catalog
from .paths import resolve_paths
from .rollouts import RolloutAnalysis, analyze_rollout, discover_rollout, validate_thread_id

PREFLIGHT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PreflightResult:
    source: Mapping[str, Any]
    native_mode: str
    mode_evidence: Mapping[str, Any]
    plan: Mapping[str, Any]
    repository: Mapping[str, Any]
    requested_model: str | None
    requested_effort: str | None
    supported_models: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    ready: bool
    exit_code: int
    rollout_diagnostics: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PREFLIGHT_SCHEMA_VERSION,
            "source": dict(self.source),
            "native_mode": self.native_mode,
            "mode_evidence": dict(self.mode_evidence),
            "plan": dict(self.plan),
            "repository": dict(self.repository),
            "model_selection": {
                "model": self.requested_model,
                "effort": self.requested_effort,
            },
            "supported_models": [dict(model) for model in self.supported_models],
            "handoff": {
                "ready": self.ready,
                "blockers": list(self.blockers),
                "warnings": list(self.warnings),
            },
            "rollout_diagnostics": dict(self.rollout_diagnostics),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n"


def _absolute_cwd(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _catalog_documents(catalog: ModelCatalog) -> tuple[Mapping[str, Any], ...]:
    return tuple(model.to_dict() for model in catalog.models)


def _plan_document(analysis: RolloutAnalysis) -> dict[str, Any]:
    return analysis.plan.to_dict()


def run_preflight(
    thread_id: str,
    *,
    cwd: str | Path | None = None,
    caller_cwd: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    codex_home: str | Path | None = None,
    model: str | None = None,
    effort: str | None = None,
    command_runner: CommandRunner | Any | None = None,
    git_runner: Any | None = None,
) -> PreflightResult:
    """Collect all Phase 01 evidence without writing state or launching Codex."""

    if (model is None) != (effort is None):
        raise InvalidCLIUsage("--model and --effort must be supplied together")
    canonical_thread_id = validate_thread_id(thread_id)
    env = os.environ if environ is None else environ
    if codex_home is None:
        codex_home_path = resolve_paths(env).codex_home
    else:
        codex_home_path = _absolute_cwd(codex_home)
    caller = _absolute_cwd(caller_cwd if caller_cwd is not None else Path.cwd())
    requested = _absolute_cwd(cwd if cwd is not None else caller)
    if not requested.is_dir():
        raise FailedPrecondition(f"requested CWD is not a directory: {requested}")

    rollout_path = discover_rollout(canonical_thread_id, codex_home_path)
    analysis = analyze_rollout(rollout_path, canonical_thread_id)
    git_inspection = inspect_repository(
        requested,
        original_working_directory=caller,
        runner=git_runner,
    )
    catalog = load_model_catalog(command_runner)

    warnings = list(analysis.warnings) + list(git_inspection.warnings) + list(catalog.warnings)
    rollout_cwd = analysis.owner.rollout_cwd
    if rollout_cwd is None:
        warnings.append("rollout session_meta did not record a CWD")
    else:
        rollout_cwd_path = _absolute_cwd(rollout_cwd)
        if rollout_cwd_path != requested:
            warnings.append(
                f"rollout CWD differs from requested CWD: rollout={rollout_cwd_path} requested={requested}"
            )

    blockers: list[str] = []
    capability_blocked = False
    if analysis.mode.value == "plan":
        blockers.append("native collaboration mode is 'plan'; handoff requires 'default'")
    elif analysis.mode.value == "missing":
        blockers.append("native collaboration mode is missing")
    elif analysis.mode.value == "unknown":
        capability_blocked = True
        blockers.append(
            f"unsupported native collaboration mode: {analysis.mode.raw_value!r}"
        )
    if analysis.plan.text is None:
        blockers.append("no valid approved plan evidence was found")
    if model is not None and effort is not None:
        if not catalog.supported_pair(model, effort):
            capability_blocked = True
            blockers.append(
                f"unsupported model/effort pair: model {model!r} does not support effort {effort!r}"
            )

    blockers = sorted(set(blockers))
    warnings = sorted(set(warnings))
    ready = not capability_blocked and not blockers
    if capability_blocked:
        exit_code = 4
    elif blockers:
        exit_code = 3
    else:
        exit_code = 0
    source = {
        "thread_id": canonical_thread_id,
        "rollout_path": str(rollout_path),
        "thread_source": analysis.owner.thread_source,
        "rollout_cwd": rollout_cwd,
        "session_meta": analysis.owner.evidence.to_dict(),
    }
    return PreflightResult(
        source=source,
        native_mode=analysis.mode.value,
        mode_evidence=analysis.mode.to_dict(),
        plan=_plan_document(analysis),
        repository=git_inspection.to_dict(),
        requested_model=model,
        requested_effort=effort,
        supported_models=_catalog_documents(catalog),
        warnings=tuple(warnings),
        blockers=tuple(blockers),
        ready=ready,
        exit_code=exit_code,
        rollout_diagnostics={
            "malformed_line_count": analysis.malformed_line_count,
            "malformed_line_numbers": list(analysis.malformed_line_numbers),
        },
    )


__all__ = ["PREFLIGHT_SCHEMA_VERSION", "PreflightResult", "run_preflight"]
