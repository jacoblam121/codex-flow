"""Phase 02 handoff persistence and shell-free launcher boundaries."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .atomic import atomic_write_json, atomic_write_text
from .contracts import (
    ArtifactPaths,
    HandoffSelection,
    RepositoryBaseline,
    RunIdentity,
    RunManifest,
    ThreadReference,
    utc_timestamp,
    validate_run_id,
    validate_sha256,
)
from .errors import (
    ContractError,
    ExternalCommandFailure,
    FailedPrecondition,
    InvalidCLIUsage,
    UnsupportedCapability,
)
from .models import CommandResult, CommandRunner, SubprocessCommandRunner
from .paths import FlowPaths, resolve_paths
from .preflight import PreflightResult, run_preflight
from .rollouts import validate_thread_id

CONTEXT_MODES = ("plan", "fork")
REPORT_STATUSES = ("completed", "partial", "blocked")
WINDOWS_WSL_COMMAND = "wsl.exe"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def build_child_argv(child_executable: str | os.PathLike[str], run_id: str) -> list[str]:
    """Build the only per-run Linux command that crosses the WT boundary."""

    canonical_run_id = _validate_run_id_for_cli(run_id)
    child = str(Path(child_executable).expanduser().resolve(strict=False))
    if not child:
        raise UnsupportedCapability("the trusted child executable path is empty")
    return [child, "child", canonical_run_id]


def build_windows_argv(
    wt_launcher_executable: str,
    profile_id: str,
    distribution: str,
    child_executable: str,
    run_id: str,
) -> list[str]:
    """Build the direct Windows Terminal to WSL argv array."""

    child_argv = build_child_argv(child_executable, run_id)
    return [
        str(wt_launcher_executable),
        "-w",
        "last",
        "new-tab",
        "--profile",
        profile_id,
        WINDOWS_WSL_COMMAND,
        "--distribution",
        distribution,
        "--exec",
        *child_argv,
    ]


def build_codex_argv(
    context_mode: str,
    cwd: str | os.PathLike[str],
    model: str,
    effort: str,
    *,
    handoff_content: str,
    source_thread_id: str | None = None,
    fork_prompt: str | None = None,
    codex_executable: str = "codex",
) -> list[str]:
    """Build the Linux Codex argv without shell quoting or interpolation."""

    _validate_context(context_mode)
    if not isinstance(handoff_content, str):
        raise ValueError("handoff_content must be text")
    canonical_cwd = str(Path(cwd).expanduser().resolve(strict=False))
    config = f'model_reasoning_effort="{effort}"'
    if context_mode == "plan":
        return [
            str(codex_executable),
            "-C",
            canonical_cwd,
            "-m",
            model,
            "-c",
            config,
            handoff_content,
        ]
    if source_thread_id is None or fork_prompt is None:
        raise ValueError("fork context requires a source thread and fork prompt")
    return [
        str(codex_executable),
        "fork",
        "-C",
        canonical_cwd,
        "-m",
        model,
        "-c",
        config,
        validate_thread_id(source_thread_id),
        fork_prompt,
    ]


def build_fork_prompt(run_id: str, handoff_path: str | os.PathLike[str]) -> str:
    """Build the small prompt used to fork a source thread."""

    canonical_run_id = _validate_run_id_for_cli(run_id)
    path = str(Path(handoff_path).expanduser().resolve(strict=False))
    marker = run_marker(canonical_run_id)
    return (
        f"{marker}\n\n"
        "This is the Codex Flow execution fork. Read and follow the complete "
        f"absolute handoff at {path}. Implement the approved plan there and "
        "use its completion envelope instructions."
    )


def run_marker(run_id: str) -> str:
    return f'<codex_flow_run run_id="{_validate_run_id_for_cli(run_id)}" version="1" />'


def generate_handoff(
    *,
    run_id: str,
    source_thread_id: str,
    cwd: str,
    model: str,
    effort: str,
    context_mode: str,
    plan_sha256: str,
    plan_text: str,
    repository: Mapping[str, Any],
    artifacts: ArtifactPaths,
) -> str:
    """Render the complete, deterministic execution handoff."""

    canonical_run_id = _validate_run_id_for_cli(run_id)
    source = validate_thread_id(source_thread_id)
    _validate_context(context_mode)
    validate_sha256(plan_sha256, "plan_sha256")
    if not isinstance(plan_text, str):
        raise FailedPrecondition("preflight did not return an approved plan text")

    marker = run_marker(canonical_run_id)
    report_json = json.dumps(
        {
            "schema_version": 1,
            "status": "<completed|partial|blocked>",
            "summary": "",
            "files_changed": [],
            "validation": [
                {"command": "", "exit_code": None, "outcome": ""}
            ],
            "deviations": [],
            "unresolved_issues": [],
            "recommended_follow_up": [],
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    plan_block = plan_text if plan_text.endswith("\n") else plan_text + "\n"
    repository_root = repository.get("repository_root")
    branch = repository.get("branch")
    head = repository.get("head")
    dirty = repository.get("dirty")
    is_git = repository.get("is_git_repository")
    fingerprint = repository.get("baseline_fingerprint")
    return (
        f"{marker}\n\n"
        "# Codex Flow execution handoff\n\n"
        "## Role\n\n"
        "You are the execution agent. Implement the approved plan in this "
        "handoff completely and report the work using the best-effort envelope "
        "below.\n\n"
        "## Launch facts\n\n"
        f"- Run ID: `{canonical_run_id}`\n"
        f"- Source thread: `{source}`\n"
        f"- Working directory: `{cwd}`\n"
        f"- Model: `{model}`\n"
        f"- Reasoning effort: `{effort}`\n"
        f"- Context mode: `{context_mode}`\n"
        f"- Approved plan SHA-256: `{plan_sha256}`\n"
        f"- Repository root: `{repository_root}`\n"
        f"- Branch: `{branch}`\n"
        f"- HEAD: `{head}`\n"
        f"- Git repository: `{is_git}`\n"
        f"- Dirty at launch: `{dirty}`\n"
        f"- Baseline fingerprint: `{fingerprint}`\n\n"
        "## Guardrails\n\n"
        "Preserve pre-existing user work. Do not discard, reset, overwrite, or "
        "reformat unrelated changes. Keep all edits within the approved plan; "
        "avoid unrelated files and unrelated behavior.\n\n"
        "## Approved plan\n\n"
        f"{plan_block}\n"
        "## Validation and completion expectations\n\n"
        "Implement the approved plan, run the relevant tests and validation "
        "checks, inspect the resulting repository state, and explain any "
        "deviations or unresolved issues. Repository state and tests remain "
        "authoritative. The following report envelope is best effort only.\n\n"
        f"Manifest: `{artifacts.manifest}`\n"
        f"Plan artifact: `{artifacts.plan}`\n"
        f"Handoff artifact: `{artifacts.handoff}`\n\n"
        "## Best-effort completion report\n\n"
        f"<codex_flow_report run_id=\"{canonical_run_id}\">\n"
        f"{report_json}\n"
        "</codex_flow_report>\n\n"
        "The completion envelope is best effort. Repository state and tests "
        "remain authoritative even when the envelope is absent or incomplete.\n"
        "Replace the status placeholder with exactly one of completed, partial, "
        "or blocked: use completed only when the approved plan is implemented "
        "and validation passes; partial when useful work is complete but some "
        "scope or validation remains; and blocked when a precondition or "
        "external issue prevents meaningful completion.\n"
    )


@dataclass(frozen=True)
class LaunchArtifacts:
    run_dir: Path
    manifest: RunManifest
    plan_text: str
    handoff_text: str


@dataclass(frozen=True)
class LaunchResult:
    run_id: str
    context_mode: str
    paths: ArtifactPaths
    child_argv: tuple[str, ...]
    windows_argv: tuple[str, ...]
    codex_argv_preview: tuple[Any, ...]
    warnings: tuple[str, ...] = ()
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": "dry-run" if self.dry_run else "dispatched",
            "dry_run": self.dry_run,
            "run_id": self.run_id,
            "context": self.context_mode,
            "paths": self.paths.to_dict(),
            "child_argv": list(self.child_argv),
            "windows_argv": list(self.windows_argv),
            "codex_argv_preview": list(self.codex_argv_preview),
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True)
class WindowsBoundary:
    wt_launcher_executable: str
    profile_id: str
    distribution: str
    child_executable: str

    def child_argv(self, run_id: str) -> list[str]:
        return build_child_argv(self.child_executable, run_id)

    def windows_argv(self, run_id: str) -> list[str]:
        return build_windows_argv(
            self.wt_launcher_executable,
            self.profile_id,
            self.distribution,
            self.child_executable,
            run_id,
        )


def resolve_windows_boundary(
    environ: Mapping[str, str],
    *,
    child_executable: str | os.PathLike[str] | None = None,
    wt_executable: str | None = None,
    wsl_capability_executable: str | None = None,
    executable_resolver: Callable[[str], str | None] | None = None,
) -> WindowsBoundary:
    """Resolve only trusted launcher configuration for the WT boundary."""

    profile_id = environ.get("WT_PROFILE_ID")
    distribution = environ.get("WSL_DISTRO_NAME")
    if not profile_id:
        raise UnsupportedCapability("WT_PROFILE_ID is not set")
    if not distribution:
        raise UnsupportedCapability("WSL_DISTRO_NAME is not set")
    resolver = shutil.which if executable_resolver is None else executable_resolver
    resolved_wt_launcher = wt_executable or resolver("wt.exe")
    if not resolved_wt_launcher:
        raise UnsupportedCapability("wt.exe is not available")
    resolved_wsl_capability = wsl_capability_executable or resolver("wsl.exe")
    if not resolved_wsl_capability:
        raise UnsupportedCapability("wsl.exe is not available")
    if child_executable is None:
        child_executable = development_child_executable()
    child = str(Path(child_executable).expanduser().resolve(strict=False))
    if not child:
        raise UnsupportedCapability("the development child executable path is empty")
    child_path = Path(child)
    if not child_path.is_file() or not os.access(child_path, os.X_OK):
        raise UnsupportedCapability(
            f"child executable is missing or not executable: {child_path}"
        )
    return WindowsBoundary(
        wt_launcher_executable=str(resolved_wt_launcher),
        profile_id=profile_id,
        distribution=distribution,
        child_executable=child,
    )


def development_child_executable() -> Path:
    """Return the absolute Phase 02 repository development shim."""

    return (Path(__file__).resolve().parents[2] / "bin" / "codex-flow").resolve(strict=False)


def _validate_context(value: str) -> str:
    if value not in CONTEXT_MODES:
        raise InvalidCLIUsage("context must be plan or fork")
    return value


def _validate_run_id_for_cli(value: str) -> str:
    try:
        return validate_run_id(value)
    except (TypeError, ValueError) as error:
        raise InvalidCLIUsage("run_id must be a canonical UUIDv4 string") from error


def _validate_launch_hash(value: str, field_name: str) -> str:
    try:
        return validate_sha256(value, field_name)
    except (TypeError, ValueError) as error:
        raise InvalidCLIUsage(str(error)) from error


def _validate_launch_args(
    thread_id: str,
    model: str,
    effort: str,
    baseline_fingerprint: str,
    plan_sha256: str,
    context_mode: str,
    confirm_dirty: str | None,
) -> tuple[str, str, str, str, str, str, str | None]:
    try:
        thread = validate_thread_id(thread_id)
    except (TypeError, ValueError, ContractError) as error:
        raise InvalidCLIUsage("thread must be a canonical UUID") from error
    for value, field_name in ((model, "model"), (effort, "effort")):
        if not isinstance(value, str) or not value.strip():
            raise InvalidCLIUsage(f"{field_name} must be a non-empty string")
    baseline = _validate_launch_hash(baseline_fingerprint, "baseline_fingerprint")
    plan = _validate_launch_hash(plan_sha256, "plan_sha256")
    _validate_context(context_mode)
    dirty = None if confirm_dirty is None else _validate_launch_hash(confirm_dirty, "confirm_dirty")
    return thread, model, effort, baseline, plan, context_mode, dirty


def _preflight_failure(result: PreflightResult) -> None:
    if result.ready:
        return
    detail = "; ".join(result.blockers) or "preflight did not approve this handoff"
    if result.exit_code == 4:
        raise UnsupportedCapability(detail)
    raise FailedPrecondition(detail)


def _checked_preflight_state(
    result: PreflightResult,
    *,
    expected_plan_sha256: str,
    expected_baseline_fingerprint: str,
    confirm_dirty: str | None,
) -> tuple[str, str, Mapping[str, Any], tuple[str, ...]]:
    """Check all mutable evidence immediately before artifact creation."""

    _preflight_failure(result)
    if result.native_mode != "default":
        raise FailedPrecondition("native collaboration mode must be default")
    plan = result.plan
    plan_text = plan.get("text")
    if not isinstance(plan_text, str):
        raise FailedPrecondition("preflight did not return an approved plan")
    extracted_hash = sha256_text(plan_text)
    if plan.get("sha256") != extracted_hash:
        raise FailedPrecondition("preflight plan SHA-256 evidence is inconsistent")
    if extracted_hash != expected_plan_sha256:
        raise FailedPrecondition("approved plan SHA-256 is stale or mismatched")
    repository = result.repository
    current_fingerprint = repository.get("baseline_fingerprint")
    if current_fingerprint != expected_baseline_fingerprint:
        raise FailedPrecondition("repository baseline fingerprint is stale or mismatched")
    if repository.get("is_git_repository") is True and repository.get("dirty") is True:
        if confirm_dirty != current_fingerprint:
            raise FailedPrecondition(
                "dirty Git launch requires --confirm-dirty equal to the current baseline fingerprint"
            )
    return plan_text, extracted_hash, repository, tuple(result.warnings)


def build_manifest(
    *,
    run_id: str,
    source_thread_id: str,
    repository: Mapping[str, Any],
    context_mode: str,
    model: str,
    effort: str,
    codex_executable: str,
    plan_sha256: str,
    artifacts: ArtifactPaths,
    source_rollout_path: str | os.PathLike[str] | None = None,
    created_at: str | None = None,
) -> RunManifest:
    """Build the immutable schema-v1 launch manifest."""

    canonical_run_id = validate_run_id(run_id)
    repository_baseline = RepositoryBaseline(
        working_directory=repository.get("requested_cwd") or repository.get("working_directory"),
        repository_root=repository.get("repository_root"),
        branch=repository.get("branch"),
        head=repository.get("head"),
        dirty=repository.get("dirty"),
        is_git_repository=repository.get("is_git_repository", False),
        baseline_fingerprint=repository.get("baseline_fingerprint"),
    )
    return RunManifest(
        schema_version=1,
        identity=RunIdentity(run_id=canonical_run_id),
        source_thread=ThreadReference(
            thread_id=source_thread_id,
            source_kind="root",
            rollout_path=source_rollout_path,
        ),
        repository=repository_baseline,
        handoff=HandoffSelection(
            context_mode=context_mode,
            model=model,
            reasoning_effort=effort,
        ),
        codex_executable=codex_executable,
        plan_sha256=plan_sha256,
        artifacts=artifacts,
        created_at=utc_timestamp() if created_at is None else created_at,
    )


def persist_run_artifacts(
    run_dir: str | os.PathLike[str],
    *,
    plan_text: str,
    handoff_text: str,
    manifest: RunManifest,
) -> LaunchArtifacts:
    """Persist plan and handoff, then publish the manifest as the commit marker."""

    directory = Path(run_dir).expanduser().resolve(strict=False)
    created = False
    committed = False
    try:
        directory.mkdir(parents=True, exist_ok=False)
        created = True
        atomic_write_text(manifest.artifacts.plan, plan_text, overwrite=False)
        atomic_write_text(manifest.artifacts.handoff, handoff_text, overwrite=False)
        atomic_write_json(manifest.artifacts.manifest, manifest.to_dict(), overwrite=False)
        committed = True
        return LaunchArtifacts(directory, manifest, plan_text, handoff_text)
    except FileExistsError as error:
        if not created:
            raise FailedPrecondition(f"run directory already exists: {directory}") from error
        raise
    except Exception:
        raise
    finally:
        all_artifacts_published = all(
            Path(path).is_file()
            for path in (
                manifest.artifacts.plan,
                manifest.artifacts.handoff,
                manifest.artifacts.manifest,
            )
        )
        if created and not committed and not all_artifacts_published:
            shutil.rmtree(directory, ignore_errors=True)


def _resolve_codex(
    resolver: Callable[[str], str | None] | None,
) -> str:
    resolved = (shutil.which if resolver is None else resolver)("codex")
    if not resolved:
        raise UnsupportedCapability("codex executable is not available")
    candidate = Path(resolved).expanduser()
    try:
        executable = candidate.resolve(strict=True)
    except OSError as error:
        raise UnsupportedCapability(
            f"codex executable is missing or cannot be resolved: {candidate}"
        ) from error
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise UnsupportedCapability(
            f"codex executable is missing or not executable: {executable}"
        )
    return str(executable)


def _sanitize_codex_argv(argv: Sequence[str], content: str, content_type: str) -> tuple[Any, ...]:
    if not argv:
        return ()
    return tuple(argv[:-1]) + (
        {
            "content_type": content_type,
            "sha256": sha256_text(content),
            "byte_length": len(content.encode("utf-8")),
        },
    )


def _command_result(runner: CommandRunner | Any, argv: Sequence[str]) -> CommandResult:
    try:
        result = runner.run(argv)
    except AttributeError:
        result = runner(argv)
    if isinstance(result, CommandResult):
        return result
    try:
        return CommandResult(int(result.returncode), str(result.stdout), str(result.stderr))
    except (AttributeError, TypeError, ValueError) as error:
        raise ExternalCommandFailure("the injected Terminal runner returned an invalid result") from error


def _manual_child_command(boundary: WindowsBoundary, run_id: str) -> str:
    return shlex.join(boundary.child_argv(run_id))


def launch(
    *,
    thread_id: str,
    cwd: str | os.PathLike[str],
    model: str,
    effort: str,
    baseline_fingerprint: str,
    plan_sha256: str,
    context_mode: str = "plan",
    confirm_dirty: str | None = None,
    dry_run: bool = False,
    environ: Mapping[str, str] | None = None,
    preflight_runner: Callable[..., PreflightResult] | None = None,
    terminal_runner: CommandRunner | Any | None = None,
    child_executable: str | os.PathLike[str] | None = None,
    wt_executable: str | None = None,
    wsl_capability_executable: str | None = None,
    executable_resolver: Callable[[str], str | None] | None = None,
    run_id_factory: Callable[[], UUID | str] = uuid4,
) -> LaunchResult:
    """Run preflight, persist a fresh handoff, and launch the WT boundary."""

    (
        thread,
        selected_model,
        selected_effort,
        expected_baseline,
        expected_plan,
        context,
        dirty_confirmation,
    ) = _validate_launch_args(
        thread_id,
        model,
        effort,
        baseline_fingerprint,
        plan_sha256,
        context_mode,
        confirm_dirty,
    )
    env = os.environ if environ is None else environ
    preflight = run_preflight if preflight_runner is None else preflight_runner
    result = preflight(
        thread,
        cwd=cwd,
        environ=env,
        model=selected_model,
        effort=selected_effort,
    )
    plan_text, fresh_plan_sha, repository, warnings = _checked_preflight_state(
        result,
        expected_plan_sha256=expected_plan,
        expected_baseline_fingerprint=expected_baseline,
        confirm_dirty=dirty_confirmation,
    )
    codex = _resolve_codex(executable_resolver)
    run_id = _validate_run_id_for_cli(str(run_id_factory()))
    paths = resolve_paths(env)
    run_dir = paths.run_path(run_id)
    artifacts = ArtifactPaths(
        manifest=run_dir / "manifest.json",
        plan=run_dir / "plan.md",
        handoff=run_dir / "handoff.md",
        execution=run_dir / "execution.json",
        report=run_dir / "report.json",
        audit=run_dir / "audit.json",
    )
    manifest = build_manifest(
        run_id=run_id,
        source_thread_id=thread,
        repository=repository,
        context_mode=context,
        model=selected_model,
        effort=selected_effort,
        codex_executable=codex,
        plan_sha256=fresh_plan_sha,
        artifacts=artifacts,
        source_rollout_path=result.source.get("rollout_path"),
    )
    handoff = generate_handoff(
        run_id=run_id,
        source_thread_id=thread,
        cwd=manifest.repository.working_directory,
        model=selected_model,
        effort=selected_effort,
        context_mode=context,
        plan_sha256=fresh_plan_sha,
        plan_text=plan_text,
        repository=repository,
        artifacts=artifacts,
    )
    fork_prompt = build_fork_prompt(run_id, artifacts.handoff)

    if dry_run:
        boundary = resolve_windows_boundary(
            env,
            child_executable=child_executable,
            wt_executable=wt_executable,
            wsl_capability_executable=wsl_capability_executable,
            executable_resolver=executable_resolver,
        )
        codex_argv = build_codex_argv(
            context,
            manifest.repository.working_directory,
            selected_model,
            selected_effort,
            handoff_content=handoff,
            source_thread_id=thread,
            fork_prompt=fork_prompt,
            codex_executable=codex,
        )
        content_type = "handoff" if context == "plan" else "fork_prompt"
        return LaunchResult(
            run_id=run_id,
            context_mode=context,
            paths=artifacts,
            child_argv=tuple(boundary.child_argv(run_id)),
            windows_argv=tuple(boundary.windows_argv(run_id)),
            codex_argv_preview=_sanitize_codex_argv(codex_argv, codex_argv[-1], content_type),
            warnings=warnings,
            dry_run=True,
        )

    try:
        paths.runs.mkdir(parents=True, exist_ok=True)
        persist_run_artifacts(
            run_dir,
            plan_text=plan_text,
            handoff_text=handoff,
            manifest=manifest,
        )
    except FailedPrecondition:
        raise
    except OSError as error:
        raise FailedPrecondition(f"could not persist run artifacts in {run_dir}: {error}") from error

    try:
        boundary = resolve_windows_boundary(
            env,
            child_executable=child_executable,
            wt_executable=wt_executable,
            wsl_capability_executable=wsl_capability_executable,
            executable_resolver=executable_resolver,
        )
    except UnsupportedCapability as error:
        raise UnsupportedCapability(
            f"Windows Terminal launch is unavailable: {error}. "
            f"Safe manual Linux child command: {_manual_child_command_for_path(run_id, boundary_child=child_executable)}"
        ) from error

    windows_argv = boundary.windows_argv(run_id)
    child_argv = boundary.child_argv(run_id)
    runner = SubprocessCommandRunner() if terminal_runner is None else terminal_runner
    try:
        terminal_result = _command_result(runner, windows_argv)
    except FileNotFoundError as error:
        raise UnsupportedCapability(
            "Windows Terminal executable could not be started. "
            f"Safe manual Linux child command: {_manual_child_command_for_path(run_id, boundary_child=boundary.child_executable)}"
        ) from error
    if terminal_result.returncode != 0:
        detail = terminal_result.stderr.strip() or terminal_result.stdout.strip() or "no diagnostic output"
        raise ExternalCommandFailure(
            f"Windows Terminal launch failed with exit status {terminal_result.returncode}: {detail}"
        )
    return LaunchResult(
        run_id=run_id,
        context_mode=context,
        paths=artifacts,
        child_argv=tuple(child_argv),
        windows_argv=tuple(windows_argv),
        codex_argv_preview=(),
        warnings=warnings,
    )


def _manual_child_command_for_path(
    run_id: str,
    *,
    boundary_child: str | os.PathLike[str] | None,
) -> str:
    child = development_child_executable() if boundary_child is None else boundary_child
    return shlex.join(build_child_argv(str(child), run_id))


def _read_utf8(path: Path, label: str) -> bytes:
    if path.is_symlink():
        raise ContractError(f"{label} is redirected through a symlink")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ContractError(f"cannot read {label}: {path}") from error


def _validate_child_manifest_paths(
    document: Mapping[str, Any],
    manifest: RunManifest,
    expected: Mapping[str, Path],
) -> None:
    raw_artifacts = document.get("artifacts")
    if not isinstance(raw_artifacts, Mapping):
        raise ContractError("manifest artifacts must be an object")
    for field_name, expected_path in expected.items():
        raw_value = raw_artifacts.get(field_name)
        if raw_value != str(expected_path):
            raise ContractError(
                f"manifest artifact {field_name} must equal the canonical path {expected_path}"
            )
        actual = getattr(manifest.artifacts, field_name)
        if actual != str(expected_path):
            raise ContractError(
                f"manifest artifact {field_name} was redirected from its canonical path"
            )


def _validate_manifest_codex_path(
    document: Mapping[str, Any],
    manifest: RunManifest,
) -> str:
    raw_value = document.get("codex_executable")
    if raw_value != manifest.codex_executable:
        raise ContractError(
            "manifest codex_executable must be a canonical absolute path"
        )
    executable = Path(manifest.codex_executable)
    if executable.is_symlink():
        raise ContractError("manifest codex executable is redirected through a symlink")
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise UnsupportedCapability(
            f"manifest codex executable is missing or not executable: {executable}"
        )
    return manifest.codex_executable
def load_run_manifest(
    run_id: str,
    *,
    paths: FlowPaths,
) -> tuple[RunManifest, str, bytes]:
    """Load and strictly validate one exact run directory before child exec."""

    canonical_run_id = _validate_run_id_for_cli(run_id)
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
    if any(path.is_symlink() for path in expected.values()):
        raise ContractError("run artifacts cannot be redirected through symlinks")
    manifest_bytes = _read_utf8(expected["manifest"], "manifest.json")
    try:
        document = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError("manifest.json is not valid UTF-8 JSON") from error
    try:
        manifest = RunManifest.from_dict(document)
    except (TypeError, ValueError) as error:
        raise ContractError(f"manifest.json is invalid: {error}") from error
    if manifest.identity.run_id != canonical_run_id:
        raise ContractError("manifest identity run_id does not match the requested run ID")
    _validate_child_manifest_paths(document, manifest, expected)
    _validate_manifest_codex_path(document, manifest)
    plan_bytes = _read_utf8(expected["plan"], "plan.md")
    handoff_bytes = _read_utf8(expected["handoff"], "handoff.md")
    try:
        handoff_bytes.decode("utf-8")
        plan_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("plan.md and handoff.md must be valid UTF-8") from error
    if sha256_bytes(plan_bytes) != manifest.plan_sha256:
        raise ContractError("plan.md SHA-256 does not match manifest plan_sha256")
    return manifest, handoff_bytes.decode("utf-8"), plan_bytes


def run_child(
    run_id: str,
    *,
    environ: Mapping[str, str] | None = None,
    paths: FlowPaths | None = None,
    exec_fn: Callable[[Sequence[str]], Any] | None = None,
    chdir_fn: Callable[[str | os.PathLike[str]], Any] | None = None,
) -> int:
    """Validate one run and replace the child with the selected Codex argv."""

    canonical_run_id = _validate_run_id_for_cli(run_id)
    env = os.environ if environ is None else environ
    resolved_paths = resolve_paths(env) if paths is None else paths
    manifest, handoff, plan_bytes = load_run_manifest(canonical_run_id, paths=resolved_paths)
    cwd = Path(manifest.repository.working_directory)
    if not cwd.is_dir():
        raise FailedPrecondition(f"manifest working directory is not a directory: {cwd}")
    change_directory = os.chdir if chdir_fn is None else chdir_fn
    try:
        change_directory(cwd)
    except OSError as error:
        raise FailedPrecondition(f"could not change to manifest working directory: {cwd}") from error
    fork_prompt = build_fork_prompt(canonical_run_id, manifest.artifacts.handoff)
    argv = build_codex_argv(
        manifest.handoff.context_mode,
        str(cwd),
        manifest.handoff.model,
        manifest.handoff.reasoning_effort,
        handoff_content=handoff,
        source_thread_id=manifest.source_thread.thread_id,
        fork_prompt=fork_prompt,
        codex_executable=manifest.codex_executable,
    )
    # Keep the variable live through construction so a future executor cannot
    # accidentally substitute a decoded or transformed plan representation.
    if sha256_bytes(plan_bytes) != manifest.plan_sha256:
        raise ContractError("plan.md SHA-256 changed during child validation")
    if exec_fn is None:
        try:
            os.execv(argv[0], argv)
        except FileNotFoundError as error:
            raise UnsupportedCapability("codex executable is not available") from error
        except OSError as error:
            raise ExternalCommandFailure(f"could not exec Codex: {error}") from error
    else:
        try:
            exec_fn(argv)
        except FileNotFoundError as error:
            raise UnsupportedCapability("codex executable is not available") from error
        except OSError as error:
            raise ExternalCommandFailure(f"could not exec Codex: {error}") from error
    return 0


__all__ = [
    "CONTEXT_MODES",
    "LaunchArtifacts",
    "LaunchResult",
    "WindowsBoundary",
    "WINDOWS_WSL_COMMAND",
    "build_child_argv",
    "build_codex_argv",
    "build_fork_prompt",
    "build_manifest",
    "build_windows_argv",
    "development_child_executable",
    "generate_handoff",
    "launch",
    "load_run_manifest",
    "persist_run_artifacts",
    "resolve_windows_boundary",
    "run_child",
    "run_marker",
    "sha256_bytes",
    "sha256_text",
]
