from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import codex_flow.launcher as launcher_module
from codex_flow.contracts import RunManifest
from codex_flow.errors import (
    ContractError,
    ExternalCommandFailure,
    FailedPrecondition,
    InvalidCLIUsage,
    UnsupportedCapability,
)
from codex_flow.launcher import (
    build_codex_argv,
    launch,
    resolve_windows_boundary,
    run_child,
)
from codex_flow.models import CommandResult


THREAD = "019f55cc-b6fb-79d2-b1d2-27ee49aaf2ac"
MODEL = "gpt-test"
EFFORT = "max"
TEST_CODEX = str(Path("/bin/sh").resolve())


def fake_preflight(
    cwd: Path,
    plan: str = "# Approved\n\n- keep exact spacing\n",
    *,
    fingerprint: str = "a" * 64,
    dirty: bool | None = False,
    is_git: bool = True,
    warnings: tuple[str, ...] = (),
):
    plan_hash = hashlib.sha256(plan.encode("utf-8")).hexdigest()
    rollout_path = cwd / "source-rollout.jsonl"
    return SimpleNamespace(
        source={"thread_id": THREAD, "rollout_path": str(rollout_path)},
        native_mode="default",
        plan={"text": plan, "sha256": plan_hash},
        repository={
            "requested_cwd": str(cwd.resolve()),
            "repository_root": str(cwd.resolve()) if is_git else None,
            "branch": "main" if is_git else None,
            "head": "deadbeef" if is_git else None,
            "dirty": dirty,
            "is_git_repository": is_git,
            "baseline_fingerprint": fingerprint,
        },
        warnings=warnings,
        blockers=(),
        ready=True,
        exit_code=0,
    )


def resolver(name: str) -> str | None:
    return {
        "wt.exe": r"C:\Trusted Tools\wt.exe",
        "wsl.exe": r"C:\Trusted Tools\wsl.exe",
        "codex": TEST_CODEX,
    }.get(name)


def launch_args(cwd: Path, plan: str = "# Approved\n\n- keep exact spacing\n") -> dict[str, str]:
    plan_hash = hashlib.sha256(plan.encode("utf-8")).hexdigest()
    shim = cwd.parent / "trusted dev" / "codex-flow"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    shim.chmod(0o755)
    return {
        "thread_id": THREAD,
        "cwd": str(cwd),
        "model": MODEL,
        "effort": EFFORT,
        "baseline_fingerprint": "a" * 64,
        "plan_sha256": plan_hash,
        "child_executable": str(shim),
    }


def test_exact_plan_and_fork_codex_argv():
    handoff = "marker\nplan"
    plan_argv = build_codex_argv(
        "plan",
        "/work tree",
        MODEL,
        EFFORT,
        handoff_content=handoff,
        codex_executable="/bin/codex",
    )
    assert plan_argv == [
        "/bin/codex",
        "-C",
        "/work tree",
        "-m",
        MODEL,
        "-c",
        'model_reasoning_effort="max"',
        handoff,
    ]
    prompt = '<codex_flow_run run_id="550e8400-e29b-41d4-a716-446655440000" version="1" />'
    fork_argv = build_codex_argv(
        "fork",
        "/work tree",
        MODEL,
        EFFORT,
        handoff_content=handoff,
        source_thread_id=THREAD,
        fork_prompt=prompt,
        codex_executable="/bin/codex",
    )
    assert fork_argv == [
        "/bin/codex",
        "fork",
        "-C",
        "/work tree",
        "-m",
        MODEL,
        "-c",
        'model_reasoning_effort="max"',
        THREAD,
        prompt,
    ]


def test_dry_run_is_sanitized_and_does_not_create_state(tmp_path):
    cwd = tmp_path / "development cwd"
    cwd.mkdir()
    plan = 'quoted "plan" & unicode é\n' * 100
    args = launch_args(cwd, plan)
    env = {
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "WT_PROFILE_ID": "Trusted Profile",
        "WSL_DISTRO_NAME": "Ubuntu-24.04",
    }
    result = launch(
        **args,
        dry_run=True,
        environ=env,
        preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, plan),
        executable_resolver=resolver,
    )
    output = result.to_json()
    assert result.dry_run
    assert not (tmp_path / "state").exists()
    assert result.windows_argv == (
        r"C:\Trusted Tools\wt.exe",
        "-w",
        "last",
        "new-tab",
        "--profile",
        "Trusted Profile",
        "wsl.exe",
        "--distribution",
        "Ubuntu-24.04",
        "--exec",
        args["child_executable"],
        "child",
        result.run_id,
    )
    assert str(cwd) not in result.windows_argv
    assert MODEL not in result.windows_argv
    assert EFFORT not in result.windows_argv
    assert plan not in output
    assert "quoted" not in output
    assert set(result.codex_argv_preview[-1]) == {
        "content_type",
        "sha256",
        "byte_length",
    }
    assert result.codex_argv_preview[-1]["byte_length"] > 0


def test_fork_dry_run_has_fork_argv_and_sanitized_prompt(tmp_path):
    cwd = tmp_path / "fork repo"
    cwd.mkdir()
    plan = 'fork plan with & quotes " and unicode é\n'
    args = launch_args(cwd, plan)
    result = launch(
        **args,
        context_mode="fork",
        dry_run=True,
        environ={
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "WT_PROFILE_ID": "Profile",
            "WSL_DISTRO_NAME": "Ubuntu",
        },
        preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, plan),
        executable_resolver=resolver,
    )
    assert result.codex_argv_preview[0:2] == (TEST_CODEX, "fork")
    assert result.windows_argv[6] == "wsl.exe"
    assert result.codex_argv_preview[-1]["content_type"] == "fork_prompt"
    assert plan not in result.to_json()
    assert not (tmp_path / "state").exists()


def test_windows_boundary_keeps_wsl_launcher_path_out_of_nested_windows_argv(tmp_path):
    child = tmp_path / "child shim"
    child.write_text("#!/bin/sh\n", encoding="utf-8")
    child.chmod(0o755)
    env = {"WT_PROFILE_ID": "Profile", "WSL_DISTRO_NAME": "Ubuntu"}
    resolver_values = {
        "wt.exe": "/mnt/c/Users/jacob/AppData/Local/Microsoft/WindowsApps/wt.exe",
        "wsl.exe": "/mnt/c/WINDOWS/system32/wsl.exe",
    }

    boundary = resolve_windows_boundary(
        env,
        child_executable=child,
        executable_resolver=resolver_values.get,
    )
    argv = boundary.windows_argv("550e8400-e29b-41d4-a716-446655440000")

    assert argv[0] == resolver_values["wt.exe"]
    assert argv[6] == "wsl.exe"
    assert resolver_values["wsl.exe"] not in argv


def test_launch_forwards_custom_environment_to_preflight(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    args = launch_args(cwd, "plan")
    env = {
        "CODEX_HOME": str(tmp_path / "custom-codex"),
        "XDG_STATE_HOME": str(tmp_path / "custom-state"),
        "WT_PROFILE_ID": "P",
        "WSL_DISTRO_NAME": "D",
    }
    seen = {}

    def preflight(*unused, **kwargs):
        seen["environ"] = kwargs["environ"]
        return fake_preflight(cwd, "plan")

    launch(
        **args,
        dry_run=True,
        environ=env,
        preflight_runner=preflight,
        executable_resolver=resolver,
    )
    assert seen["environ"] is env


@pytest.mark.parametrize("context_mode", ["plan", "fork"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_parent_resolves_codex_for_each_context_and_launch_mode(
    tmp_path, context_mode, dry_run
):
    cwd = tmp_path / f"repo-{context_mode}-{dry_run}"
    cwd.mkdir()
    args = launch_args(cwd, "plan")
    env = {
        "XDG_STATE_HOME": str(tmp_path / f"state-{context_mode}-{dry_run}"),
        "WT_PROFILE_ID": "P",
        "WSL_DISTRO_NAME": "D",
    }
    calls: list[str] = []

    def resolving(name: str) -> str | None:
        calls.append(name)
        return resolver(name)

    launch(
        **args,
        context_mode=context_mode,
        dry_run=dry_run,
        environ=env,
        preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, "plan"),
        terminal_runner=type("T", (), {"run": lambda self, argv: CommandResult(0, "", "")})(),
        executable_resolver=resolving,
    )
    assert calls.count("codex") == 1


@pytest.mark.parametrize("codex_mode", ["missing", "non-executable"])
def test_invalid_parent_codex_fails_before_run_persistence(tmp_path, codex_mode):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    args = launch_args(cwd, "plan")
    state = tmp_path / "state"
    env = {
        "XDG_STATE_HOME": str(state),
        "WT_PROFILE_ID": "P",
        "WSL_DISTRO_NAME": "D",
    }
    codex = tmp_path / "codex with spaces"
    if codex_mode == "non-executable":
        codex.write_text("#!/bin/sh\n", encoding="utf-8")

    def resolving(name: str) -> str | None:
        return str(codex) if name == "codex" else resolver(name)

    with pytest.raises(UnsupportedCapability, match="codex executable"):
        launch(
            **args,
            environ=env,
            preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, "plan"),
            executable_resolver=resolving,
        )
    assert not state.exists()


def test_parent_codex_absolute_path_is_persisted_and_used_in_dry_run(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    args = launch_args(cwd, "plan")
    codex = tmp_path / "trusted tools" / "codex"
    codex.parent.mkdir()
    codex.write_text("#!/bin/sh\n", encoding="utf-8")
    codex.chmod(0o755)
    env = {
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "WT_PROFILE_ID": "P",
        "WSL_DISTRO_NAME": "D",
    }

    def resolving(name: str) -> str | None:
        return str(codex) if name == "codex" else resolver(name)

    result = launch(
        **args,
        dry_run=True,
        environ=env,
        preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, "plan"),
        executable_resolver=resolving,
    )
    assert result.codex_argv_preview[0] == str(codex.resolve())
    assert not Path(result.paths.manifest).exists()


def test_real_launch_persists_exact_artifacts_manifest_last_and_no_sidecars(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    plan = "# exact\n\nampersand & quote \" and unicode é\n"
    args = launch_args(cwd, plan)
    calls: list[tuple[str, ...]] = []

    class Terminal:
        def run(self, argv):
            calls.append(tuple(argv))
            return CommandResult(0, "", "")

    env = {
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "WT_PROFILE_ID": "Profile",
        "WSL_DISTRO_NAME": "Ubuntu",
    }
    result = launch(
        **args,
        environ=env,
        preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, plan),
        terminal_runner=Terminal(),
        executable_resolver=resolver,
        run_id_factory=lambda: UUID("550e8400-e29b-41d4-a716-446655440000"),
    )
    run_dir = Path(result.paths.manifest).parent
    assert Path(result.paths.plan).read_text(encoding="utf-8") == plan
    handoff = Path(result.paths.handoff).read_text(encoding="utf-8")
    assert handoff.startswith(
        '<codex_flow_run run_id="550e8400-e29b-41d4-a716-446655440000" version="1" />'
    )
    assert plan in handoff
    decoded = RunManifest.from_json(Path(result.paths.manifest).read_text(encoding="utf-8"))
    assert decoded.plan_sha256 == hashlib.sha256(plan.encode()).hexdigest()
    assert decoded.source_thread.rollout_path == str((cwd / "source-rollout.jsonl").resolve())
    assert not (run_dir / "execution.json").exists()
    assert not (run_dir / "report.json").exists()
    assert not (run_dir / "audit.json").exists()
    assert calls[0][-3:] == (args["child_executable"], "child", result.run_id)
    assert result.to_dict()["status"] == "dispatched"


def test_artifact_write_failure_cleans_new_run_and_manifest_is_last(tmp_path, monkeypatch):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    plan = "plan"
    args = launch_args(cwd, plan)
    env = {
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "WT_PROFILE_ID": "P",
        "WSL_DISTRO_NAME": "D",
    }
    original_text = launcher_module.atomic_write_text
    original_json = launcher_module.atomic_write_json
    events: list[str] = []

    def record_text(path, value, **kwargs):
        events.append(Path(path).name)
        return original_text(path, value, **kwargs)

    def record_json(path, value, **kwargs):
        events.append(Path(path).name)
        return original_json(path, value, **kwargs)

    monkeypatch.setattr(launcher_module, "atomic_write_text", record_text)
    monkeypatch.setattr(launcher_module, "atomic_write_json", record_json)
    launched = launch(
        **args,
        environ=env,
        preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, plan),
        terminal_runner=type("T", (), {"run": lambda self, argv: CommandResult(0, "", "")})(),
        executable_resolver=resolver,
    )
    assert events[-1] == "manifest.json"
    assert events[:2] == ["plan.md", "handoff.md"]
    assert Path(launched.paths.manifest).exists()

    def fail_handoff(path, value, **kwargs):
        if Path(path).name == "handoff.md":
            raise OSError("injected handoff write failure")
        return original_text(path, value, **kwargs)

    monkeypatch.setattr(launcher_module, "atomic_write_text", fail_handoff)
    with pytest.raises(FailedPrecondition, match="persist run artifacts"):
        launch(
            **args,
            environ={**env, "XDG_STATE_HOME": str(tmp_path / "failed-state")},
            preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, plan),
            executable_resolver=resolver,
        )
    failed_runs = tmp_path / "failed-state" / "codex-flow" / "runs"
    assert not list(failed_runs.iterdir())


def test_generated_report_contract_has_replaceable_status_instructions(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    plan = "plan"
    args = launch_args(cwd, plan)
    result = launch(
        **args,
        environ={
            "XDG_STATE_HOME": str(tmp_path / "state-real"),
            "WT_PROFILE_ID": "P",
            "WSL_DISTRO_NAME": "D",
        },
        preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, plan),
        terminal_runner=type("T", (), {"run": lambda self, argv: CommandResult(0, "", "")})(),
        executable_resolver=resolver,
    )
    handoff = Path(result.paths.handoff).read_text(encoding="utf-8")
    start = handoff.index("<codex_flow_report")
    body_start = handoff.index("\n", start) + 1
    body_end = handoff.index("\n</codex_flow_report>", body_start)
    report = json.loads(handoff[body_start:body_end])
    assert report["status"] == "<completed|partial|blocked>"
    assert set(report) == {
        "schema_version",
        "status",
        "summary",
        "files_changed",
        "validation",
        "deviations",
        "unresolved_issues",
        "recommended_follow_up",
    }
    assert "completed only" in handoff
    assert "meaningful completion" in handoff


def test_stale_and_dirty_confirmation_checks(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    plan = "plan"
    args = launch_args(cwd, plan)
    env = {"XDG_STATE_HOME": str(tmp_path / "state")}
    preflight = lambda *unused, **kwargs: fake_preflight(cwd, plan, dirty=True)
    with pytest.raises(FailedPrecondition, match="plan SHA"):
        launch(
            **{**args, "plan_sha256": "b" * 64},
            environ=env,
            preflight_runner=preflight,
            dry_run=True,
            executable_resolver=resolver,
        )
    with pytest.raises(FailedPrecondition, match="baseline fingerprint"):
        launch(
            **{**args, "baseline_fingerprint": "b" * 64},
            environ=env,
            preflight_runner=preflight,
            dry_run=True,
            executable_resolver=resolver,
        )
    with pytest.raises(FailedPrecondition, match="dirty Git"):
        launch(
            **args,
            environ=env,
            preflight_runner=preflight,
            dry_run=True,
            executable_resolver=resolver,
        )
    dirty_args = {**args, "confirm_dirty": "a" * 64}
    result = launch(
        **dirty_args,
        environ={**env, "WT_PROFILE_ID": "P", "WSL_DISTRO_NAME": "D"},
        preflight_runner=preflight,
        dry_run=True,
        executable_resolver=resolver,
    )
    assert result.dry_run


def test_non_git_warning_does_not_require_dirty_confirmation(tmp_path):
    cwd = tmp_path / "plain"
    cwd.mkdir()
    args = launch_args(cwd, "plan")
    result = launch(
        **args,
        environ={
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "WT_PROFILE_ID": "P",
            "WSL_DISTRO_NAME": "D",
        },
        preflight_runner=lambda *unused, **kwargs: fake_preflight(
            cwd, "plan", is_git=False, dirty=None, warnings=("reduced audit",)
        ),
        dry_run=True,
        executable_resolver=resolver,
    )
    assert result.warnings == ("reduced audit",)


def test_child_validates_identity_paths_hash_and_exec_injection(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    plan = "child plan\n"
    args = launch_args(cwd, plan)
    env = {
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "WT_PROFILE_ID": "P",
        "WSL_DISTRO_NAME": "D",
    }
    launched = launch(
        **args,
        environ=env,
        preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, plan),
        terminal_runner=type("T", (), {"run": lambda self, argv: CommandResult(0, "", "")})(),
        executable_resolver=resolver,
    )
    captured: list[list[str]] = []
    changed: list[str] = []
    run_id = launched.run_id
    assert run_child(
        run_id,
        environ=env,
        exec_fn=lambda argv: captured.append(list(argv)),
        chdir_fn=lambda path: changed.append(str(path)),
    ) == 0
    assert captured[0][0] == TEST_CODEX
    assert captured[0][1:7] == ["-C", str(cwd.resolve()), "-m", MODEL, "-c", 'model_reasoning_effort="max"']
    assert captured[0][-1].startswith(
        f'<codex_flow_run run_id="{run_id}" version="1" />'
    )
    assert changed == [str(cwd.resolve())]
    # The child uses the persisted absolute path even when its PATH cannot find Codex.
    captured.clear()
    assert run_child(
        run_id,
        environ={**env, "PATH": ""},
        exec_fn=lambda argv: captured.append(list(argv)),
        chdir_fn=lambda path: None,
    ) == 0
    assert captured[0][0] == TEST_CODEX
    with pytest.raises(InvalidCLIUsage):
        run_child("../escape", environ=env)
    manifest_path = Path(launched.paths.manifest)
    original_document = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity_mismatch = json.loads(json.dumps(original_document))
    identity_mismatch["identity"]["run_id"] = "550e8400-e29b-41d4-a716-446655440000"
    manifest_path.write_text(json.dumps(identity_mismatch), encoding="utf-8")
    with pytest.raises(ContractError, match="identity run_id"):
        run_child(run_id, environ=env, exec_fn=lambda argv: None)
    manifest_path.write_text(json.dumps(original_document), encoding="utf-8")
    plan_path = Path(launched.paths.plan)
    plan_path.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ContractError, match="plan.md SHA-256"):
        run_child(run_id, environ=env, exec_fn=lambda argv: None)
    plan_path.write_text(plan, encoding="utf-8")
    handoff_path = Path(launched.paths.handoff)
    handoff_path.unlink()
    with pytest.raises(ContractError, match="handoff"):
        run_child(run_id, environ=env, exec_fn=lambda argv: None)
    # Restore the required artifact before exercising manifest path integrity.
    handoff_path.write_text("restored", encoding="utf-8")
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["artifacts"]["plan"] = str(Path(launched.paths.manifest).parent / "../plan.md")
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractError, match="canonical path"):
        run_child(run_id, environ=env, exec_fn=lambda argv: None)


def test_child_rejects_missing_non_executable_or_redirected_manifest_codex(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    plan = "child plan\n"
    args = launch_args(cwd, plan)
    env = {
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "WT_PROFILE_ID": "P",
        "WSL_DISTRO_NAME": "D",
    }
    launched = launch(
        **args,
        environ=env,
        preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, plan),
        terminal_runner=type("T", (), {"run": lambda self, argv: CommandResult(0, "", "")})(),
        executable_resolver=resolver,
    )
    manifest_path = Path(launched.paths.manifest)
    original = json.loads(manifest_path.read_text(encoding="utf-8"))

    missing = tmp_path / "missing-codex"
    document = json.loads(json.dumps(original))
    document["codex_executable"] = str(missing)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(UnsupportedCapability, match="manifest codex executable"):
        run_child(launched.run_id, environ={**env, "PATH": ""}, exec_fn=lambda argv: None)

    non_executable = tmp_path / "not-executable-codex"
    non_executable.write_text("#!/bin/sh\n", encoding="utf-8")
    document["codex_executable"] = str(non_executable)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(UnsupportedCapability, match="manifest codex executable"):
        run_child(launched.run_id, environ={**env, "PATH": ""}, exec_fn=lambda argv: None)

    redirected = tmp_path / "redirected-codex"
    redirected.symlink_to("/bin/sh")
    document["codex_executable"] = str(redirected)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractError, match="codex_executable"):
        run_child(launched.run_id, environ={**env, "PATH": ""}, exec_fn=lambda argv: None)

    manifest_path.write_text(json.dumps(original), encoding="utf-8")


def test_missing_terminal_and_nonzero_terminal_retain_artifacts(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    args = launch_args(cwd, "plan")
    env = {"XDG_STATE_HOME": str(tmp_path / "state")}
    with pytest.raises(UnsupportedCapability, match="Safe manual Linux child command"):
        launch(
            **args,
            environ=env,
            preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, "plan"),
            executable_resolver=resolver,
        )
    run_dirs = list((Path(env["XDG_STATE_HOME"]) / "codex-flow" / "runs").iterdir())
    assert len(run_dirs) == 1

    env2 = {
        "XDG_STATE_HOME": str(tmp_path / "state2"),
        "WT_PROFILE_ID": "P",
        "WSL_DISTRO_NAME": "D",
    }
    with pytest.raises(ExternalCommandFailure):
        launch(
            **args,
            environ=env2,
            preflight_runner=lambda *unused, **kwargs: fake_preflight(cwd, "plan"),
            terminal_runner=type(
                "T", (), {"run": lambda self, argv: CommandResult(7, "", "terminal failed")}
            )(),
            executable_resolver=resolver,
        )
    assert len(list((Path(env2["XDG_STATE_HOME"]) / "codex-flow" / "runs").iterdir())) == 1


def test_each_windows_boundary_capability_is_checked_individually(tmp_path):
    child = tmp_path / "child shim"
    child.write_text("#!/bin/sh\n", encoding="utf-8")
    child.chmod(0o755)
    env = {"WT_PROFILE_ID": "P", "WSL_DISTRO_NAME": "D"}

    with pytest.raises(UnsupportedCapability, match="wt.exe"):
        resolve_windows_boundary(
            env,
            child_executable=child,
            executable_resolver=lambda name: None if name == "wt.exe" else "/trusted/wsl.exe",
        )
    with pytest.raises(UnsupportedCapability, match="wsl.exe"):
        resolve_windows_boundary(
            env,
            child_executable=child,
            executable_resolver=lambda name: None if name == "wsl.exe" else "/trusted/wt.exe",
        )
    with pytest.raises(UnsupportedCapability, match="WT_PROFILE_ID"):
        resolve_windows_boundary(
            {"WSL_DISTRO_NAME": "D"},
            child_executable=child,
            executable_resolver=resolver,
        )
    with pytest.raises(UnsupportedCapability, match="WSL_DISTRO_NAME"):
        resolve_windows_boundary(
            {"WT_PROFILE_ID": "P"},
            child_executable=child,
            executable_resolver=resolver,
        )
    missing_child = tmp_path / "missing-child"
    with pytest.raises(UnsupportedCapability, match="child executable"):
        resolve_windows_boundary(
            env,
            child_executable=missing_child,
            executable_resolver=resolver,
        )
    non_executable = tmp_path / "not-executable"
    non_executable.write_text("#!/bin/sh\n", encoding="utf-8")
    with pytest.raises(UnsupportedCapability, match="not executable"):
        resolve_windows_boundary(
            env,
            child_executable=non_executable,
            executable_resolver=resolver,
        )
