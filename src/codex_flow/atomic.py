"""Small atomic JSON persistence primitive."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: str | os.PathLike[str], value: Any) -> Path:
    """Write JSON through a sibling temporary file and replace the target.

    The destination directory must already exist. This deliberate constraint
    keeps the helper's side effects explicit and prevents commands from
    accidentally creating run storage.
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
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
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
