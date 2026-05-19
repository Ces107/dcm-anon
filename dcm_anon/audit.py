"""Typed audit records, summary, and reporting helpers."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import cast


def utc_now_iso() -> str:
    """ISO-8601 UTC second-precision timestamp ending in Z."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ProcessingError:
    """One failed file when ``continue_on_error=True`` is set."""

    source: str
    error_type: str
    error_message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class AuditRecord:
    source: str
    source_sha256: str
    output: str | None
    tags_modified: list[str]
    burned_in_phi_warning: bool
    dry_run: bool
    timestamp_utc: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AuditSummary:
    version: str
    files_processed: int
    files_failed: int
    burned_in_warnings: int
    uid_remapping_count: int
    dry_run: bool
    records: list[AuditRecord]
    errors: list[ProcessingError]
    audit_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "files_processed": self.files_processed,
            "files_failed": self.files_failed,
            "burned_in_warnings": self.burned_in_warnings,
            "uid_remapping_count": self.uid_remapping_count,
            "dry_run": self.dry_run,
            "records": [r.as_dict() for r in self.records],
            "errors": [e.as_dict() for e in self.errors],
            "audit_sha256": self.audit_sha256,
        }


def audit_sha256(records: Iterable[AuditRecord]) -> str:
    """Tamper-evident SHA-256 of a record list (canonical-JSON encoding)."""
    serialisable = [r.as_dict() for r in records]
    canonical = json.dumps(serialisable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_markdown_report(audit: AuditSummary) -> str:
    """Human-readable Markdown summary suitable for IRB submissions."""
    data = audit.as_dict()

    rec_count = data.get("files_processed", 0)
    err_count = data.get("files_failed", 0)
    burned = data.get("burned_in_warnings", 0)
    uids = data.get("uid_remapping_count", 0)
    sha = data.get("audit_sha256", "")
    dry_label = " (DRY RUN: no files written)" if data.get("dry_run") else ""

    lines: list[str] = [
        f"# DICOM Anonymization Report{dry_label}",
        "",
        f"- **Tool version:** dcm-anon {data.get('version', '?')}",
        f"- **Files processed:** {rec_count}",
        f"- **Files failed:** {err_count}",
        f"- **Burned-in PHI warnings:** {burned}",
        f"- **Distinct UIDs remapped:** {uids}",
        f"- **Audit SHA-256:** `{sha}`",
        "",
        "## Per-file action summary",
        "",
        "| # | Source | Tags modified | Burned-in PHI? | Output |",
        "|---|--------|---------------|----------------|--------|",
    ]
    records: list[dict[str, object]] = cast(list[dict[str, object]], data.get("records") or [])
    for i, rec in enumerate(records, start=1):
        src = rec.get("source", "?")
        tags_val = rec.get("tags_modified", []) or []
        n_tags = len(tags_val) if isinstance(tags_val, list) else 0
        warn = "YES" if rec.get("burned_in_phi_warning") else "no"
        out = rec.get("output") or "(dry-run)"
        lines.append(f"| {i} | `{src}` | {n_tags} | {warn} | `{out}` |")

    raw_errs = data.get("errors", []) or []
    errs: list[dict[str, str]] = list(raw_errs) if isinstance(raw_errs, list) else []
    if errs:
        lines.extend([
            "",
            "## Errors",
            "",
            "| Source | Type | Message |",
            "|--------|------|---------|",
        ])
        for e in errs:
            lines.append(
                f"| `{e['source']}` | `{e['error_type']}` | {e['error_message']} |"
            )

    return "\n".join(lines) + "\n"
