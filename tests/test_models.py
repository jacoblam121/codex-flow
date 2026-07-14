from __future__ import annotations

import json

import pytest

from codex_flow.errors import ExternalCommandFailure, UnsupportedCapability
from codex_flow.models import CommandResult, load_model_catalog, parse_model_catalog, validate_model_selection


VALID = {
    "models": [
        {
            "slug": "z-model",
            "supported_reasoning_levels": [{"effort": "max"}, {"effort": "low"}],
            "extra": "ignored",
        },
        {"slug": "a-model", "supported_reasoning_levels": [{"effort": "medium"}]},
        "ignored entries are not permitted",
    ]
}


class FakeRunner:
    def __init__(self, result: CommandResult):
        self.result = result
        self.argv = None

    def run(self, argv):
        self.argv = tuple(argv)
        return self.result


def test_catalog_is_sorted_and_stderr_is_a_warning():
    document = {"models": VALID["models"][:2]}
    runner = FakeRunner(CommandResult(0, json.dumps(document), "bundled cache warning"))
    catalog = load_model_catalog(runner)
    assert runner.argv == ("codex", "debug", "models", "--bundled")
    assert [model.slug for model in catalog.models] == ["a-model", "z-model"]
    assert catalog.models[1].efforts == ("low", "max")
    assert catalog.warnings == ("codex debug models --bundled emitted stderr: bundled cache warning",)
    assert catalog.supported_pair("z-model", "max")


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"models": "not a list"},
        {"models": [{"supported_reasoning_levels": []}]},
        {"models": [{"slug": "x"}]},
        {"models": [{"slug": "x", "supported_reasoning_levels": [{"effort": ""}]}]},
        {"models": [{"slug": "x", "supported_reasoning_levels": [{"effort": "low"}, {"effort": "low"}]}]},
        {"models": [{"slug": "x", "supported_reasoning_levels": []}, {"slug": "x", "supported_reasoning_levels": []}]},
    ],
)
def test_malformed_or_ambiguous_catalog_is_rejected(document):
    with pytest.raises(UnsupportedCapability):
        parse_model_catalog(document)


def test_catalog_ignores_unrelated_top_level_and_entry_fields():
    catalog = parse_model_catalog(
        {
            "models": [{"slug": "x", "supported_reasoning_levels": [{"effort": "low", "x": 1}]}],
            "future": {"shape": "ignored"},
        }
    )
    assert catalog.to_dict() == {"models": [{"slug": "x", "efforts": ["low"]}]}


def test_empty_catalog_and_empty_effort_list_are_unsupported():
    with pytest.raises(UnsupportedCapability, match="models list is empty"):
        parse_model_catalog({"models": []})
    with pytest.raises(UnsupportedCapability, match="no usable reasoning efforts"):
        parse_model_catalog(
            {"models": [{"slug": "x", "supported_reasoning_levels": []}]}
        )


def test_unsupported_pair_and_nonzero_or_unparseable_commands_fail():
    catalog = parse_model_catalog({"models": [{"slug": "x", "supported_reasoning_levels": [{"effort": "low"}]}]})
    with pytest.raises(UnsupportedCapability, match="unsupported model/effort"):
        validate_model_selection(catalog, "x", "max")
    with pytest.raises(ExternalCommandFailure):
        load_model_catalog(FakeRunner(CommandResult(7, "", "failed")))
    with pytest.raises(UnsupportedCapability, match="unparseable"):
        load_model_catalog(FakeRunner(CommandResult(0, "not json", "")))
