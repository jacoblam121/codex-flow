#!/usr/bin/env python3
"""Repository-only helper for reversible Codex Flow development links."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from codex_flow.devlinks import DevLinkError, LinkStatus, link, status, unlink  # noqa: E402


def _add_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository containing skills/codex-flow and bin/codex-flow",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=Path.home(),
        help="isolated home directory whose .agents and .local paths are managed",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dev_link.py",
        description="Safely manage temporary Codex Flow development links.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "link", "unlink"):
        command = commands.add_parser(name, help=f"{name} development links")
        _add_paths(command)
    return parser


def _print_status(entries: tuple[LinkStatus, ...]) -> None:
    for entry in entries:
        print(f"{entry.spec.name}: {entry.state}")
        print(f"  destination: {entry.spec.destination}")
        print(f"  source: {entry.spec.source}")
        if entry.stored_target is not None:
            print(f"  stored target: {entry.stored_target}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            _print_status(status(args.repo, args.home))
        elif args.command == "link":
            report = link(args.repo, args.home)
            _print_status(report.entries)
            if report.changed:
                print(f"created: {len(report.changed)}")
        else:
            report = unlink(args.repo, args.home)
            _print_status(report.entries)
            if report.changed:
                print(f"removed: {len(report.changed)}")
    except DevLinkError as error:
        print(f"dev_link.py: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
