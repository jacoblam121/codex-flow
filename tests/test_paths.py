from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from codex_flow.paths import resolve_paths


def test_default_paths_are_absolute(tmp_path):
    paths = resolve_paths({}, home=tmp_path)
    assert paths.codex_home == (tmp_path / ".codex").resolve()
    assert paths.xdg_state_home == (tmp_path / ".local" / "state").resolve()
    assert paths.runs == paths.xdg_state_home / "codex-flow" / "runs"


def test_environment_overrides_are_normalized(tmp_path):
    paths = resolve_paths(
        {"CODEX_HOME": "~/codex-custom", "XDG_STATE_HOME": "~/state-custom"},
        home=tmp_path,
    )
    assert paths.codex_home.is_absolute()
    assert paths.xdg_state_home.is_absolute()
    assert paths.codex_home == Path.home() / "codex-custom"
    assert paths.xdg_state_home == Path.home() / "state-custom"


def test_run_path_validates_before_joining(tmp_path):
    paths = resolve_paths({}, home=tmp_path)
    valid = str(uuid4())
    assert paths.run_path(valid) == paths.runs / valid
    for malicious in ("../escape", "a/b", "x;touch /tmp/pwned", "$(touch pwned)", ""):
        with pytest.raises(ValueError):
            paths.run_path(malicious)
