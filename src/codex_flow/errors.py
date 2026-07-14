"""Typed application failures and the stable CLI exit-code contract."""

from __future__ import annotations

from collections.abc import Mapping


class ApplicationError(Exception):
    """Base class for expected, user-facing application failures."""

    exit_code: int


class InvalidCLIUsage(ApplicationError):
    """The command line could not be parsed or is otherwise invalid."""

    exit_code = 2


class FailedPrecondition(ApplicationError):
    """A required state or precondition is missing or invalid."""

    exit_code = 3


class ContractError(FailedPrecondition):
    """A persisted contract is malformed or cannot be interpreted safely."""


class FutureSchemaError(ContractError):
    """A persisted contract uses a schema version newer than this package."""


class UnsupportedCapability(ApplicationError):
    """The requested capability is unavailable in this phase or environment."""

    exit_code = 4


class ExternalCommandFailure(ApplicationError):
    """An external command ran but reported failure."""

    exit_code = 5


ERROR_EXIT_CODES: Mapping[type[ApplicationError], int] = {
    InvalidCLIUsage: 2,
    FailedPrecondition: 3,
    UnsupportedCapability: 4,
    ExternalCommandFailure: 5,
}


def exit_code_for(error: ApplicationError | None) -> int:
    """Return the stable exit code for an application error, or success for ``None``."""

    if error is None:
        return 0
    for error_type, code in ERROR_EXIT_CODES.items():
        if isinstance(error, error_type):
            return code
    raise TypeError(f"unsupported application error type: {type(error).__name__}")
