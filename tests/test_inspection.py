from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

import codex_flow.inspection as inspection_module
from codex_flow.contracts import (
    ArtifactPaths,
    HandoffSelection,
    RunIdentity,
    RunManifest,
    ThreadReference,
)
from codex_flow.errors import ContractError, FailedPrecondition
from codex_flow.git import inspect_repository
from codex_flow.inspection import load_run_bundle, show_run, show_runs_by_source
from codex_flow.paths import FlowPaths


FIXTURES = Path(__file__).parent / "fixtures"
RUN = "550e8400-e29b-41d4-a716-446655440000"
ROOT_THREAD = "019f6000-0000-7000-8000-000000000001"
SOURCE_THREAD = "019f5000-0000-7000-8000-000000000001"


def paths(tmp_path: Path) -> FlowPaths:
    state = tmp_path / "state"
    return FlowPaths(
        codex_home=tmp_path / "codex",
        xdg_state_home=state,
        flow_home=state / "codex-flow",
        runs=state / "codex-flow" / "runs",
    )


def create_bundle(
    flow_paths: FlowPaths,
    cwd: Path,
    *,
    run_id: str = RUN,
    source_thread: str = SOURCE_THREAD,
    created_at: str = "2026-07-14T10:00:00.000000Z",
) -> RunManifest:
    baseline = inspect_repository(cwd).baseline
    run_dir = flow_paths.run_path(run_id)
    artifacts = ArtifactPaths(
        manifest=run_dir / "manifest.json",
        plan=run_dir / "plan.md",
        handoff=run_dir / "handoff.md",
        execution=run_dir / "execution.json",
        report=run_dir / "report.json",
        audit=run_dir / "audit.json",
    )
    plan = "plan"
    manifest = RunManifest(
        schema_version=1,
        identity=RunIdentity(run_id),
        source_thread=ThreadReference(source_thread),
        repository=baseline,
        handoff=HandoffSelection("plan", "gpt-test", "max"),
        codex_executable="/missing/historical/codex",
        plan_sha256=hashlib.sha256(plan.encode()).hexdigest(),
        artifacts=artifacts,
        created_at=created_at,
    )
    run_dir.mkdir(parents=True)
    Path(artifacts.plan).write_text(plan, encoding="utf-8")
    Path(artifacts.handoff).write_text("sanitized handoff", encoding="utf-8")
    Path(artifacts.manifest).write_text(manifest.to_json(), encoding="utf-8")
    return manifest


def create_rollout(
    flow_paths: FlowPaths,
    cwd: Path,
    *,
    run_id: str = RUN,
    execution_thread: str = ROOT_THREAD,
) -> Path:
    fixture = (FIXTURES / "sanitized_execution_root.jsonl").read_text(encoding="utf-8")
    fixture = fixture.replace("/sanitized/worktree", str(cwd.resolve()))
    fixture = fixture.replace(RUN, run_id).replace(ROOT_THREAD, execution_thread)
    rollout = (
        flow_paths.codex_home
        / "sessions"
        / "2026"
        / "07"
        / f"rollout-sanitized-{execution_thread}.jsonl"
    )
    rollout.parent.mkdir(parents=True, exist_ok=True)
    rollout.write_text(fixture, encoding="utf-8")
    return rollout


def init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    (path / "tracked.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=path, check=True, capture_output=True)


def tree_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_bundle_loading_does_not_require_historical_codex_executable(tmp_path):
    flow_paths = paths(tmp_path)
    cwd = tmp_path / "plain"
    cwd.mkdir()
    manifest = create_bundle(flow_paths, cwd)
    assert not Path(manifest.codex_executable).exists()
    loaded = load_run_bundle(RUN, paths=flow_paths)
    assert loaded.manifest == manifest


def test_exact_show_shape_states_and_live_git_are_independent_of_report_claims(tmp_path):
    flow_paths = paths(tmp_path)
    repo = tmp_path / "repo"
    init_repo(repo)
    create_bundle(flow_paths, repo)
    rollout = create_rollout(flow_paths, repo)
    records = [json.loads(line) for line in rollout.read_text(encoding="utf-8").splitlines()]
    report_text = records[7]["payload"]["content"][0]["text"]
    records[7]["payload"]["content"][0]["text"] = report_text.replace(
        '"files_changed":[]', '"files_changed":["claimed-but-absent.txt"]'
    )
    rollout.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    document = show_run(RUN, paths=flow_paths)
    assert set(document) == {"schema_version", "query", "run"}
    assert document["query"] == {"run_id": RUN}
    run = document["run"]
    assert set(run) == {
        "run_id",
        "created_at",
        "source_thread",
        "working_directory",
        "context_mode",
        "model",
        "reasoning_effort",
        "states",
        "execution",
        "report",
        "latest_assistant_result",
        "repository",
        "derived_caches",
        "persisted_derived",
        "diagnostics",
    }
    assert run["states"] == {
        "launched": True,
        "associated": True,
        "reported": True,
        "reviewable": True,
        "blocked": False,
    }
    assert run["report"]["status"] == "completed"
    assert run["report"]["files_changed"] == ["claimed-but-absent.txt"]
    assert run["repository"]["live"]["dirty"] is False
    assert "correct" not in json.dumps(run["states"]).lower()
    assert run["derived_caches"]["execution"]["status"] == "missing"


def test_changed_git_state_and_dirty_baseline_are_live_evidence(tmp_path):
    flow_paths = paths(tmp_path)
    repo = tmp_path / "repo"
    init_repo(repo)
    create_bundle(flow_paths, repo)
    create_rollout(flow_paths, repo)
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    changed = show_run(RUN, paths=flow_paths)["run"]
    assert changed["repository"]["live"]["dirty"] is True
    assert changed["repository"]["comparison"]["dirty_changed"] is True
    assert changed["states"]["reviewable"] is True

    dirty_paths = paths(tmp_path / "dirty-case")
    dirty_repo = tmp_path / "dirty-case" / "repo"
    init_repo(dirty_repo)
    (dirty_repo / "tracked.txt").write_text("dirty at launch\n", encoding="utf-8")
    create_bundle(dirty_paths, dirty_repo)
    create_rollout(dirty_paths, dirty_repo)
    dirty = show_run(RUN, paths=dirty_paths)["run"]
    assert dirty["repository"]["baseline"]["dirty"] is True
    assert dirty["repository"]["live"]["dirty"] is True
    assert dirty["states"]["reviewable"] is True


def test_non_git_is_reviewable_and_moved_cwd_is_not(tmp_path):
    flow_paths = paths(tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    create_bundle(flow_paths, plain)
    create_rollout(flow_paths, plain)
    non_git = show_run(RUN, paths=flow_paths)["run"]
    assert non_git["repository"]["live"]["is_git_repository"] is False
    assert non_git["states"]["reviewable"] is True

    moved = tmp_path / "moved"
    plain.rename(moved)
    missing = show_run(RUN, paths=flow_paths)["run"]
    assert missing["states"]["associated"] is True
    assert missing["states"]["reviewable"] is False
    assert missing["repository"] is None
    assert any("not a directory" in message for message in missing["diagnostics"])


def test_exact_show_without_persistence_supports_confirmed_repository_only_fallback(tmp_path):
    flow_paths = paths(tmp_path)
    repo = tmp_path / "repo"
    init_repo(repo)
    manifest = create_bundle(flow_paths, repo)
    repository_before = tree_snapshot(repo)

    shown = show_run(RUN, paths=flow_paths)["run"]

    assert shown["states"]["associated"] is False
    assert shown["states"]["reviewable"] is False
    assert shown["report"] is None
    assert shown["latest_assistant_result"] is None
    assert shown["persisted_derived"] == []
    assert not Path(manifest.artifacts.audit).exists()
    assert tree_snapshot(repo) == repository_before


def test_associated_run_without_current_assistant_final_has_no_text_fallback(tmp_path):
    flow_paths = paths(tmp_path)
    cwd = tmp_path / "plain"
    cwd.mkdir()
    create_bundle(flow_paths, cwd)
    rollout = create_rollout(flow_paths, cwd)
    records = [
        json.loads(line) for line in rollout.read_text(encoding="utf-8").splitlines()
    ]
    # Keep the current marker and task completion, but remove every assistant
    # final so the association remains valid with a null latest result.
    records = records[:7] + [records[8]]
    rollout.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )

    shown = show_run(RUN, paths=flow_paths)["run"]

    assert shown["states"]["associated"] is True
    assert shown["states"]["reviewable"] is True
    assert shown["states"]["reported"] is False
    assert shown["latest_assistant_result"] is None


def test_ordinary_exact_and_source_show_do_not_write_any_file(tmp_path):
    flow_paths = paths(tmp_path)
    cwd = tmp_path / "plain"
    cwd.mkdir()
    create_bundle(flow_paths, cwd)
    create_rollout(flow_paths, cwd)
    before_state = tree_snapshot(flow_paths.xdg_state_home)
    before_codex = tree_snapshot(flow_paths.codex_home)
    exact = show_run(RUN, paths=flow_paths)
    source = show_runs_by_source(SOURCE_THREAD, cwd, paths=flow_paths)
    assert exact["run"]["persisted_derived"] == []
    assert len(source["candidates"]) == 1
    assert source["selection"]["status"] == "selected"
    assert tree_snapshot(flow_paths.xdg_state_home) == before_state
    assert tree_snapshot(flow_paths.codex_home) == before_codex


def test_persist_derived_writes_only_execution_and_valid_report_sidecars(tmp_path):
    flow_paths = paths(tmp_path)
    cwd = tmp_path / "plain"
    cwd.mkdir()
    manifest = create_bundle(flow_paths, cwd)
    create_rollout(flow_paths, cwd)
    before = set(path.name for path in flow_paths.run_path(RUN).iterdir())
    document = show_run(RUN, paths=flow_paths, persist_derived=True)
    after = set(path.name for path in flow_paths.run_path(RUN).iterdir())
    assert after - before == {"execution.json", "report.json"}
    assert not Path(manifest.artifacts.audit).exists()
    assert document["run"]["derived_caches"]["execution"]["status"] == "valid"
    assert document["run"]["derived_caches"]["report"]["status"] == "valid"
    assert document["run"]["persisted_derived"] == [
        manifest.artifacts.execution,
        manifest.artifacts.report,
    ]


def test_persist_derived_without_valid_report_writes_execution_only(tmp_path):
    flow_paths = paths(tmp_path)
    cwd = tmp_path / "plain"
    cwd.mkdir()
    manifest = create_bundle(flow_paths, cwd)
    rollout = create_rollout(flow_paths, cwd)
    records = [json.loads(line) for line in rollout.read_text(encoding="utf-8").splitlines()]
    records[7]["payload"]["content"][0]["text"] = "unstructured final"
    rollout.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    shown = show_run(RUN, paths=flow_paths, persist_derived=True)["run"]
    assert shown["states"]["reported"] is False
    assert Path(manifest.artifacts.execution).is_file()
    assert not Path(manifest.artifacts.report).exists()
    assert shown["persisted_derived"] == [manifest.artifacts.execution]


def test_review_sidecar_persistence_is_not_a_review_or_repository_mutation(tmp_path):
    flow_paths = paths(tmp_path)
    repo = tmp_path / "repo"
    init_repo(repo)
    manifest = create_bundle(flow_paths, repo)
    create_rollout(flow_paths, repo)
    manifest_before = Path(manifest.artifacts.manifest).read_bytes()
    repository_before = tree_snapshot(repo)

    shown = show_run(RUN, paths=flow_paths, persist_derived=True)["run"]

    assert Path(manifest.artifacts.manifest).read_bytes() == manifest_before
    assert tree_snapshot(repo) == repository_before
    assert not Path(manifest.artifacts.audit).exists()
    assert set(shown["states"]) == {
        "launched",
        "associated",
        "reported",
        "reviewable",
        "blocked",
    }
    assert all(
        state not in shown["states"]
        for state in ("audited", "reviewed", "accepted", "completed")
    )


def test_stale_sidecars_are_rejected_as_authority_and_revalidated(tmp_path):
    flow_paths = paths(tmp_path)
    cwd = tmp_path / "plain"
    cwd.mkdir()
    create_bundle(flow_paths, cwd)
    rollout = create_rollout(flow_paths, cwd)
    show_run(RUN, paths=flow_paths, persist_derived=True)
    records = [json.loads(line) for line in rollout.read_text(encoding="utf-8").splitlines()]
    records.insert(
        13,
        {
            "timestamp": "2026-07-14T10:02:59.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "new live result"}],
            },
        },
    )
    rollout.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    shown = show_run(RUN, paths=flow_paths)["run"]
    assert shown["latest_assistant_result"]["text"] == "new live result"
    assert shown["derived_caches"]["execution"]["status"] == "stale"
    assert shown["states"]["associated"] is True


def test_symlinked_sidecar_is_visible_as_invalid_and_rejected_for_persistence(tmp_path):
    flow_paths = paths(tmp_path)
    cwd = tmp_path / "plain"
    cwd.mkdir()
    manifest = create_bundle(flow_paths, cwd)
    create_rollout(flow_paths, cwd)
    outside = tmp_path / "outside.json"
    outside.write_text("sentinel", encoding="utf-8")
    Path(manifest.artifacts.execution).symlink_to(outside)
    ordinary = show_run(RUN, paths=flow_paths)["run"]
    assert ordinary["derived_caches"]["execution"]["status"] == "invalid"
    with pytest.raises(ContractError, match="symlinked"):
        show_run(RUN, paths=flow_paths, persist_derived=True)
    assert outside.read_text(encoding="utf-8") == "sentinel"


def test_atomic_replacement_failure_cleans_temp_and_never_touches_audit(
    tmp_path, monkeypatch
):
    flow_paths = paths(tmp_path)
    cwd = tmp_path / "plain"
    cwd.mkdir()
    manifest = create_bundle(flow_paths, cwd)
    create_rollout(flow_paths, cwd)
    original = inspection_module.atomic_write_json

    def fail_report(path, value, **kwargs):
        if Path(path).name == "report.json":
            raise OSError("injected replacement failure")
        return original(path, value, **kwargs)

    monkeypatch.setattr(inspection_module, "atomic_write_json", fail_report)
    with pytest.raises(FailedPrecondition, match="atomically"):
        show_run(RUN, paths=flow_paths, persist_derived=True)
    assert Path(manifest.artifacts.execution).is_file()
    assert not Path(manifest.artifacts.report).exists()
    assert not Path(manifest.artifacts.audit).exists()
    assert list(flow_paths.run_path(RUN).glob(".*.tmp")) == []


def test_source_query_zero_one_and_multiple_candidates_have_exact_shape(tmp_path):
    flow_paths = paths(tmp_path)
    cwd = tmp_path / "plain"
    cwd.mkdir()
    zero = show_runs_by_source(SOURCE_THREAD, cwd, paths=flow_paths)
    assert zero == {
        "schema_version": 1,
        "query": {"source_thread": SOURCE_THREAD, "cwd": str(cwd.resolve())},
        "selection": {
            "status": "none",
            "run_id": None,
            "candidate_run_ids": [],
            "reason": "no matching runs",
        },
        "candidates": [],
        "diagnostics": [],
    }
    create_bundle(flow_paths, cwd)
    unreviewable = show_runs_by_source(SOURCE_THREAD, cwd, paths=flow_paths)
    assert unreviewable["selection"] == {
        "status": "none",
        "run_id": None,
        "candidate_run_ids": [RUN],
        "reason": "the only matching run is not reviewable",
    }
    create_rollout(flow_paths, cwd)
    one = show_runs_by_source(SOURCE_THREAD, cwd, paths=flow_paths)
    assert len(one["candidates"]) == 1
    assert one["selection"] == {
        "status": "selected",
        "run_id": RUN,
        "candidate_run_ids": [RUN],
        "reason": "the only matching run is reviewable",
    }
    assert not {
        "execution",
        "report",
        "latest_assistant_result",
        "repository",
    } & set(one["candidates"][0])
    assert "Sanitized later assistant result" not in json.dumps(one)
    second_run = str(uuid4())
    create_bundle(
        flow_paths,
        cwd,
        run_id=second_run,
        created_at="2026-07-14T10:00:01.000000Z",
    )
    multiple = show_runs_by_source(SOURCE_THREAD, cwd, paths=flow_paths)
    assert [candidate["run_id"] for candidate in multiple["candidates"]] == [
        second_run,
        RUN,
    ]
    assert multiple["candidates"][0]["states"]["reviewable"] is False
    assert multiple["candidates"][1]["states"]["reviewable"] is True
    assert multiple["selection"] == {
        "status": "ambiguous",
        "run_id": None,
        "candidate_run_ids": [second_run, RUN],
        "reason": "multiple matching runs require explicit selection",
    }
