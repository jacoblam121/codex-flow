from __future__ import annotations

from pathlib import Path

import pytest

import codex_flow.atomic as atomic


def test_atomic_json_write_success(tmp_path):
    target = tmp_path / "state.json"
    assert atomic.atomic_write_json(target, {"answer": 42}) == target
    assert target.read_text(encoding="utf-8") == '{\n  "answer": 42\n}\n'
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_atomic_json_write_cleans_up_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "state.json"

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(atomic.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replacement failure"):
        atomic.atomic_write_json(target, {"answer": 42})
    assert not target.exists()
    assert list(tmp_path.glob(".state.json.*.tmp")) == []
