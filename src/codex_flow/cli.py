"""Phase 00 CLI dispatcher and presentation boundary."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .errors import ApplicationError, InvalidCLIUsage, UnsupportedCapability

COMMANDS = (
    "doctor",
    "preflight",
    "launch",
    "show",
    "install",
    "uninstall",
    "child",
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        raise InvalidCLIUsage(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="codex-flow",
        description="Deterministic Codex Flow launcher foundation.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        metavar="{" + ",".join(COMMANDS) + "}",
    )
    for command in COMMANDS:
        subparsers.add_parser(
            command,
            help=(
                "reserved for a later phase"
                if command != "child"
                else "internal child entry point; reserved for a later phase"
            ),
        )
    return parser


def _dispatch(command: str | None) -> None:
    if command is None:
        raise InvalidCLIUsage("a command is required; use --help for usage")
    raise UnsupportedCapability(
        f"command '{command}' is registered but not implemented in Phase 00"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its stable process exit code."""

    parser = build_parser()
    try:
        try:
            args = parser.parse_args(argv)
        except SystemExit as exit_signal:
            return int(exit_signal.code)
        _dispatch(args.command)
    except ApplicationError as error:
        print(f"codex-flow: {error}", file=sys.stderr)
        return error.exit_code
