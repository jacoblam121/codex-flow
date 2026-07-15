from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from codex_flow.cli import COMMANDS, build_parser, main
from codex_flow.errors import ExternalCommandFailure


def test_help_contains_all_eventual_commands(capsys):
    assert main(["--help"]) == 0
    output = capsys.readouterr().out
    assert "{" + ",".join(COMMANDS) + "}" in output
    for command in COMMANDS:
        assert command in output


def test_unknown_command_is_invalid_usage(capsys):
    assert main(["not-a-command"]) == 2
    assert "invalid choice" in capsys.readouterr().err


def test_registered_command_is_clear_and_side_effect_free(capsys):
    assert main(["launch"]) == 2
    assert "required" in capsys.readouterr().err


def test_all_deferred_commands_remain_exit_four(capsys):
    for command in ("doctor", "install", "uninstall"):
        assert main([command]) == 4
    assert main(["child"]) == 2
    assert "registered but not implemented" in capsys.readouterr().err


def test_preflight_thread_and_cwd_argument_precedence(monkeypatch, capsys):
    calls = []

    def fake_preflight(thread_id, **kwargs):
        calls.append((thread_id, kwargs))
        return SimpleNamespace(
            source={"thread_id": thread_id, "rollout_path": "/rollout"},
            native_mode="default",
            ready=True,
            plan={"sha256": "hash"},
            warnings=(),
            blockers=(),
            exit_code=0,
            to_json=lambda: '{"ok":true}\n',
        )

    monkeypatch.setattr("codex_flow.cli.run_preflight", fake_preflight)
    monkeypatch.setenv("CODEX_THREAD_ID", "from-environment")
    assert main(["preflight", "--thread", "explicit", "--cwd", "/explicit", "--json"]) == 0
    assert calls[-1][0] == "explicit"
    assert calls[-1][1]["cwd"] == "/explicit"
    assert capsys.readouterr().out == '{"ok":true}\n'

    assert main(["preflight", "--json"]) == 0
    assert calls[-1][0] == "from-environment"


def test_preflight_model_and_effort_are_a_pair(monkeypatch, capsys):
    monkeypatch.setattr("codex_flow.cli.run_preflight", pytest.fail)
    assert main(["preflight", "--model", "only-model"]) == 2
    assert "supplied together" in capsys.readouterr().err


def test_external_preflight_failure_uses_exit_code_five(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise ExternalCommandFailure("Git executable was not found")

    monkeypatch.setattr("codex_flow.cli.run_preflight", fail)
    assert main(["preflight", "--thread", "019f55cc-b6fb-79d2-b1d2-27ee49aaf2ac"]) == 5
    assert "Git executable was not found" in capsys.readouterr().err


def test_parser_uses_stable_command_set():
    parser = build_parser()
    assert set(parser._subparsers._group_actions[0].choices) == set(COMMANDS)


def test_launch_dry_run_requires_json_and_context_is_canonical(capsys):
    common = [
        "launch",
        "--thread",
        "019f55cc-b6fb-79d2-b1d2-27ee49aaf2ac",
        "--cwd",
        ".",
        "--model",
        "gpt-test",
        "--effort",
        "max",
        "--baseline-fingerprint",
        "a" * 64,
        "--plan-sha256",
        "b" * 64,
    ]
    assert main([*common, "--dry-run"]) == 2
    assert "requires --json" in capsys.readouterr().err
    assert main([*common, "--context", "plan-only"]) == 2
    assert "invalid choice" in capsys.readouterr().err


def test_cli_forwards_launch_and_child_arguments(monkeypatch, capsys):
    launch_calls = []
    child_calls = []

    def fake_launch(**kwargs):
        launch_calls.append(kwargs)
        return SimpleNamespace(to_json=lambda: '{"status":"dry-run"}\n')

    def fake_child(run_id, **kwargs):
        child_calls.append((run_id, kwargs))
        return 0

    monkeypatch.setattr("codex_flow.cli.launch", fake_launch)
    monkeypatch.setattr("codex_flow.cli.run_child", fake_child)
    plan_hash = "b" * 64
    baseline = "a" * 64
    assert main(
        [
            "launch",
            "--thread",
            "019f55cc-b6fb-79d2-b1d2-27ee49aaf2ac",
            "--cwd",
            "/work tree",
            "--model",
            "gpt-test",
            "--effort",
            "max",
            "--baseline-fingerprint",
            baseline,
            "--plan-sha256",
            plan_hash,
            "--context",
            "fork",
            "--confirm-dirty",
            baseline,
            "--json",
            "--dry-run",
        ]
    ) == 0
    assert capsys.readouterr().out == '{"status":"dry-run"}\n'
    assert launch_calls[0]["thread_id"] == "019f55cc-b6fb-79d2-b1d2-27ee49aaf2ac"
    assert launch_calls[0]["cwd"] == "/work tree"
    assert launch_calls[0]["context_mode"] == "fork"
    assert launch_calls[0]["baseline_fingerprint"] == baseline
    assert launch_calls[0]["plan_sha256"] == plan_hash
    assert launch_calls[0]["dry_run"] is True

    run_id = "550e8400-e29b-41d4-a716-446655440000"
    assert main(["child", run_id]) == 0
    assert child_calls[0][0] == run_id
    assert child_calls[0][1]["environ"] is os.environ


def test_show_requires_exact_supported_json_forms(capsys):
    assert main(["show"]) == 2
    assert "one of the arguments" in capsys.readouterr().err
    assert main(["show", "--run", "id"]) == 2
    assert "requires --json" in capsys.readouterr().err
    assert main(["show", "--source-thread", "thread", "--json"]) == 2
    assert "requires --cwd" in capsys.readouterr().err
    assert main(
        ["show", "--source-thread", "thread", "--cwd", "/work", "--json", "--persist-derived"]
    ) == 2
    assert "only valid with one exact" in capsys.readouterr().err
    assert main(["show", "--run", "id", "--cwd", "/work", "--json"]) == 2
    assert "only valid with --source-thread" in capsys.readouterr().err


def test_cli_forwards_exact_and_source_show_without_hidden_writes(monkeypatch, capsys):
    calls = []

    def fake_run(run_id, **kwargs):
        calls.append(("run", run_id, kwargs))
        return {"schema_version": 1, "query": {"run_id": run_id}, "run": {}}

    def fake_source(thread, cwd, **kwargs):
        calls.append(("source", thread, cwd, kwargs))
        return {
            "schema_version": 1,
            "query": {"source_thread": thread, "cwd": cwd},
            "selection": {"status": "none", "run_id": None},
            "candidates": [],
        }

    monkeypatch.setattr("codex_flow.cli.show_run", fake_run)
    monkeypatch.setattr("codex_flow.cli.show_runs_by_source", fake_source)
    assert main(["show", "--run", "run-id", "--json", "--persist-derived"]) == 0
    exact = json.loads(capsys.readouterr().out)
    assert exact["query"]["run_id"] == "run-id"
    assert calls[-1][2]["persist_derived"] is True
    assert calls[-1][2]["environ"] is os.environ

    assert main(
        ["show", "--source-thread", "source-id", "--cwd", "/work tree", "--json"]
    ) == 0
    source = json.loads(capsys.readouterr().out)
    assert source["candidates"] == []
    assert calls[-1][0:3] == ("source", "source-id", "/work tree")
