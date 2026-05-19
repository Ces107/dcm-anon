"""dcm-anon public entry point. Real logic lives in submodules; import from
here to keep the package surface stable. CLI: ``dcm-anon src dst``.
"""
from __future__ import annotations

from dcm_anon.actions import DEFAULT_REGISTRY, Action, ActionRegistry
from dcm_anon.audit import (
    AuditRecord,
    AuditSummary,
    ProcessingError,
    audit_sha256,
    render_markdown_report,
)
from dcm_anon.cli import main
from dcm_anon.manifest import (
    ComplianceManifest,
    build_manifest,
    render_markdown,
    verify_manifest,
)
from dcm_anon.phi_table import BURNED_IN_TAG, PHI_TAGS, PLACEHOLDERS
from dcm_anon.pipeline import (
    AnonymizationConfig,
    ProgressCallback,
    TagSet,
    anonymize_file,
    anonymize_path,
    parse_keep_tag,
)
from dcm_anon.uid_mapper import UIDMapper
from dcm_anon.verify_output import VerificationResult, scan_outputs

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version
    __version__: str = _pkg_version("dcm-anon")
except (ImportError, PackageNotFoundError):  # pragma: no cover — source-checkout fallback
    __version__ = "0.0.0+source"

__all__ = [
    "BURNED_IN_TAG",
    "DEFAULT_REGISTRY",
    "PHI_TAGS",
    "PLACEHOLDERS",
    "Action",
    "ActionRegistry",
    "AnonymizationConfig",
    "AuditRecord",
    "AuditSummary",
    "ComplianceManifest",
    "ProcessingError",
    "ProgressCallback",
    "TagSet",
    "UIDMapper",
    "VerificationResult",
    "__version__",
    "anonymize_file",
    "anonymize_path",
    "audit_sha256",
    "build_manifest",
    "main",
    "parse_keep_tag",
    "render_markdown",
    "render_markdown_report",
    "scan_outputs",
    "verify_manifest",
]
