"""Runtime model-catalog loading and exact selection validation."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .errors import ExternalCommandFailure, UnsupportedCapability


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str], cwd: Path | None = None) -> CommandResult: ...


class SubprocessCommandRunner:
    """Shell-free command runner used by production preflight."""

    def run(self, argv: Sequence[str], cwd: Path | None = None) -> CommandResult:
        try:
            completed = subprocess.run(
                list(argv),
                cwd=None if cwd is None else str(cwd),
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except FileNotFoundError:
            # Git inspection uses this exception to provide a reduced audit;
            # model loading converts it into an external-command failure.
            raise
        except OSError as error:
            raise ExternalCommandFailure(
                f"could not execute {' '.join(argv)}: {error}"
            ) from error
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class ModelEntry:
    slug: str
    efforts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"slug": self.slug, "efforts": list(self.efforts)}


@dataclass(frozen=True)
class ModelCatalog:
    models: tuple[ModelEntry, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"models": [model.to_dict() for model in self.models]}

    def supported_pair(self, slug: str, effort: str) -> bool:
        return any(model.slug == slug and effort in model.efforts for model in self.models)


def _result_from_runner(result: Any) -> CommandResult:
    if isinstance(result, CommandResult):
        return result
    try:
        return CommandResult(int(result.returncode), str(result.stdout), str(result.stderr))
    except (AttributeError, TypeError, ValueError) as error:
        raise ExternalCommandFailure("the injected command runner returned an invalid result") from error


def _run(runner: CommandRunner | Any, argv: Sequence[str]) -> CommandResult:
    try:
        result = runner.run(argv)
    except AttributeError:
        result = runner(argv)
    return _result_from_runner(result)


def parse_model_catalog(document: Any) -> ModelCatalog:
    """Validate the characterized bundled-model JSON shape."""

    if not isinstance(document, Mapping) or not isinstance(document.get("models"), list):
        raise UnsupportedCapability(
            "codex debug models --bundled returned an unsupported catalog: top-level models list is required"
        )
    if not document["models"]:
        raise UnsupportedCapability(
            "codex debug models --bundled returned an unsupported catalog: models list is empty"
        )
    entries: list[ModelEntry] = []
    seen_slugs: set[str] = set()
    for index, raw_model in enumerate(document["models"]):
        if not isinstance(raw_model, Mapping):
            raise UnsupportedCapability(f"model catalog entry {index} is not an object")
        slug = raw_model.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            raise UnsupportedCapability(f"model catalog entry {index} has a malformed slug")
        if slug in seen_slugs:
            raise UnsupportedCapability(f"model catalog contains duplicate model slug {slug!r}")
        levels = raw_model.get("supported_reasoning_levels")
        if not isinstance(levels, list):
            raise UnsupportedCapability(
                f"model catalog entry {slug!r} has no supported_reasoning_levels list"
            )
        if not levels:
            raise UnsupportedCapability(
                f"model catalog entry {slug!r} has no usable reasoning efforts"
            )
        efforts: list[str] = []
        for level_index, raw_level in enumerate(levels):
            if not isinstance(raw_level, Mapping):
                raise UnsupportedCapability(
                    f"model {slug!r} reasoning level {level_index} is not an object"
                )
            effort = raw_level.get("effort")
            if not isinstance(effort, str) or not effort.strip():
                raise UnsupportedCapability(
                    f"model {slug!r} reasoning level {level_index} has a malformed effort"
                )
            if effort in efforts:
                raise UnsupportedCapability(
                    f"model {slug!r} contains duplicate reasoning effort {effort!r}"
                )
            efforts.append(effort)
        seen_slugs.add(slug)
        entries.append(ModelEntry(slug, tuple(sorted(efforts))))
    return ModelCatalog(tuple(sorted(entries, key=lambda entry: entry.slug)))


def load_model_catalog(
    runner: CommandRunner | Any | None = None,
) -> ModelCatalog:
    runner = SubprocessCommandRunner() if runner is None else runner
    argv = ("codex", "debug", "models", "--bundled")
    try:
        result = _run(runner, argv)
    except FileNotFoundError as error:
        raise ExternalCommandFailure(f"could not execute {' '.join(argv)}: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        raise ExternalCommandFailure(
            f"{' '.join(argv)} failed with exit status {result.returncode}: {detail}"
        )
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise UnsupportedCapability(
            f"{' '.join(argv)} returned unparseable catalog JSON"
        ) from error
    catalog = parse_model_catalog(document)
    warnings = []
    if result.stderr.strip():
        warnings.append(f"{' '.join(argv)} emitted stderr: {result.stderr.strip()}")
    return ModelCatalog(catalog.models, tuple(sorted(warnings)))


def validate_model_selection(catalog: ModelCatalog, slug: str, effort: str) -> None:
    if not catalog.supported_pair(slug, effort):
        raise UnsupportedCapability(
            f"unsupported model/effort pair: model {slug!r} does not support effort {effort!r}"
        )


__all__ = [
    "CommandResult",
    "CommandRunner",
    "ModelCatalog",
    "ModelEntry",
    "SubprocessCommandRunner",
    "load_model_catalog",
    "parse_model_catalog",
    "validate_model_selection",
]
