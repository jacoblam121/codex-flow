"""Shared, normalized path resolution for Codex Flow state."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .contracts import validate_run_id


def _absolute_normalized(value: str | os.PathLike[str]) -> Path:
    return Path(value).expanduser().resolve(strict=False)


@dataclass(frozen=True)
class FlowPaths:
    """Resolved user-scoped paths used by Codex Flow.

    Resolving paths does not create any directories. Run creation belongs to a
    later phase; ``run_path`` only validates and computes a path.
    """

    codex_home: Path
    xdg_state_home: Path
    flow_home: Path
    runs: Path

    def run_path(self, run_id: str) -> Path:
        """Return the path for a validated run ID without creating it."""

        return self.runs / validate_run_id(run_id)


def resolve_paths(
    environ: Mapping[str, str] | None = None,
    *,
    home: str | os.PathLike[str] | None = None,
) -> FlowPaths:
    """Resolve Codex and XDG state paths from overrides or standard defaults."""

    env = os.environ if environ is None else environ
    home_path = _absolute_normalized(home if home is not None else Path.home())
    codex_home = _absolute_normalized(env.get("CODEX_HOME") or home_path / ".codex")
    xdg_state_home = _absolute_normalized(
        env.get("XDG_STATE_HOME") or home_path / ".local" / "state"
    )
    flow_home = xdg_state_home / "codex-flow"
    runs = flow_home / "runs"
    return FlowPaths(
        codex_home=codex_home,
        xdg_state_home=xdg_state_home,
        flow_home=flow_home,
        runs=runs,
    )
