"""Codex Flow foundation package."""

__version__ = "0.1.0"

from .contracts import (
    ArtifactPaths,
    HandoffSelection,
    RepositoryBaseline,
    RunIdentity,
    RunManifest,
    ThreadReference,
    UTC,
    manifest_from_dict,
    manifest_from_json,
    validate_run_id,
)
from .errors import (
    ApplicationError,
    ContractError,
    ExternalCommandFailure,
    FailedPrecondition,
    FutureSchemaError,
    InvalidCLIUsage,
    UnsupportedCapability,
    exit_code_for,
)
from .paths import FlowPaths, resolve_paths
from .preflight import PREFLIGHT_SCHEMA_VERSION, PreflightResult, run_preflight
from .rollouts import (
    JsonlReader,
    RolloutAnalysis,
    analyze_rollout,
    discover_rollout,
    validate_thread_id,
)

__all__ = [
    "ApplicationError",
    "ArtifactPaths",
    "ContractError",
    "ExternalCommandFailure",
    "FailedPrecondition",
    "FutureSchemaError",
    "FlowPaths",
    "HandoffSelection",
    "InvalidCLIUsage",
    "RepositoryBaseline",
    "RunIdentity",
    "RunManifest",
    "ThreadReference",
    "UTC",
    "UnsupportedCapability",
    "exit_code_for",
    "manifest_from_dict",
    "manifest_from_json",
    "resolve_paths",
    "validate_run_id",
    "JsonlReader",
    "PREFLIGHT_SCHEMA_VERSION",
    "PreflightResult",
    "RolloutAnalysis",
    "analyze_rollout",
    "discover_rollout",
    "run_preflight",
    "validate_thread_id",
]
