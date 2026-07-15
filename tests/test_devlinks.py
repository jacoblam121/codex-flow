from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import codex_flow.devlinks as devlinks
from codex_flow.devlinks import DevLinkError, link, status, unlink


ROOT = Path(__file__).resolve().parents[1]


def make_sources(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo with spaces"
    (repo / "skills" / "codex-flow").mkdir(parents=True)
    (repo / "bin").mkdir()
    shim = repo / "bin" / "codex-flow"
    shim.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    shim.chmod(0o755)
    home = tmp_path / "isolated home"
    home.mkdir()
    return repo, home


def destinations(repo: Path, home: Path) -> tuple[Path, Path]:
    return (
        home / ".agents" / "skills" / "codex-flow",
        home / ".local" / "bin" / "codex-flow",
    )


def test_link_creation_repeat_noop_and_exact_targets(tmp_path):
    repo, home = make_sources(tmp_path)
    first = link(repo, home)
    skill_destination, shim_destination = destinations(repo, home)

    assert len(first.changed) == 2
    assert os.readlink(skill_destination) == str((repo / "skills" / "codex-flow").resolve())
    assert os.readlink(shim_destination) == str((repo / "bin" / "codex-flow").resolve())
    assert [entry.state for entry in status(repo, home)] == ["linked", "linked"]

    repeated = link(repo, home)
    assert repeated.changed == ()
    assert [entry.state for entry in repeated.entries] == ["linked", "linked"]


def test_conflict_is_refused_before_any_mutation(tmp_path):
    repo, home = make_sources(tmp_path)
    skill_destination, shim_destination = destinations(repo, home)
    shim_destination.parent.mkdir(parents=True, exist_ok=True)
    shim_destination.write_text("user file\n", encoding="utf-8")

    with pytest.raises(DevLinkError, match="conflict"):
        link(repo, home)

    assert not skill_destination.exists()
    assert not skill_destination.is_symlink()
    assert shim_destination.read_text(encoding="utf-8") == "user file\n"
    assert not (home / ".agents").exists()


def test_unlink_removes_only_exact_links_and_keeps_parents(tmp_path):
    repo, home = make_sources(tmp_path)
    link(repo, home)
    skill_destination, shim_destination = destinations(repo, home)

    removed = unlink(repo, home)
    assert set(removed.changed) == {skill_destination, shim_destination}
    assert not skill_destination.exists()
    assert not shim_destination.exists()
    assert (home / ".agents" / "skills").is_dir()
    assert (home / ".local" / "bin").is_dir()

    absent = unlink(repo, home)
    assert absent.changed == ()
    assert [entry.state for entry in absent.entries] == ["absent", "absent"]


def test_unlink_preserves_wrong_and_dangling_symlinks(tmp_path):
    repo, home = make_sources(tmp_path)
    skill_destination, shim_destination = destinations(repo, home)
    skill_destination.parent.mkdir(parents=True)
    shim_destination.parent.mkdir(parents=True)
    redirected_target = tmp_path / "unrelated-target"
    redirected_target.mkdir()
    os.symlink(redirected_target, skill_destination)
    os.symlink(tmp_path / "missing-target", shim_destination)

    result = unlink(repo, home)
    assert result.changed == ()
    assert skill_destination.is_symlink()
    assert shim_destination.is_symlink()
    assert [entry.state for entry in result.entries] == ["redirected", "dangling"]


def test_link_rolls_back_only_links_created_by_this_invocation(tmp_path, monkeypatch):
    repo, home = make_sources(tmp_path)
    original_symlink = devlinks.os.symlink
    calls = 0

    def fail_second(source, destination, *, target_is_directory=False):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second-link failure")
        return original_symlink(
            source, destination, target_is_directory=target_is_directory
        )

    monkeypatch.setattr(devlinks.os, "symlink", fail_second)
    with pytest.raises(DevLinkError, match="could not create"):
        link(repo, home)

    skill_destination, shim_destination = destinations(repo, home)
    assert not skill_destination.exists()
    assert not skill_destination.is_symlink()
    assert not shim_destination.exists()
    assert not shim_destination.is_symlink()
    assert (home / ".agents" / "skills").is_dir()
    assert (home / ".local" / "bin").is_dir()


def test_non_executable_shim_is_refused_before_mutation(tmp_path):
    repo, home = make_sources(tmp_path)
    shim = repo / "bin" / "codex-flow"
    shim.chmod(0o644)

    with pytest.raises(DevLinkError, match="not executable"):
        link(repo, home)

    skill_destination, shim_destination = destinations(repo, home)
    assert not skill_destination.exists()
    assert not shim_destination.exists()
    assert not (home / ".agents").exists()


def test_rollback_cleanup_failure_is_visible(tmp_path, monkeypatch):
    repo, home = make_sources(tmp_path)
    original_symlink = devlinks.os.symlink
    original_unlink = Path.unlink
    skill_destination, _ = destinations(repo, home)
    calls = 0

    def fail_second(source, destination, *, target_is_directory=False):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second-link failure")
        return original_symlink(
            source, destination, target_is_directory=target_is_directory
        )

    def fail_cleanup(path, *args, **kwargs):
        if path == skill_destination:
            raise OSError("injected cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(devlinks.os, "symlink", fail_second)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(DevLinkError) as raised:
        link(repo, home)

    message = str(raised.value)
    assert "injected second-link failure" in message
    assert "rollback cleanup failed" in message
    assert "injected cleanup failure" in message
    assert str(skill_destination) in message
    assert skill_destination.is_symlink()


SCRIPT = ROOT / "scripts" / "dev_link.py"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ | {"PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def script_paths(repo: Path, home: Path) -> list[str]:
    return ["--repo", str(repo), "--home", str(home)]


def test_script_round_trip_repeat_and_conflict_contract(tmp_path):
    repo, home = make_sources(tmp_path)
    paths = script_paths(repo, home)

    linked = run_script("link", *paths)
    assert linked.returncode == 0, linked.stderr
    repeated = run_script("link", *paths)
    assert repeated.returncode == 0, repeated.stderr
    assert "created:" not in repeated.stdout

    inspected = run_script("status", *paths)
    assert inspected.returncode == 0, inspected.stderr
    assert inspected.stdout.count("linked") == 2

    removed = run_script("unlink", *paths)
    assert removed.returncode == 0, removed.stderr
    after = run_script("status", *paths)
    assert after.returncode == 0, after.stderr
    assert after.stdout.count("absent") == 2

    skill_destination, shim_destination = destinations(repo, home)
    shim_destination.parent.mkdir(parents=True, exist_ok=True)
    shim_destination.write_text("owned by user\n", encoding="utf-8")
    conflict = run_script("link", *paths)
    assert conflict.returncode == 2
    assert "refusing to overwrite development-link conflict" in conflict.stderr
    assert not skill_destination.exists()
    assert shim_destination.read_text(encoding="utf-8") == "owned by user\n"
