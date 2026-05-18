"""dcm-anon — DICOM PS3.15 Basic Application Level Confidentiality Profile.

This module is the public entry point. Real logic lives in single-responsibility
submodules; importing from here keeps the package surface stable for users::

    from anonymize import anonymize_path, anonymize_file, UIDMapper

For CLI use::

    python -m anonymize input.dcm out/

Submodules:
    * :mod:`phi_table`          — PS3.15 Table E.1-1 reference data.
    * :mod:`actions`            — Action enum and dispatch registry.
    * :mod:`uid_mapper`         — Stable UID remapping (random or salted-deterministic).
    * :mod:`audit`              — Typed audit dataclasses + Markdown reporter.
    * :mod:`pipeline`           — File and directory anonymization orchestration.
    * :mod:`regulatory_mapping` — PS3.15-action → regulatory-clause table (v0.3+).
    * :mod:`verify_output`      — Independent post-run PHI residual scanner (v0.3+).
    * :mod:`manifest`           — Compliance manifest builder + verifier (v0.3+).
    * :mod:`cli`                — Argparse + main() entry point.
"""
from __future__ import annotations

from typing import Final

from actions import DEFAULT_REGISTRY, Action, ActionRegistry
from audit import (
    AuditRecord,
    AuditSummary,
    ProcessingError,
    audit_sha256,
    render_markdown_report,
    utc_now_iso,
)
from cli import main
from manifest import (
    ComplianceManifest,
    build_manifest,
    render_markdown,
    verify_manifest,
)
from phi_table import BURNED_IN_TAG, PHI_TAGS, PLACEHOLDERS
from pipeline import (
    AnonymizationConfig,
    ProgressCallback,
    TagSet,
    anonymize_file,
    anonymize_path,
    parse_keep_tag,
)
from uid_mapper import UIDMapper
from verify_output import VerificationResult, scan_outputs

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    __version__: Final[str] = _pkg_version("dcm-anonymizer")
except (ImportError, PackageNotFoundError):  # pragma: no cover - source-checkout fallback
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
    "utc_now_iso",
    "verify_manifest",
]


if __name__ == "__main__":
    raise SystemExit(main())
