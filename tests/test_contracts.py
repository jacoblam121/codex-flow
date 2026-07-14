from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import hashlib

import pytest

from codex_flow.contracts import (
    ArtifactPaths,
    HandoffSelection,
    RepositoryBaseline,
    RunIdentity,
    RunManifest,
    ThreadReference,
    manifest_from_dict,
    utc_timestamp,
    validate_run_id,
)
from codex_flow.errors import FutureSchemaError


def make_manifest() -> RunManifest:
    run_id = str(uuid4())
    return RunManifest(
        schema_version=1,
        identity=RunIdentity(run_id=run_id),
        source_thread=ThreadReference(
            thread_id="019f55cc-b6fb-79d2-b1d2-27ee49aaf2ac", source_kind="root"
        ),
        repository=RepositoryBaseline(
            working_directory=".",
            repository_root=".",
            branch="phase-00",
            head="abc123",
            dirty=True,
            is_git_repository=True,
            original_working_directory=".",
        ),
        handoff=HandoffSelection(
            context_mode="plan", model="gpt-5.6-luna", reasoning_effort="medium"
        ),
        codex_executable=str(Path("/bin/sh").resolve()),
        plan_sha256=hashlib.sha256(b"plan").hexdigest(),
        artifacts=ArtifactPaths(
            manifest="./manifest.json",
            plan="./plan.md",
            handoff="./handoff.md",
            execution="./execution.json",
            report="./report.json",
            audit="./audit.json",
        ),
        created_at=utc_timestamp(datetime(2026, 7, 13, tzinfo=timezone.utc)),
    )


def test_uuidv4_validation_accepts_valid_and_rejects_attacks():
    run_id = str(uuid4())
    assert validate_run_id(run_id) == run_id
    for value in ("../x", "../../tmp", "a/b", "id;echo hacked", "$(touch x)", "not-a-uuid"):
        with pytest.raises(ValueError):
            validate_run_id(value)


def test_manifest_round_trip_preserves_all_fields():
    manifest = make_manifest()
    decoded = manifest_from_dict(json.loads(manifest.to_json()))
    assert decoded == manifest
    assert decoded.to_dict() == manifest.to_dict()
    assert decoded.codex_executable == str(Path("/bin/sh").resolve())
    assert decoded.created_at.endswith("Z")
    assert decoded.artifacts.manifest.startswith("/")
    assert set(decoded.to_dict()) == {
        "schema_version",
        "identity",
        "source_thread",
        "repository",
        "handoff",
        "codex_executable",
        "plan_sha256",
        "artifacts",
        "created_at",
    }
    assert set(json.loads(decoded.to_json())["artifacts"]) == {
        "manifest",
        "plan",
        "handoff",
        "execution",
        "report",
        "audit",
    }
    assert decoded.repository.working_directory.startswith("/")


def test_future_schema_is_rejected():
    document = make_manifest().to_dict()
    document["schema_version"] = 2
    with pytest.raises(FutureSchemaError, match="future schema"):
        manifest_from_dict(document)


@pytest.mark.parametrize("value", [None, "", "A" * 64, "g" * 64, "0" * 63])
def test_required_plan_sha256_is_lowercase_and_schema_v1(value):
    document = make_manifest().to_dict()
    if value is None:
        del document["plan_sha256"]
    else:
        document["plan_sha256"] = value
    with pytest.raises(ValueError, match="plan_sha256"):
        manifest_from_dict(document)


@pytest.mark.parametrize("value", [None, "", "codex", "/tmp/../bin/sh"])
def test_required_codex_executable_is_canonical_absolute_path(value):
    document = make_manifest().to_dict()
    if value is None:
        del document["codex_executable"]
    else:
        document["codex_executable"] = value
    with pytest.raises(ValueError, match="codex_executable"):
        manifest_from_dict(document)


@pytest.mark.parametrize("context", ["plan-only", "default", "", "PLAN"])
def test_persisted_handoff_context_is_canonical(context):
    document = make_manifest().to_dict()
    document["handoff"]["context_mode"] = context
    with pytest.raises(ValueError, match="context_mode"):
        manifest_from_dict(document)


def test_generated_timestamps_are_accepted():
    timestamp = utc_timestamp(datetime(2026, 7, 13, 12, 34, 56, tzinfo=timezone.utc))
    manifest = make_manifest().to_dict()
    manifest["created_at"] = timestamp
    assert manifest_from_dict(manifest).created_at == timestamp


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-W29-1T00:00:00Z",
        "2026-07-13 00:00:00Z",
        "2026-07-13T00:00Z",
        "2026-07-13T00:00:00+00:00",
        "2026-02-30T00:00:00Z",
        "2026-07-13T00:00:00z",
    ],
)
def test_noncanonical_or_invalid_timestamps_are_rejected(timestamp):
    manifest = make_manifest().to_dict()
    manifest["created_at"] = timestamp
    with pytest.raises(ValueError):
        manifest_from_dict(manifest)


def test_execution_thread_reference_remains_reusable_for_future_sidecar():
    reference = ThreadReference(thread_id=str(uuid4()), source_kind="execution")
    assert reference.source_kind == "execution"
