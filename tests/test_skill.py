from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "codex-flow"
SKILL_TEXT = (SKILL / "SKILL.md").read_text(encoding="utf-8")
HANDOFF_TEXT = (SKILL / "references" / "handoff.md").read_text(encoding="utf-8")
MODEL_TEXT = (SKILL / "references" / "model-selection.md").read_text(encoding="utf-8")
EVIDENCE_TEXT = (SKILL / "references" / "evidence-contracts.md").read_text(encoding="utf-8")
METADATA_TEXT = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")


def test_skill_structure_and_metadata_are_minimal():
    assert sorted(path.relative_to(SKILL).as_posix() for path in SKILL.rglob("*")) == [
        "SKILL.md",
        "agents",
        "agents/openai.yaml",
        "references",
        "references/evidence-contracts.md",
        "references/handoff.md",
        "references/model-selection.md",
    ]
    assert SKILL_TEXT.startswith(
        "---\nname: codex-flow\ndescription:"
    )
    frontmatter = SKILL_TEXT.split("---", 2)[1]
    assert frontmatter.count("name:") == 1
    assert frontmatter.count("description:") == 1
    assert {
        line.split(":", 1)[0]
        for line in frontmatter.splitlines()
        if line.strip()
    } == {"name", "description"}
    for reference in (
        "references/handoff.md",
        "references/model-selection.md",
        "references/evidence-contracts.md",
    ):
        assert f"]({reference})" in SKILL_TEXT
    assert "TODO" not in "\n".join(path.read_text(encoding="utf-8") for path in SKILL.rglob("*") if path.is_file())
    assert "placeholder" not in "\n".join(path.read_text(encoding="utf-8") for path in SKILL.rglob("*") if path.is_file()).lower()
    assert 'display_name: "Codex Flow"' in METADATA_TEXT
    assert 'short_description: "Plan with Sol, execute with the right model"' in METADATA_TEXT
    assert 'default_prompt: "Use $codex-flow handoff to prepare and confirm an execution handoff."' in METADATA_TEXT
    assert "allow_implicit_invocation: true" in METADATA_TEXT
    assert all(term not in METADATA_TEXT for term in ("icon_", "brand_color", "dependencies"))


def test_official_skill_validator_passes():
    validator = Path("/home/jacob/.codex/skills/.system/skill-creator/scripts/quick_validate.py")
    result = subprocess.run(
        [sys.executable, str(validator), str(SKILL)],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("prompt", "description_contract"),
    [
        ("$codex-flow handoff", "explicit `$codex-flow handoff`"),
        ("Hand off the approved plan to the execution agent", "hand off an approved plan"),
        ("What is Codex Flow?", "explanatory question about Codex Flow"),
        ("Implement the parser bug", "ordinary coding"),
        ("Book me a flight", "unrelated work"),
    ],
)
def test_trigger_fixture_is_a_static_forward_test_contract(prompt, description_contract):
    """These prompts specify later fresh-session cases; static tests do not prove LLM triggering."""

    assert prompt
    assert description_contract in SKILL_TEXT
    assert "must never launch" in SKILL_TEXT
    assert "later explicit confirmation" in SKILL_TEXT
    assert "initial handoff request as intent, not confirmation" in SKILL_TEXT


AUTOMATIC_CASES = [
    ("trivial read-only lookup", "gpt-5.6-luna", "low"),
    ("bounded exploration, documentation extraction, or small sanity checks", "gpt-5.6-luna", "medium"),
    ("ordinary execution with slightly complex subagent work", "gpt-5.6-luna", "xhigh"),
    ("short difficult bounded reasoning", "gpt-5.6-luna", "max"),
    ("long-horizon multi-stage exploration edit and test cycles", "gpt-5.6-sol", "medium"),
    ("insufficient upper-tier peer or ambiguous architecture-heavy execution", "gpt-5.6-sol", "high"),
    ("highest uncertainty after repeated failure", "gpt-5.6-sol", "max"),
]


@pytest.mark.parametrize("prompt,model,effort", AUTOMATIC_CASES)
def test_automatic_frontier_fixture_is_documented(prompt, model, effort):
    assert prompt
    assert f"`{model}` / `{effort}`" in SKILL_TEXT


def test_exact_frontier_and_catalog_only_manual_choices():
    frontier = re.findall(r"^\d+\. `([^`]+)` / `([^`]+)`:", SKILL_TEXT, flags=re.MULTILINE)
    assert frontier == [(model, effort) for _, model, effort in AUTOMATIC_CASES]
    assert "six capability tiers" in SKILL_TEXT.lower()
    assert "Luna max and Sol medium are Tier-4 peers, not sequential rungs" in SKILL_TEXT
    assert "If Tier 4 is unnecessary, remain on Luna xhigh" in SKILL_TEXT
    assert "If the Tier-4 horizon is unclear, prefer Luna max" in SKILL_TEXT
    assert "horizon chooses between the Tier-4 peers only after Tier 4 is judged adequate" in SKILL_TEXT
    assert "current catalog" in HANDOFF_TEXT
    assert "Any exact catalog-supported model/effort pair may be selected manually" in MODEL_TEXT
    assert "Never automatically recommend Luna high" in MODEL_TEXT
    assert "Sol low/xhigh/ultra" in MODEL_TEXT
    assert "Terra" in MODEL_TEXT
    assert not re.search(r"^\d+\. `[^`]+` / `[^`]+`", MODEL_TEXT, flags=re.MULTILINE)


def test_skill_alone_contains_canonical_explanation_routing():
    for phrase in (
        "ordinary implementation",
        "not the normal implementation default",
        "short-horizon but difficult",
        "long-horizon, multi-stage",
        "complex, architecture-sensitive, correctness-critical",
        "Select it directly when inherent complexity or risk warrants it",
        "highest-risk or highest-uncertainty",
        "Luna high, Sol low/xhigh/ultra, Terra, and other catalog entries are manual-only",
        "Capability and correctness risk take priority over horizon",
        "never invent, rename, modernize, or substitute model families",
    ):
        assert phrase in SKILL_TEXT


def test_skill_bundle_has_no_stale_invented_model_names():
    bundle = "\n".join(
        path.read_text(encoding="utf-8")
        for path in SKILL.rglob("*")
        if path.is_file()
    )
    assert all(
        stale not in bundle
        for stale in (
            "gpt-5.1-codex-mini",
            "gpt-5.1-codex",
            "gpt-5.1-codex-max",
        )
    )


@pytest.mark.parametrize(
    ("case", "required"),
    [
        ("short upper-tier task", "Luna max"),
        ("long upper-tier task", "Sol medium"),
        ("unavailable peer", "disclose the tradeoff"),
        ("convergent escalation", "Sol high, then Sol max"),
        ("manual-only", "Luna high, Sol low/xhigh/ultra, Terra"),
    ],
)
def test_frontier_routing_cases_are_explicit_contracts(case, required):
    assert case
    assert required in MODEL_TEXT


@pytest.mark.parametrize(
    "phrase",
    [
        "Shift+Tab",
        "native collaboration mode",
        "missing or unknown",
        "`plan`",
        "`default`",
        "clean execution session",
        "source thread",
        "plan title",
        "exact working directory",
        "baseline fingerprint",
        "dirty warning",
        "selected context mode",
        "selected model and reasoning effort",
        "preflight warning",
        "Approve",
        "Edit",
        "fresh complete proposal",
        "confirmation again",
        "Reject",
        "does not support it",
        "--confirm-dirty",
        "stale",
        "Rerun preflight",
        "run ID and artifact paths",
        "Never concurrently `resume`",
        "Recommendations may appear in the proposal; require explicit confirmation before dispatching, spawning, or applying a selection or escalation",
    ],
)
def test_handoff_state_machine_contract(phrase):
    assert phrase in HANDOFF_TEXT


def test_evidence_contract_stays_best_effort_and_phase_bounded():
    assert '<codex_flow_run run_id="<validated UUID>" version="1" />' in EVIDENCE_TEXT
    assert "versioned `<codex_flow_report run_id=\"…\">`" in EVIDENCE_TEXT
    assert "does not prove failure" in EVIDENCE_TEXT
    assert "Repository state, diffs, and tests remain authoritative" in EVIDENCE_TEXT
    assert "belong to Phase 04" in EVIDENCE_TEXT
    assert "Do not add an audit envelope" in EVIDENCE_TEXT


def test_execution_wording_is_model_neutral():
    assert "execution TUI" in SKILL_TEXT
    assert "execution session" in HANDOFF_TEXT
    assert "execution agent's response" in EVIDENCE_TEXT
    assert "Plan with Sol, execute with the right model" in METADATA_TEXT
    assert "separate Luna execution TUI" not in SKILL_TEXT
    assert "Do not wait for Luna" not in HANDOFF_TEXT
    assert "Luna's execution response" not in EVIDENCE_TEXT
