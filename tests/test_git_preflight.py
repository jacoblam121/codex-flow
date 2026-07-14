from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from codex_flow.errors import ExternalCommandFailure, UnsupportedCapability
from codex_flow.models import CommandResult, SubprocessCommandRunner
from codex_flow.preflight import run_preflight
from codex_flow.git import inspect_repository


THREAD = "019f55cc-b6fb-79d2-b1d2-27ee49aaf2ac"


class ModelRunner:
    def run(self, argv):
        assert tuple(argv) == ("codex", "debug", "models", "--bundled")
        return CommandResult(
            0,
            json.dumps(
                {
                    "models": [
                        {
                            "slug": "gpt-test",
                            "supported_reasoning_levels": [{"effort": "low"}, {"effort": "max"}],
                        }
                    ]
                }
            ),
            "",
        )


class UnusableModelRunner:
    def run(self, argv):
        return CommandResult(0, json.dumps({"models": []}), "")


class CapturingGitRunner:
    def __init__(self):
        self.calls = []
        self.delegate = SubprocessCommandRunner()

    def run(self, argv, cwd=None):
        self.calls.append(tuple(argv))
        return self.delegate.run(argv, cwd=cwd)


class ScriptedGitRunner:
    def __init__(self, head_returncode=1):
        self.head_returncode = head_returncode
        self.calls = []

    def run(self, argv, cwd=None):
        argv = tuple(argv)
        self.calls.append(argv)
        if argv == ("git", "rev-parse", "--is-inside-work-tree"):
            return CommandResult(0, "true\n", "")
        if argv == ("git", "rev-parse", "--show-toplevel"):
            return CommandResult(0, str(cwd) + "\n", "")
        if argv == ("git", "rev-parse", "--git-common-dir"):
            return CommandResult(0, ".git\n", "")
        if argv == ("git", "symbolic-ref", "--quiet", "--short", "HEAD"):
            return CommandResult(0, "main\n", "")
        if argv == ("git", "rev-parse", "--verify", "--quiet", "HEAD"):
            return CommandResult(self.head_returncode, "", "")
        if argv == (
            "git",
            "--no-optional-locks",
            "-c",
            "core.quotePath=false",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            return CommandResult(0, "", "")
        raise AssertionError(argv)


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
    )


def init_repo(path: Path) -> None:
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Codex Flow Test")
    git(path, "config", "user.email", "codex-flow@example.invalid")


def commit_repo(path: Path, text: str = "content") -> str:
    (path / "file.txt").write_text(text, encoding="utf-8")
    git(path, "add", "file.txt")
    git(path, "commit", "-m", "initial")
    return git(path, "rev-parse", "HEAD").stdout.strip()


def test_git_fingerprint_is_stable_and_changes_with_status_head_and_branch(tmp_path):
    repo = tmp_path / "repo with spaces"
    init_repo(repo)
    unborn = inspect_repository(repo)
    assert unborn.is_git_repository
    assert unborn.unborn
    assert unborn.head is None

    first_head = commit_repo(repo)
    clean = inspect_repository(repo)
    repeated = inspect_repository(repo)
    assert clean.to_dict() == repeated.to_dict()
    assert clean.baseline_fingerprint == repeated.baseline_fingerprint
    assert clean.head == first_head
    assert not clean.dirty

    (repo / "unicode é name.txt").write_text("x", encoding="utf-8")
    dirty = inspect_repository(repo)
    assert dirty.dirty
    assert any("unicode é name.txt" in status for status in dirty.porcelain_status)
    assert dirty.baseline_fingerprint != clean.baseline_fingerprint

    git(repo, "add", ".")
    git(repo, "commit", "-m", "unicode")
    second_head = inspect_repository(repo)
    assert second_head.head != first_head
    assert second_head.baseline_fingerprint != dirty.baseline_fingerprint

    git(repo, "checkout", "--detach", "HEAD")
    detached = inspect_repository(repo)
    assert detached.detached
    assert detached.baseline_fingerprint != second_head.baseline_fingerprint


def test_worktree_root_and_non_git_reduced_audit(tmp_path):
    repo = tmp_path / "repo"
    init_repo(repo)
    commit_repo(repo)
    worktree = tmp_path / "worktree"
    git(repo, "worktree", "add", "-b", "feature", str(worktree))
    inspection = inspect_repository(worktree)
    assert inspection.repository_root == worktree.resolve().as_posix()
    assert inspection.branch == "feature"

    plain = tmp_path / "plain"
    plain.mkdir()
    reduced = inspect_repository(plain)
    assert not reduced.is_git_repository
    assert reduced.repository_root is None
    assert reduced.dirty is None
    assert reduced.to_dict()["dirty"] is None
    assert reduced.baseline_fingerprint
    assert any("reduced audit" in warning for warning in reduced.warnings)


def test_git_status_disables_optional_locks(tmp_path):
    repo = tmp_path / "repo"
    init_repo(repo)
    commit_repo(repo)
    runner = CapturingGitRunner()
    inspect_repository(repo, runner=runner)
    status_calls = [call for call in runner.calls if "status" in call]
    assert len(status_calls) == 1
    assert "--no-optional-locks" in status_calls[0]


def test_missing_git_is_external_failure(tmp_path):
    class MissingGit:
        def run(self, argv, cwd=None):
            raise FileNotFoundError("git")

    with pytest.raises(ExternalCommandFailure, match="Git executable"):
        inspect_repository(tmp_path, runner=MissingGit())


def test_unexpected_git_probe_failure_is_external(tmp_path):
    class DubiousOwnership:
        def run(self, argv, cwd=None):
            assert tuple(argv) == ("git", "rev-parse", "--is-inside-work-tree")
            return CommandResult(
                128,
                "",
                "fatal: detected dubious ownership in repository at '/tmp/repo'",
            )

    with pytest.raises(ExternalCommandFailure, match="dubious ownership"):
        inspect_repository(tmp_path, runner=DubiousOwnership())


def test_expected_unborn_head_result_is_accepted_and_unexpected_failure_is_external(tmp_path):
    expected = ScriptedGitRunner(head_returncode=1)
    inspection = inspect_repository(tmp_path, runner=expected)
    assert inspection.unborn
    assert inspection.head is None

    unexpected = ScriptedGitRunner(head_returncode=2)
    with pytest.raises(ExternalCommandFailure, match="rev-parse --verify"):
        inspect_repository(tmp_path, runner=unexpected)


def test_preflight_is_deterministic_and_respects_explicit_cwd_over_caller(tmp_path):
    codex_home = tmp_path / "codex"
    rollout = codex_home / "sessions" / "2026" / "07" / "12" / f"rollout-x-{THREAD}.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_meta", "payload": {"id": THREAD, "session_id": THREAD, "cwd": "/rollout", "thread_source": "user"}}),
                json.dumps({"type": "turn_context", "payload": {"collaboration_mode": {"mode": "default"}}}),
                json.dumps({"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "Plan", "text": "# Stable"}}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    result = run_preflight(
        THREAD,
        cwd=explicit,
        caller_cwd=tmp_path,
        environ={"CODEX_HOME": str(codex_home)},
        command_runner=ModelRunner(),
    )
    repeated = run_preflight(
        THREAD,
        cwd=explicit,
        caller_cwd=tmp_path,
        environ={"CODEX_HOME": str(codex_home)},
        command_runner=ModelRunner(),
    )
    assert result.to_json() == repeated.to_json()
    assert result.source["rollout_path"] == str(rollout.resolve())
    assert result.repository["requested_cwd"] == str(explicit.resolve())
    assert result.source["rollout_cwd"] == "/rollout"
    assert any("differs from requested" in warning for warning in result.warnings)
    assert result.ready
    assert result.exit_code == 0
    assert result.plan["sha256"]
    assert result.supported_models == ({"slug": "gpt-test", "efforts": ["low", "max"]},)


def test_preflight_plan_mode_and_selection_are_blocked_without_state(tmp_path):
    codex_home = tmp_path / "codex"
    rollout = codex_home / "sessions" / "2026" / "07" / "12" / f"rollout-x-{THREAD}.jsonl"
    rollout.parent.mkdir(parents=True)
    records = [
        {"type": "session_meta", "payload": {"id": THREAD, "session_id": THREAD, "cwd": str(tmp_path), "thread_source": "user"}},
        {"type": "turn_context", "payload": {"collaboration_mode": {"mode": "plan"}}},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "Plan", "text": "plan"}}},
    ]
    rollout.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    result = run_preflight(
        THREAD,
        cwd=tmp_path,
        environ={"CODEX_HOME": str(codex_home)},
        model="gpt-test",
        effort="unsupported",
        command_runner=ModelRunner(),
    )
    assert not result.ready
    assert result.exit_code == 4
    assert any("native collaboration mode" in blocker for blocker in result.blockers)
    assert any("unsupported model/effort" in blocker for blocker in result.blockers)


def test_preflight_unusable_catalog_cannot_be_ready(tmp_path):
    codex_home = tmp_path / "codex"
    rollout = codex_home / "sessions" / "2026" / "07" / "12" / f"rollout-x-{THREAD}.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_meta", "payload": {"id": THREAD, "session_id": THREAD, "thread_source": "user"}}),
                json.dumps({"type": "turn_context", "payload": {"collaboration_mode": {"mode": "default"}}}),
                json.dumps({"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "Plan", "text": "plan"}}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(UnsupportedCapability, match="empty"):
        run_preflight(
            THREAD,
            cwd=tmp_path,
            environ={"CODEX_HOME": str(codex_home)},
            command_runner=UnusableModelRunner(),
        )
