from __future__ import annotations

import pytest

from codex_flow.errors import (
    ExternalCommandFailure,
    FailedPrecondition,
    InvalidCLIUsage,
    UnsupportedCapability,
    exit_code_for,
)


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        (InvalidCLIUsage, 2),
        (FailedPrecondition, 3),
        (UnsupportedCapability, 4),
        (ExternalCommandFailure, 5),
    ],
)
def test_application_error_exit_mapping(error_type, expected):
    assert exit_code_for(error_type("test")) == expected


def test_success_exit_mapping():
    assert exit_code_for(None) == 0
