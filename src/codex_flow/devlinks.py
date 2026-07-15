"""Safe, reversible development links for the Phase 03 skill and shim."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class DevLinkError(RuntimeError):
    """A development link cannot be inspected or changed safely."""


@dataclass(frozen=True)
class LinkSpec:
    """One source/destination pair owned by the development helper."""

    name: str
    source: Path
    destination: Path


@dataclass(frozen=True)
class LinkStatus:
    """The non-mutating state of one managed destination."""

    spec: LinkSpec
    state: str
    stored_target: str | None = None

    @property
    def exact(self) -> bool:
        return self.state == "linked"


@dataclass(frozen=True)
class DevLinkReport:
    """Result of a development-link operation."""

    operation: str
    entries: tuple[LinkStatus, ...]
    changed: tuple[Path, ...] = ()


def _resolve_directory(value: str | os.PathLike[str], label: str) -> Path:
    candidate = Path(value).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise DevLinkError(f"{label} cannot be resolved: {candidate}") from error
    if not resolved.is_dir():
        raise DevLinkError(f"{label} is not a directory: {resolved}")
    return resolved


def _resolve_source(
    path: Path,
    *,
    repo_root: Path,
    label: str,
    directory: bool,
) -> Path:
    try:
        source = path.resolve(strict=True)
    except OSError as error:
        raise DevLinkError(f"{label} is missing or cannot be resolved: {path}") from error
    if not source.is_relative_to(repo_root):
        raise DevLinkError(f"{label} resolves outside the repository: {source}")
    if directory and not source.is_dir():
        raise DevLinkError(f"{label} is not a directory: {source}")
    if not directory and not source.is_file():
        raise DevLinkError(f"{label} is not a file: {source}")
    if not directory and not os.access(source, os.X_OK):
        raise DevLinkError(f"{label} is not executable: {source}")
    return source


def expected_links(
    repo: str | os.PathLike[str],
    home: str | os.PathLike[str] | None = None,
) -> tuple[LinkSpec, ...]:
    """Resolve and validate all repository sources before any mutation."""

    repo_root = _resolve_directory(repo, "repository")
    home_root = _resolve_directory(Path.home() if home is None else home, "home")
    skill = _resolve_source(
        repo_root / "skills" / "codex-flow",
        repo_root=repo_root,
        label="skill source",
        directory=True,
    )
    shim = _resolve_source(
        repo_root / "bin" / "codex-flow",
        repo_root=repo_root,
        label="CLI shim source",
        directory=False,
    )
    return (
        LinkSpec("skill", skill, home_root / ".agents" / "skills" / "codex-flow"),
        LinkSpec("shim", shim, home_root / ".local" / "bin" / "codex-flow"),
    )


def _destination_exists(path: Path) -> bool:
    """Return true for normal paths and dangling symlinks."""

    return path.exists() or path.is_symlink()


def _status(spec: LinkSpec) -> LinkStatus:
    destination = spec.destination
    if not _destination_exists(destination):
        return LinkStatus(spec, "absent")
    if destination.is_symlink():
        stored_target = os.readlink(destination)
        if stored_target == str(spec.source):
            return LinkStatus(spec, "linked", stored_target)
        target = Path(stored_target)
        if not target.is_absolute():
            target = destination.parent / target
        state = "redirected" if target.exists() else "dangling"
        return LinkStatus(spec, state, stored_target)
    if destination.is_dir():
        return LinkStatus(spec, "directory")
    if destination.is_file():
        return LinkStatus(spec, "file")
    return LinkStatus(spec, "conflict")


def inspect_links(
    repo: str | os.PathLike[str],
    home: str | os.PathLike[str] | None = None,
) -> tuple[LinkStatus, ...]:
    """Return managed-link states without changing filesystem state."""

    return tuple(_status(spec) for spec in expected_links(repo, home))


def status(
    repo: str | os.PathLike[str],
    home: str | os.PathLike[str] | None = None,
) -> tuple[LinkStatus, ...]:
    """Alias for :func:`inspect_links` used by the repository helper."""

    return inspect_links(repo, home)


def _check_destination_parents(specs: Iterable[LinkSpec]) -> None:
    """Reject existing parent conflicts before creating any parent directory."""

    checked: set[Path] = set()
    for spec in specs:
        parent = spec.destination.parent
        while parent not in checked:
            checked.add(parent)
            if parent.is_symlink():
                raise DevLinkError(
                    f"destination parent is a symlink and will not be followed: {parent}"
                )
            if parent.exists() and not parent.is_dir():
                raise DevLinkError(f"destination parent is not a directory: {parent}")
            if parent.parent == parent or parent.exists():
                break
            parent = parent.parent


def _link_preflight(specs: tuple[LinkSpec, ...]) -> tuple[LinkStatus, ...]:
    """Validate both destinations before creating either link."""

    _check_destination_parents(specs)
    statuses = tuple(_status(spec) for spec in specs)
    conflicts = [
        f"{status.spec.destination} ({status.state})"
        for status in statuses
        if status.state not in {"absent", "linked"}
    ]
    if conflicts:
        joined = ", ".join(conflicts)
        raise DevLinkError(f"refusing to overwrite development-link conflict: {joined}")
    return statuses


def _is_exact_link(spec: LinkSpec) -> bool:
    return _status(spec).exact


def link(
    repo: str | os.PathLike[str],
    home: str | os.PathLike[str] | None = None,
) -> DevLinkReport:
    """Create both exact links, or create neither when either destination conflicts."""

    specs = expected_links(repo, home)
    statuses = _link_preflight(specs)
    if all(status.exact for status in statuses):
        return DevLinkReport("link", statuses)

    created: list[Path] = []
    try:
        for spec, before in zip(specs, statuses):
            if before.exact:
                continue
            spec.destination.parent.mkdir(parents=True, exist_ok=True)
            after = _status(spec)
            if not after.state == "absent":
                raise DevLinkError(
                    f"destination changed during link creation: {spec.destination} ({after.state})"
                )
            os.symlink(
                str(spec.source),
                str(spec.destination),
                target_is_directory=spec.source.is_dir(),
            )
            created.append(spec.destination)
    except Exception as error:
        cleanup_failures: list[str] = []
        for destination in reversed(created):
            spec = next(item for item in specs if item.destination == destination)
            try:
                exact = _is_exact_link(spec)
            except Exception as cleanup_error:
                cleanup_failures.append(
                    f"{destination} (could not verify ownership: {cleanup_error})"
                )
                continue
            if exact:
                try:
                    destination.unlink()
                except Exception as cleanup_error:
                    cleanup_failures.append(f"{destination} ({cleanup_error})")
            else:
                try:
                    remains = _destination_exists(destination)
                except Exception as cleanup_error:
                    cleanup_failures.append(
                        f"{destination} (could not verify removal: {cleanup_error})"
                    )
                else:
                    if remains:
                        cleanup_failures.append(
                            f"{destination} (no longer an exact owned link; preserved)"
                        )
        if cleanup_failures:
            paths = ", ".join(cleanup_failures)
            raise DevLinkError(
                f"could not create development links: {error}; rollback cleanup failed, "
                f"these link paths may remain: {paths}"
            ) from error
        if isinstance(error, DevLinkError):
            raise
        raise DevLinkError(f"could not create development links: {error}") from error

    return DevLinkReport("link", tuple(_status(spec) for spec in specs), tuple(created))


def unlink(
    repo: str | os.PathLike[str],
    home: str | os.PathLike[str] | None = None,
) -> DevLinkReport:
    """Remove only exact canonical links and preserve every other destination."""

    specs = expected_links(repo, home)
    before = tuple(_status(spec) for spec in specs)
    removed: list[Path] = []
    for spec, status_entry in zip(specs, before):
        if not status_entry.exact:
            continue
        if _is_exact_link(spec):
            try:
                spec.destination.unlink()
            except OSError as error:
                raise DevLinkError(
                    f"could not remove exact development link {spec.destination}: {error}"
                ) from error
            removed.append(spec.destination)
    return DevLinkReport("unlink", tuple(_status(spec) for spec in specs), tuple(removed))


__all__ = [
    "DevLinkError",
    "DevLinkReport",
    "LinkSpec",
    "LinkStatus",
    "expected_links",
    "inspect_links",
    "link",
    "status",
    "unlink",
]
