"""Read-only, shell-free Git/environment inspection for preflight."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import RepositoryBaseline
from .errors import ExternalCommandFailure
from .models import CommandResult, CommandRunner, SubprocessCommandRunner


def _line(value: str) -> str:
    return value.rstrip("\r\n")


def _run(runner: CommandRunner | Any, argv: Sequence[str], cwd: Path) -> CommandResult:
    try:
        result = runner.run(argv, cwd=cwd)
    except AttributeError:
        try:
            result = runner(argv, cwd)
        except TypeError:
            result = runner(argv)
    if isinstance(result, CommandResult):
        return result
    try:
        return CommandResult(int(result.returncode), str(result.stdout), str(result.stderr))
    except (AttributeError, TypeError, ValueError) as error:
        raise ExternalCommandFailure("the injected Git runner returned an invalid result") from error


@dataclass(frozen=True)
class GitInspection:
    requested_cwd: str
    is_git_repository: bool
    repository_root: str | None
    repository_identity: str | None
    branch: str | None
    detached: bool
    head: str | None
    unborn: bool
    porcelain_status: tuple[str, ...]
    porcelain_text: str
    dirty: bool | None
    baseline_fingerprint: str
    warnings: tuple[str, ...]
    baseline: RepositoryBaseline

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_cwd": self.requested_cwd,
            "is_git_repository": self.is_git_repository,
            "repository_root": self.repository_root,
            "repository_identity": self.repository_identity,
            "branch": self.branch,
            "detached": self.detached,
            "head": self.head,
            "unborn": self.unborn,
            "porcelain_status": list(self.porcelain_status),
            "porcelain_text": self.porcelain_text,
            "dirty": self.dirty,
            "baseline_fingerprint": self.baseline_fingerprint,
        }


def _fingerprint(
    requested_cwd: str,
    repository_identity: str | None,
    branch: str | None,
    detached: bool,
    head: str | None,
    unborn: bool,
    porcelain_text: str,
) -> str:
    document = {
        "requested_cwd": requested_cwd,
        "repository_identity": repository_identity,
        "branch": branch,
        "detached": detached,
        "head": head,
        "unborn": unborn,
        "porcelain_text": porcelain_text,
    }
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _failure(argv: Sequence[str], result: CommandResult) -> ExternalCommandFailure:
    detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
    return ExternalCommandFailure(
        f"{' '.join(argv)} failed with exit status {result.returncode}: {detail}"
    )


def _is_expected_non_git_probe(result: CommandResult) -> bool:
    """Recognize Git's normal outside-repository diagnostic only."""

    if result.returncode == 0:
        return False
    diagnostic = f"{result.stderr}\n{result.stdout}".lower()
    return "not a git repository" in diagnostic


def inspect_repository(
    requested_cwd: str | Path,
    *,
    original_working_directory: str | Path | None = None,
    runner: CommandRunner | Any | None = None,
) -> GitInspection:
    requested = Path(requested_cwd).expanduser().resolve(strict=False)
    if not requested.is_dir():
        raise ExternalCommandFailure(f"requested CWD is not a directory: {requested}")
    runner = SubprocessCommandRunner() if runner is None else runner
    warnings: list[str] = []
    probe_argv = ("git", "rev-parse", "--is-inside-work-tree")
    try:
        probe = _run(runner, probe_argv, requested)
    except FileNotFoundError as error:
        raise ExternalCommandFailure(
            f"could not execute {' '.join(probe_argv)}: Git executable was not found"
        ) from error
    if probe.stderr.strip():
        warnings.append(f"git probe emitted stderr: {probe.stderr.strip()}")
    if _is_expected_non_git_probe(probe):
        warnings.append(
            f"requested CWD {requested} is not a Git worktree; reduced audit is being used"
        )
        fingerprint = _fingerprint(
            str(requested), None, None, False, None, False, ""
        )
        baseline = RepositoryBaseline(
            working_directory=str(requested),
            repository_root=None,
            branch=None,
            head=None,
            dirty=None,
            is_git_repository=False,
            original_working_directory=(
                None
                if original_working_directory is None
                else str(Path(original_working_directory).expanduser().resolve(strict=False))
            ),
            baseline_fingerprint=fingerprint,
        )
        return GitInspection(
            requested_cwd=str(requested),
            is_git_repository=False,
            repository_root=None,
            repository_identity=None,
            branch=None,
            detached=False,
            head=None,
            unborn=False,
            porcelain_status=(),
            porcelain_text="",
            dirty=None,
            baseline_fingerprint=fingerprint,
            warnings=tuple(sorted(set(warnings))),
            baseline=baseline,
        )
    if probe.returncode != 0:
        raise _failure(probe_argv, probe)
    if _line(probe.stdout) != "true":
        raise ExternalCommandFailure(
            f"{' '.join(probe_argv)} returned unexpected output: {probe.stdout.strip()!r}"
        )

    root_argv = ("git", "rev-parse", "--show-toplevel")
    root_result = _run(runner, root_argv, requested)
    if root_result.returncode != 0:
        raise _failure(root_argv, root_result)
    repository_root = str(Path(_line(root_result.stdout)).expanduser().resolve(strict=False))
    git_dir_argv = ("git", "rev-parse", "--git-common-dir")
    git_dir_result = _run(runner, git_dir_argv, requested)
    if git_dir_result.returncode != 0:
        raise _failure(git_dir_argv, git_dir_result)
    raw_git_dir = Path(_line(git_dir_result.stdout))
    if not raw_git_dir.is_absolute():
        raw_git_dir = requested / raw_git_dir
    repository_identity = str(raw_git_dir.expanduser().resolve(strict=False))

    branch_argv = ("git", "symbolic-ref", "--quiet", "--short", "HEAD")
    branch_result = _run(runner, branch_argv, requested)
    if branch_result.returncode == 0:
        branch = _line(branch_result.stdout)
        detached = False
    elif branch_result.returncode == 1:
        branch = None
        detached = True
    else:
        raise _failure(branch_argv, branch_result)
    if branch_result.stderr.strip():
        warnings.append(f"git branch inspection emitted stderr: {branch_result.stderr.strip()}")

    head_argv = ("git", "rev-parse", "--verify", "--quiet", "HEAD")
    head_result = _run(runner, head_argv, requested)
    if head_result.returncode == 0:
        head = _line(head_result.stdout)
        unborn = False
    elif head_result.returncode == 1:
        head = None
        unborn = True
    else:
        raise _failure(head_argv, head_result)
    if head_result.stderr.strip():
        warnings.append(f"git HEAD inspection emitted stderr: {head_result.stderr.strip()}")

    status_argv = (
        "git",
        "--no-optional-locks",
        "-c",
        "core.quotePath=false",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    status_result = _run(runner, status_argv, requested)
    if status_result.returncode != 0:
        raise _failure(status_argv, status_result)
    if status_result.stderr.strip():
        warnings.append(f"git status emitted stderr: {status_result.stderr.strip()}")
    porcelain_text = status_result.stdout
    porcelain_status = tuple(porcelain_text.splitlines()) if porcelain_text else ()
    dirty = bool(porcelain_text)
    fingerprint = _fingerprint(
        str(requested),
        repository_identity,
        branch,
        detached,
        head,
        unborn,
        porcelain_text,
    )
    baseline = RepositoryBaseline(
        working_directory=str(requested),
        repository_root=repository_root,
        branch=branch,
        head=head,
        dirty=dirty,
        is_git_repository=True,
        original_working_directory=(
            None
            if original_working_directory is None
            else str(Path(original_working_directory).expanduser().resolve(strict=False))
        ),
        baseline_fingerprint=fingerprint,
    )
    return GitInspection(
        requested_cwd=str(requested),
        is_git_repository=True,
        repository_root=repository_root,
        repository_identity=repository_identity,
        branch=branch,
        detached=detached,
        head=head,
        unborn=unborn,
        porcelain_status=porcelain_status,
        porcelain_text=porcelain_text,
        dirty=dirty,
        baseline_fingerprint=fingerprint,
        warnings=tuple(sorted(set(warnings))),
        baseline=baseline,
    )


__all__ = ["GitInspection", "inspect_repository"]
