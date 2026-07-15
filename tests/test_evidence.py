from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from codex_flow.contracts import (
    ArtifactPaths,
    HandoffSelection,
    RepositoryBaseline,
    RunIdentity,
    RunManifest,
    ThreadReference,
    report_payload_from_dict,
)
from codex_flow.errors import FutureSchemaError
from codex_flow.evidence import associate_execution


FIXTURES = Path(__file__).parent / "fixtures"
RUN = "550e8400-e29b-41d4-a716-446655440000"
OTHER_RUN = "6ba7b810-9dad-41d1-80b4-00c04fd430c8"
ROOT_THREAD = "019f6000-0000-7000-8000-000000000001"
FORK_THREAD = "019f6000-0000-7000-8000-000000000002"
SOURCE_THREAD = "019f5000-0000-7000-8000-000000000001"
CWD = "/sanitized/worktree"


def manifest(tmp_path: Path, *, context: str = "plan", cwd: str = CWD) -> RunManifest:
    run_dir = tmp_path / RUN
    return RunManifest(
        schema_version=1,
        identity=RunIdentity(RUN),
        source_thread=ThreadReference(SOURCE_THREAD),
        repository=RepositoryBaseline(
            working_directory=cwd,
            repository_root=cwd,
            branch="main",
            head="a" * 40,
            dirty=False,
            is_git_repository=True,
            baseline_fingerprint="a" * 64,
        ),
        handoff=HandoffSelection(context, "gpt-test", "max"),
        codex_executable="/missing/historical/codex",
        plan_sha256=hashlib.sha256(b"plan").hexdigest(),
        artifacts=ArtifactPaths(
            manifest=run_dir / "manifest.json",
            plan=run_dir / "plan.md",
            handoff=run_dir / "handoff.md",
            execution=run_dir / "execution.json",
            report=run_dir / "report.json",
            audit=run_dir / "audit.json",
        ),
        created_at="2026-07-14T10:00:00.000000Z",
    )


def fixture_records(name: str) -> list[dict]:
    return [json.loads(line) for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()]


def write_records(home: Path, thread: str, records: list[dict], *, leaf: str = "a") -> Path:
    path = home / "sessions" / leaf / f"rollout-sanitized-{thread}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return path


def report_text(status: str = "completed", *, run_id: str = RUN, extra: dict | None = None) -> str:
    payload = {
        "schema_version": 1,
        "status": status,
        "summary": f"{status} report",
        "files_changed": [],
        "validation": [],
        "deviations": [],
        "unresolved_issues": [],
        "recommended_follow_up": [],
    }
    if extra:
        payload.update(extra)
    return f'<codex_flow_report run_id="{run_id}">\n{json.dumps(payload)}\n</codex_flow_report>'


def assistant_final(text: str, turn: str = "019f6000-0000-7000-8000-000000000021") -> dict:
    return {
        "timestamp": "2026-07-14T10:02:05.000Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "phase": "final_answer",
            "content": [{"type": "output_text", "text": text}],
            "internal_chat_message_metadata_passthrough": {"turn_id": turn},
        },
    }


def test_clean_root_fixture_uses_line_order_and_next_run_task_boundary(tmp_path):
    home = tmp_path / "codex"
    path = write_records(home, ROOT_THREAD, fixture_records("sanitized_execution_root.jsonl"))
    result = associate_execution(manifest(tmp_path), home)
    assert not result.ambiguous
    assert result.association is not None
    association = result.association
    assert association.execution.execution_thread_id == ROOT_THREAD
    assert association.execution.rollout_path == str(path.resolve())
    assert association.execution.marker_line == 5
    assert association.execution.task_started_line == 2
    assert association.execution.turn_context_line == 4
    assert association.execution.segment_end_before_line == 14
    assert association.execution.observed_end_line == 17
    assert association.latest_assistant_result.line_number == 13
    assert association.latest_assistant_result.text == "Sanitized later assistant result."
    assert association.report.payload.status == "completed"
    assert association.report.sidecar.assistant_result.line_number == 8


def test_fork_fixture_uses_current_owner_and_cannot_take_inherited_report(tmp_path):
    home = tmp_path / "codex"
    write_records(home, FORK_THREAD, fixture_records("sanitized_execution_fork.jsonl"))
    result = associate_execution(manifest(tmp_path, context="fork"), home)
    assert result.association is not None
    association = result.association
    assert association.execution.session_meta_line == 1
    assert association.execution.forked_from_id == SOURCE_THREAD
    assert association.execution.marker_line == 10
    assert association.report.payload.status == "partial"
    assert association.report.payload.summary == "Current fork report wins."
    assert association.report.sidecar.assistant_result.line_number == 11


def test_event_echo_tool_output_and_task_complete_copies_never_count(tmp_path):
    home = tmp_path / "codex"
    records = fixture_records("sanitized_execution_root.jsonl")
    records[7]["payload"]["content"][0]["text"] = "No canonical report here."
    write_records(home, ROOT_THREAD, records)
    association = associate_execution(manifest(tmp_path), home).association
    assert association is not None
    assert association.report is None


def test_duplicate_markers_and_multiple_rollouts_are_ambiguous(tmp_path):
    records = fixture_records("sanitized_execution_root.jsonl")[:13]
    records.insert(5, json.loads(json.dumps(records[4])))
    home = tmp_path / "duplicate-marker"
    write_records(home, ROOT_THREAD, records)
    duplicate = associate_execution(manifest(tmp_path), home)
    assert duplicate.association is None
    assert duplicate.ambiguous
    assert any("multiple qualifying markers" in message for message in duplicate.diagnostics)

    home = tmp_path / "duplicate-rollout"
    first = fixture_records("sanitized_execution_root.jsonl")
    second = json.loads(json.dumps(first))
    second_thread = "019f6000-0000-7000-8000-000000000003"
    second[0]["payload"]["id"] = second_thread
    second[0]["payload"]["session_id"] = second_thread
    write_records(home, ROOT_THREAD, first, leaf="a")
    write_records(home, second_thread, second, leaf="b")
    multiple = associate_execution(manifest(tmp_path), home)
    assert multiple.association is None
    assert multiple.ambiguous
    assert any("multiple qualifying execution rollouts" in message for message in multiple.diagnostics)


def test_duplicate_marker_rollout_makes_one_other_qualifying_rollout_globally_ambiguous(
    tmp_path,
):
    ambiguous_records = fixture_records("sanitized_execution_root.jsonl")[:13]
    ambiguous_records.insert(5, json.loads(json.dumps(ambiguous_records[4])))
    good_records = fixture_records("sanitized_execution_root.jsonl")
    good_thread = "019f6000-0000-7000-8000-000000000004"
    good_records[0]["payload"]["id"] = good_thread
    good_records[0]["payload"]["session_id"] = good_thread
    home = tmp_path / "hybrid"
    write_records(home, ROOT_THREAD, ambiguous_records, leaf="ambiguous")
    write_records(home, good_thread, good_records, leaf="good")

    result = associate_execution(manifest(tmp_path), home)

    assert result.association is None
    assert result.ambiguous
    assert any("multiple qualifying markers" in message for message in result.diagnostics)
    assert any("globally ambiguous" in message for message in result.diagnostics)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_fork",
        "session_cwd",
        "turn_cwd",
        "session_before_launch",
        "marker_before_session",
        "owner",
        "version",
        "turn_id",
        "mode",
        "model",
    ],
)
def test_wrong_origin_cwd_timestamps_owner_version_or_turn_metadata_do_not_associate(
    tmp_path, mutation
):
    records = fixture_records("sanitized_execution_fork.jsonl")
    if mutation == "wrong_fork":
        records[0]["payload"]["forked_from_id"] = ROOT_THREAD
    elif mutation == "session_cwd":
        records[0]["payload"]["cwd"] = "/wrong"
    elif mutation == "turn_cwd":
        records[8]["payload"]["cwd"] = "/wrong"
    elif mutation == "session_before_launch":
        records[0]["timestamp"] = "2026-07-14T09:59:00.000Z"
    elif mutation == "marker_before_session":
        records[9]["timestamp"] = "2026-07-14T10:01:00.000Z"
    elif mutation == "owner":
        records[0]["payload"]["thread_source"] = "subagent"
    elif mutation == "version":
        records[9]["payload"]["content"][0]["text"] = records[9]["payload"]["content"][0]["text"].replace('version="1"', 'version="2"')
    elif mutation == "turn_id":
        records[9]["payload"]["internal_chat_message_metadata_passthrough"]["turn_id"] = ROOT_THREAD
    elif mutation == "mode":
        records[8]["payload"]["collaboration_mode"]["mode"] = "plan"
    elif mutation == "model":
        records[8]["payload"]["model"] = "wrong-model"
    home = tmp_path / mutation
    write_records(home, FORK_THREAD, records)
    result = associate_execution(manifest(tmp_path, context="fork"), home)
    assert result.association is None


@pytest.mark.parametrize("status", ["completed", "partial", "blocked"])
def test_all_report_statuses_are_valid_and_latest_valid_wins(tmp_path, status):
    records = fixture_records("sanitized_execution_fork.jsonl")
    records.append(assistant_final(report_text(status)))
    home = tmp_path / status
    write_records(home, FORK_THREAD, records)
    association = associate_execution(manifest(tmp_path, context="fork"), home).association
    assert association.report.payload.status == status
    assert association.report.sidecar.assistant_result.line_number == 12


@pytest.mark.parametrize(
    "text",
    [
        "ordinary result without an envelope",
        f'<codex_flow_report run_id="{RUN}">\n{{',
        f'<codex_flow_report run_id="{RUN}">not json</codex_flow_report>',
        f'<codex_flow_report run_id="{RUN}"><codex_flow_report run_id="{RUN}">{{}}</codex_flow_report></codex_flow_report>',
        report_text(run_id=OTHER_RUN),
        report_text(extra={"schema_version": 2}),
        report_text(extra={"unexpected": True}),
    ],
)
def test_missing_malformed_truncated_nested_wrong_run_and_future_reports_degrade(
    tmp_path, text
):
    records = fixture_records("sanitized_execution_fork.jsonl")[:10]
    records.append(assistant_final(text))
    home = tmp_path / "reports"
    write_records(home, FORK_THREAD, records)
    association = associate_execution(manifest(tmp_path, context="fork"), home).association
    assert association is not None
    assert association.report is None
    assert association.latest_assistant_result.text == text


def test_valid_report_survives_later_malformed_attempt_and_latest_result_falls_back(tmp_path):
    malformed = f'<codex_flow_report run_id="{RUN}">\n{{'
    records = fixture_records("sanitized_execution_fork.jsonl")
    records.append(assistant_final(malformed))
    home = tmp_path / "codex"
    write_records(home, FORK_THREAD, records)
    association = associate_execution(manifest(tmp_path, context="fork"), home).association
    assert association.report.payload.status == "partial"
    assert association.latest_assistant_result.line_number == 12
    assert association.latest_assistant_result.text == malformed
    assert any("truncated" in message for message in association.diagnostics)


def test_repeated_reports_select_latest_complete_schema_valid_envelope(tmp_path):
    text = report_text("completed") + "\nprose\n" + report_text("blocked")
    records = fixture_records("sanitized_execution_fork.jsonl")[:10]
    records.append(assistant_final(text))
    home = tmp_path / "codex"
    write_records(home, FORK_THREAD, records)
    association = associate_execution(manifest(tmp_path, context="fork"), home).association
    assert association.report.payload.status == "blocked"
    assert association.report.sidecar.envelope_index == 1


def test_report_payload_schema_is_exact_and_exit_code_rejects_boolean():
    payload = json.loads(report_text().split("\n", 1)[1].rsplit("\n", 1)[0])
    assert report_payload_from_dict(payload).status == "completed"
    payload["validation"] = [{"command": "test", "exit_code": True, "outcome": "bad"}]
    with pytest.raises(ValueError, match="integer or null"):
        report_payload_from_dict(payload)
    payload["validation"] = []
    payload["schema_version"] = 2
    with pytest.raises(FutureSchemaError):
        report_payload_from_dict(payload)
