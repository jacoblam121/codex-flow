"""Small atomic UTF-8 text and JSON persistence primitives."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _atomic_write(
    path: str | os.PathLike[str],
    writer: Any,
    *,
    overwrite: bool,
) -> Path:
    """Write a file through a sibling temporary file.

    ``overwrite=False`` publishes the temporary file with a hard link, which
    fails atomically if the destination already exists.  That is useful for
    immutable launch records while retaining the replace semantics used by
    later mutable sidecars.
    """

    target = Path(path)
    target_parent = target.parent
    temp_path: Path | None = None
    file_descriptor: int | None = None
    try:
        file_descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target_parent
        )
        temp_path = Path(temp_name)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            file_descriptor = None
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temp_path, target)
        else:
            os.link(temp_path, target)
            temp_path.unlink()
        temp_path = None
        return target
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def atomic_write_text(
    path: str | os.PathLike[str],
    value: str,
    *,
    overwrite: bool = True,
) -> Path:
    """Write exact UTF-8 text through a sibling temporary file.

    The destination directory must already exist. This deliberate constraint
    keeps the helper's side effects explicit and prevents commands from
    accidentally creating run storage.
    """

    if not isinstance(value, str):
        raise TypeError("atomic text values must be strings")
    return _atomic_write(
        path,
        lambda stream: stream.write(value),
        overwrite=overwrite,
    )


def atomic_write_json(
    path: str | os.PathLike[str],
    value: Any,
    *,
    overwrite: bool = True,
) -> Path:
    """Write JSON through a sibling temporary file and replace the target."""

    return _atomic_write(
        path,
        lambda stream: (
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True),
            stream.write("\n"),
        ),
        overwrite=overwrite,
    )
