"""CLI dispatcher and presentation boundary."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from . import __version__
from .errors import ApplicationError, InvalidCLIUsage, UnsupportedCapability
from .preflight import run_preflight

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
        command_parser = subparsers.add_parser(
            command,
            help=(
                "read-only session and environment preflight"
                if command == "preflight"
                else "reserved for a later phase"
                if command != "child"
                else "internal child entry point; reserved for a later phase"
            ),
        )
        if command == "preflight":
            command_parser.add_argument("--thread")
            command_parser.add_argument("--cwd")
            command_parser.add_argument("--model")
            command_parser.add_argument("--effort")
            command_parser.add_argument("--json", action="store_true")
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    command = args.command
    if command is None:
        raise InvalidCLIUsage("a command is required; use --help for usage")
    if command == "preflight":
        if (args.model is None) != (args.effort is None):
            raise InvalidCLIUsage("--model and --effort must be supplied together")
        # Resolve the thread here so an explicit argument always wins over the
        # environment, including when the argument is malformed.
        thread_id = args.thread if args.thread is not None else os.environ.get("CODEX_THREAD_ID")
        if thread_id is None:
            raise InvalidCLIUsage(
                "a source thread is required; provide --thread or set CODEX_THREAD_ID"
            )
        result = run_preflight(
            thread_id,
            cwd=args.cwd,
            environ=os.environ,
            model=args.model,
            effort=args.effort,
        )
        if args.json:
            sys.stdout.write(result.to_json())
        else:
            print(f"source thread: {result.source['thread_id']}")
            print(f"rollout: {result.source['rollout_path']}")
            print(f"native mode: {result.native_mode}")
            print(f"handoff ready: {'yes' if result.ready else 'no'}")
            if result.plan.get("sha256"):
                print(f"plan SHA-256: {result.plan['sha256']}")
            for warning in result.warnings:
                print(f"warning: {warning}", file=sys.stderr)
            for blocker in result.blockers:
                print(f"blocked: {blocker}", file=sys.stderr)
        return result.exit_code
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
        return _dispatch(args)
    except ApplicationError as error:
        print(f"codex-flow: {error}", file=sys.stderr)
        return error.exit_code
