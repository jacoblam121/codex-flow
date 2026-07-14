from __future__ import annotations

from codex_flow.cli import COMMANDS, build_parser, main


def test_help_contains_all_eventual_commands(capsys):
    assert main(["--help"]) == 0
    output = capsys.readouterr().out
    assert "{" + ",".join(COMMANDS) + "}" in output
    for command in COMMANDS:
        assert command in output


def test_unknown_command_is_invalid_usage(capsys):
    assert main(["not-a-command"]) == 2
    assert "invalid choice" in capsys.readouterr().err


def test_registered_command_is_clear_and_side_effect_free(capsys):
    assert main(["launch"]) == 4
    assert "registered but not implemented" in capsys.readouterr().err


def test_parser_uses_stable_command_set():
    parser = build_parser()
    assert set(parser._subparsers._group_actions[0].choices) == set(COMMANDS)
