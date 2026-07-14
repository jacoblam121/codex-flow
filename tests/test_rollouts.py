from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from codex_flow.errors import ContractError, UnsupportedCapability
from codex_flow.rollouts import JsonlReader, analyze_rollout, discover_rollout


THREAD = "019f55cc-b6fb-79d2-b1d2-27ee49aaf2ac"
OTHER_THREAD = "019f55d8-c19c-7561-a797-28592fcb7194"


def meta(thread: str = THREAD, *, source: str = "user", cwd: str = "/work") -> dict:
    return {
        "type": "session_meta",
        "payload": {
            "id": thread,
            "session_id": thread,
            "cwd": cwd,
            "thread_source": source,
        },
    }


def mode(value: str) -> dict:
    return {
        "type": "turn_context",
        "payload": {"collaboration_mode": {"mode": value}},
    }


def structured(text: str) -> dict:
    return {
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "item": {"type": "Plan", "text": text},
        },
    }


def tagged(text: str, *, wrapper: str = "\n") -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "phase": "final_answer",
            "content": [
                {
                    "type": "output_text",
                    "text": f"<proposed_plan>{wrapper}{text}{wrapper}</proposed_plan>",
                }
            ],
        },
    }


def assistant_final(text: str) -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "phase": "final_answer",
            "content": [{"type": "output_text", "text": text}],
        },
    }


def write_rollout(
    home: Path,
    thread: str = THREAD,
    records: list[dict | str] | None = None,
    *,
    directory: str = "2026/07/12",
    suffix: str = "",
) -> Path:
    path = home / "sessions" / directory / f"rollout-2026-07-12T03-08-27-{thread}{suffix}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for record in records or []:
        lines.append(record if isinstance(record, str) else json.dumps(record))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def valid_records(plan: str = "# Plan\n\n- one") -> list[dict]:
    return [meta(), mode("default"), structured(plan), tagged(plan)]


def test_exact_filename_discovery_ignores_newer_unrelated_subagent_rollout(tmp_path):
    home = tmp_path / "codex"
    root = write_rollout(home, records=valid_records())
    unrelated = write_rollout(
        home,
        OTHER_THREAD,
        [meta(THREAD, source="subagent"), meta(THREAD, source="user")],
        directory="2026/07/13",
    )
    os.utime(root, (1, 1))
    os.utime(unrelated, (2, 2))
    assert discover_rollout(THREAD, home) == root.resolve()
    assert analyze_rollout(root, THREAD).owner.thread_source == "user"


def test_subagent_owner_is_rejected_even_when_root_metadata_is_inherited_later(tmp_path):
    home = tmp_path / "codex"
    path = write_rollout(
        home,
        records=[meta(source="subagent"), meta(source="user"), mode("default")],
    )
    with pytest.raises(UnsupportedCapability, match="subagent rollout"):
        analyze_rollout(path, THREAD)


def test_live_shaped_subagent_id_is_checked_before_parent_session_id(tmp_path):
    home = tmp_path / "codex"
    subagent_id = OTHER_THREAD
    record = meta(subagent_id, source="subagent")
    record["payload"]["session_id"] = THREAD
    path = write_rollout(
        home,
        subagent_id,
        records=[record, meta(subagent_id, source="user"), mode("default")],
    )
    with pytest.raises(UnsupportedCapability, match="subagent rollout"):
        analyze_rollout(path, subagent_id)


def test_zero_and_multiple_exact_filename_matches_are_actionable(tmp_path):
    home = tmp_path / "codex"
    with pytest.raises(ContractError, match="no rollout filename"):
        discover_rollout(THREAD, home)
    first = write_rollout(home, records=valid_records())
    second = write_rollout(home, records=valid_records(), directory="2026/07/13")
    assert first != second
    with pytest.raises(ContractError, match="multiple exact rollout filename matches"):
        discover_rollout(THREAD, home)


def test_filename_and_first_session_metadata_must_agree(tmp_path):
    home = tmp_path / "codex"
    path = write_rollout(home, records=[meta(OTHER_THREAD), mode("default")])
    with pytest.raises(ContractError, match="does not agree"):
        analyze_rollout(path, THREAD)


@pytest.mark.parametrize(
    ("mode_value", "expected"),
    [("plan", "plan"), ("default", "default"), (None, "missing"), ("experimental", "unknown")],
)
def test_latest_native_mode_is_classified(tmp_path, mode_value, expected):
    home = tmp_path / "codex"
    records: list[dict] = [meta()]
    if mode_value is not None:
        records.append(mode(mode_value))
    path = write_rollout(home, records=records)
    assert analyze_rollout(path, THREAD).mode.value == expected


def test_latest_structured_matching_pair_wins_and_later_nonplan_final_is_ignored(tmp_path):
    home = tmp_path / "codex"
    old = "# Old\n\nold"
    latest = "### Latest\n\n  keep spacing  "
    records = [meta(), mode("default"), structured(old), tagged(old), structured(latest), tagged(latest)]
    records.append(
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "later answer without a plan"}],
            },
        }
    )
    analysis = analyze_rollout(write_rollout(home, records=records), THREAD)
    assert analysis.plan.text == latest
    assert analysis.plan.source == "structured+tagged"
    assert analysis.plan.structured.line_number == 5
    assert analysis.plan.tagged.line_number == 6
    assert analysis.plan.title == "Latest"
    assert analysis.plan.sha256 == hashlib.sha256(latest.encode()).hexdigest()


def test_structured_only_and_tagged_only_are_warned_fallbacks(tmp_path):
    home = tmp_path / "codex"
    structured_path = write_rollout(home, records=[meta(), mode("default"), structured("plan")])
    structured_analysis = analyze_rollout(structured_path, THREAD)
    assert structured_analysis.plan.source == "structured-only"
    assert any("without a matching tagged" in warning for warning in structured_analysis.warnings)

    tagged_path = write_rollout(
        home,
        OTHER_THREAD,
        [meta(OTHER_THREAD), mode("default"), tagged("fallback")],
        directory="2026/07/13",
    )
    tagged_analysis = analyze_rollout(tagged_path, OTHER_THREAD)
    assert tagged_analysis.plan.source == "tagged-only"
    assert any("compatibility plan fallback" in warning for warning in tagged_analysis.warnings)


def test_structured_and_tagged_mismatch_fails_without_using_an_older_plan(tmp_path):
    home = tmp_path / "codex"
    path = write_rollout(home, records=[meta(), mode("default"), structured("new"), tagged("old")])
    with pytest.raises(ContractError, match="differ"):
        analyze_rollout(path, THREAD)


@pytest.mark.parametrize(
    ("leading", "trailing"),
    [("", ""), ("\n", ""), ("", "\n"), ("\n", "\n")],
)
def test_structured_pair_allows_literal_markers_and_preserves_terminal_newline(
    tmp_path, leading, trailing
):
    home = tmp_path / "codex"
    structured_text = "# Plan\n\nLiteral <proposed_plan> and </proposed_plan>.\n"
    final_text = (
        "  <proposed_plan>"
        + leading
        + structured_text
        + trailing
        + "</proposed_plan>  \n"
    )
    path = write_rollout(
        home,
        records=[meta(), mode("default"), structured(structured_text), assistant_final(final_text)],
    )
    analysis = analyze_rollout(path, THREAD)
    assert analysis.plan.source == "structured+tagged"
    assert analysis.plan.text == structured_text
    assert analysis.plan.text.endswith("\n")
    assert analysis.plan.sha256 == hashlib.sha256(structured_text.encode()).hexdigest()


def test_first_subsequent_ordinary_final_wins_pairing_and_later_inline_examples_are_ignored(
    tmp_path,
):
    home = tmp_path / "codex"
    text = "# Valid\n\n- item"
    inline = "Discussion mentions <proposed_plan> and </proposed_plan> inline."
    path = write_rollout(
        home,
        records=[
            meta(),
            mode("default"),
            structured(text),
            assistant_final("The plan was accepted; ordinary response."),
            assistant_final(inline),
            tagged(text),
        ],
    )
    analysis = analyze_rollout(path, THREAD)
    assert analysis.plan.source == "structured-only"
    assert analysis.plan.text == text


def test_mismatching_corresponding_envelope_is_not_replaced_by_later_match(tmp_path):
    home = tmp_path / "codex"
    path = write_rollout(
        home,
        records=[meta(), mode("default"), structured("new"), tagged("old"), tagged("new")],
    )
    with pytest.raises(ContractError, match="corresponding tagged final differ"):
        analyze_rollout(path, THREAD)


def test_inline_marker_mentions_are_not_malformed_tag_evidence(tmp_path):
    home = tmp_path / "codex"
    path = write_rollout(
        home,
        records=[meta(), mode("default"), assistant_final("Use `<proposed_plan>` as an example.")],
    )
    analysis = analyze_rollout(path, THREAD)
    assert analysis.plan.source == "missing"
    assert analysis.plan.text is None


@pytest.mark.parametrize(
    "text",
    [
        "<proposed_plan>\ntruncated",
        "<proposed_plan>\nouter <proposed_plan>inner</proposed_plan>\n</proposed_plan>",
        "<proposed_plan>\na\n</proposed_plan>\n<proposed_plan>\nb\n</proposed_plan>",
    ],
)
def test_truncated_nested_and_repeated_tags_are_rejected(tmp_path, text):
    home = tmp_path / "codex"
    record = tagged("ignored")
    record["payload"]["content"][0]["text"] = text
    path = write_rollout(home, records=[meta(), mode("default"), record])
    with pytest.raises(ContractError, match="plan|proposed"):
        analyze_rollout(path, THREAD)


def test_missing_tags_do_not_invent_a_plan_and_unknown_records_are_ignored(tmp_path):
    home = tmp_path / "codex"
    path = write_rollout(
        home,
        records=[
            meta(),
            {"type": "future_record", "payload": {"new": True}},
            mode("default"),
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "no tag here"}],
                },
            },
        ],
    )
    analysis = analyze_rollout(path, THREAD)
    assert analysis.plan.source == "missing"
    assert analysis.plan.text is None


def test_malformed_before_later_evidence_warns_but_malformed_after_evidence_blocks(tmp_path):
    home = tmp_path / "codex"
    path = write_rollout(
        home,
        records=["{not json", meta(), mode("default"), structured("plan"), tagged("plan")],
    )
    analysis = analyze_rollout(path, THREAD)
    assert analysis.malformed_line_count == 1
    assert analysis.malformed_line_numbers == (1,)
    assert any("line 1" in warning for warning in analysis.warnings)

    blocked = write_rollout(
        home,
        OTHER_THREAD,
        [meta(OTHER_THREAD), mode("default"), structured("plan"), tagged("plan"), "{later bad"],
        directory="2026/07/13",
    )
    with pytest.raises(ContractError, match="after the latest"):
        analyze_rollout(blocked, OTHER_THREAD)


def test_jsonl_reader_retains_line_numbers_and_ignores_unknown_valid_shapes(tmp_path):
    path = tmp_path / "rollout.jsonl"
    path.write_bytes(b"\n{\"type\":\"future\"}\n{bad\n42\n")
    reader = JsonlReader(path)
    records = list(reader)
    assert [record.line_number for record in records] == [2, 4]
    assert reader.malformed_line_numbers == [1, 3]
    assert reader.malformed_line_count == 2
