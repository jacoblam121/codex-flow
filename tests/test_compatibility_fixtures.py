from __future__ import annotations

import json
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures"


def test_sanitized_rollout_fixture_has_only_required_shapes():
    records = [json.loads(line) for line in (FIXTURES / "sanitized_rollout.jsonl").read_text().splitlines()]
    assert [record["type"] for record in records] == [
        "session_meta",
        "turn_context",
        "event_msg",
        "response_item",
        "turn_context",
    ]
    assert records[0]["type"] == "session_meta"
    assert [record["payload"]["collaboration_mode"]["mode"] for record in records if record["type"] == "turn_context"] == ["plan", "default"]

    completed = records[2]
    assert completed["payload"]["type"] == "item_completed"
    assert completed["payload"]["item"]["type"] == "Plan"
    structured_plan = completed["payload"]["item"]["text"]

    response = records[3]
    assert response["payload"]["type"] == "message"
    assert response["payload"]["role"] == "assistant"
    assert response["payload"]["phase"] == "final_answer"
    output_text = [
        part["text"]
        for part in response["payload"]["content"]
        if part.get("type") == "output_text"
    ]
    assert len(output_text) == 1
    tagged_plan = output_text[0]
    assert tagged_plan.startswith("<proposed_plan>\n")
    assert tagged_plan.endswith("\n</proposed_plan>")
    assert tagged_plan.removeprefix("<proposed_plan>\n").removesuffix("\n</proposed_plan>") == structured_plan
    assert all("private" not in json.dumps(record).lower() for record in records)


def test_sanitized_catalog_fixture_is_json_and_small():
    catalog = json.loads((FIXTURES / "sanitized_models.json").read_text())
    assert sorted(catalog) == ["models"]
    assert {model["slug"] for model in catalog["models"]} == {"gpt-5.6-sol", "gpt-5.6-luna"}


def test_sanitized_subagent_fixture_is_distinguishable_for_later_rejection():
    record = json.loads(
        (FIXTURES / "sanitized_subagent_rollout.jsonl").read_text().strip()
    )
    assert record["payload"]["thread_source"] == "subagent"
