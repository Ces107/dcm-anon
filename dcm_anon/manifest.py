"""Compliance manifest builder + verifier for PS3.15 de-identification runs."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Final

from dcm_anon.actions import Action
from dcm_anon.audit import AuditSummary, utc_now_iso
from dcm_anon.regulatory_mapping import (
    AI_ACT_DEADLINE_CONTEXT,
    DISCLAIMER,
    EXPERT_DETERMINATION_DISCLAIMER,
    GDPR_ART9_DISCLOSURE,
    PSEUDONYMOUS_RISK_STATEMENT,
    REGIMES,
    GuidanceReference,
    RegimeMetadata,
    RegulatoryClause,
    audit_trail_clauses_for,
    clauses_for_action,
    get_regime,
    guidance_for,
)
from dcm_anon.verify_output import VerificationResult

_REGIME_DISCLOSURES: dict[str, list[tuple[str, str]]] = {
    "hipaa": [
        ("HIPAA method declaration", EXPERT_DETERMINATION_DISCLAIMER),
    ],
    "gdpr": [
        ("GDPR Art. 9 lawful basis", GDPR_ART9_DISCLOSURE),
    ],
    "eu-ai-act": [
        ("EU AI Act enforcement context", AI_ACT_DEADLINE_CONTEXT),
    ],
}

_MANIFEST_FORMAT_VERSION: Final = "1.2"
_PS315_PROFILE_NAME: Final = "PS3.15 Basic Application Level Confidentiality Profile (2024 ed.)"
_OUTPUT_CLASSIFICATION: Final = "pseudonymous"


@dataclass(frozen=True)
class ActionUsage:
    """How often each PS3.15 action code appears across the audit."""

    code: str
    count: int
    clauses: list[RegulatoryClause]

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "count": self.count,
            "clauses": [asdict(c) for c in self.clauses],
        }


@dataclass(frozen=True)
class ComplianceManifest:
    """Self-contained regulatory evidence artifact.

    The serialised form is stable: re-running the build over the same
    audit produces the same JSON modulo the generation timestamp. The
    manifest SHA-256 covers everything EXCEPT itself; verification
    recomputes the chain and compares.

    ``output_verification`` is the result of an independent post-run scan
    over the anonymized files. When present, it breaks the
    self-attestation problem: the manifest no longer relies solely on the
    same pipeline that performed the anonymization.
    """

    manifest_format_version: str
    tool_name: str
    tool_version: str
    ps315_profile: str
    output_classification: str
    risk_statement: str
    regime: RegimeMetadata
    days_to_enforcement: int | None
    generated_at_utc: str
    disclaimer: str
    audit_sha256: str
    files_processed: int
    files_failed: int
    burned_in_warnings: int
    uid_remapping_count: int
    actions_used: list[ActionUsage]
    audit_trail_clauses: list[RegulatoryClause]
    guidance_references: list[GuidanceReference]
    regime_disclosures: list[tuple[str, str]]
    output_verification: VerificationResult | None
    manifest_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "manifest_format_version": self.manifest_format_version,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "ps315_profile": self.ps315_profile,
            "output_classification": self.output_classification,
            "risk_statement": self.risk_statement,
            "regime": asdict(self.regime),
            "days_to_enforcement": self.days_to_enforcement,
            "generated_at_utc": self.generated_at_utc,
            "disclaimer": self.disclaimer,
            "audit_sha256": self.audit_sha256,
            "files_processed": self.files_processed,
            "files_failed": self.files_failed,
            "burned_in_warnings": self.burned_in_warnings,
            "uid_remapping_count": self.uid_remapping_count,
            "actions_used": [a.as_dict() for a in self.actions_used],
            "audit_trail_clauses": [asdict(c) for c in self.audit_trail_clauses],
            "guidance_references": [asdict(g) for g in self.guidance_references],
            "regime_disclosures": [
                {"label": label, "body": body}
                for label, body in self.regime_disclosures
            ],
            "output_verification": (
                self.output_verification.as_dict()
                if self.output_verification is not None
                else None
            ),
            "manifest_sha256": self.manifest_sha256,
        }


def _count_actions(audit: AuditSummary) -> dict[str, int]:
    """Count how often each PS3.15 action appears across the run."""
    counts: dict[str, int] = dict.fromkeys([a.value for a in Action], 0)
    for record in audit.records:
        for entry in record.tags_modified:
            # Entries are formatted "GGGG,EEEE:CODE" or "GGGG,EEEE:X(range)".
            if ":" not in entry:
                continue
            code = entry.split(":", 1)[1]
            base = code[0] if code else ""
            if base in counts:
                counts[base] += 1
    return counts


def _days_to_enforcement(regime: RegimeMetadata, as_of: date | None = None) -> int | None:
    """Days until enforcement, or None if past or unparseable."""
    try:
        deadline = date.fromisoformat(regime.enforcement_date)
    except ValueError:
        return None
    today = as_of or datetime.now(timezone.utc).date()
    delta = (deadline - today).days
    return delta if delta > 0 else None


def _hash_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_manifest(
    audit: AuditSummary,
    regime_code: str,
    *,
    tool_name: str = "dcm-anon",
    tool_version: str | None = None,
    now: str | None = None,
    today: date | None = None,
    output_verification: VerificationResult | None = None,
) -> ComplianceManifest:
    """Build a :class:`ComplianceManifest` from an audit summary.

    ``regime_code`` must be one of the keys in
    :data:`regulatory_mapping.REGIMES`. ``tool_version`` defaults to the
    audit's own version field. ``now`` and ``today`` are injectable for
    deterministic tests. ``output_verification`` is an optional result
    from :func:`verify_output.scan_outputs`; when supplied it is folded
    into the SHA-chained manifest payload.
    """
    regime = get_regime(regime_code)
    counts = _count_actions(audit)
    actions: list[ActionUsage] = [
        ActionUsage(
            code=a.value,
            count=counts[a.value],
            clauses=clauses_for_action(a.value, regime.code),
        )
        for a in Action
    ]
    trail = audit_trail_clauses_for(regime.code)
    guidance = guidance_for(regime.code)
    disclosures = list(_REGIME_DISCLOSURES.get(regime.code, []))

    generated_at = now or utc_now_iso()
    days_left = _days_to_enforcement(regime, as_of=today)
    version = tool_version if tool_version is not None else audit.version

    payload_for_hash = {
        "manifest_format_version": _MANIFEST_FORMAT_VERSION,
        "tool_name": tool_name,
        "tool_version": version,
        "ps315_profile": _PS315_PROFILE_NAME,
        "output_classification": _OUTPUT_CLASSIFICATION,
        "regime_code": regime.code,
        "generated_at_utc": generated_at,
        "audit_sha256": audit.audit_sha256,
        "files_processed": audit.files_processed,
        "files_failed": audit.files_failed,
        "burned_in_warnings": audit.burned_in_warnings,
        "uid_remapping_count": audit.uid_remapping_count,
        "actions_used": [a.as_dict() for a in actions],
        "audit_trail_clauses": [asdict(c) for c in trail],
        "guidance_references": [asdict(g) for g in guidance],
        "regime_disclosures": [
            {"label": label, "body": body} for label, body in disclosures
        ],
        "output_verification": (
            output_verification.as_dict()
            if output_verification is not None
            else None
        ),
    }
    manifest_hash = _hash_payload(payload_for_hash)

    return ComplianceManifest(
        manifest_format_version=_MANIFEST_FORMAT_VERSION,
        tool_name=tool_name,
        tool_version=version,
        ps315_profile=_PS315_PROFILE_NAME,
        output_classification=_OUTPUT_CLASSIFICATION,
        risk_statement=PSEUDONYMOUS_RISK_STATEMENT,
        regime=regime,
        days_to_enforcement=days_left,
        generated_at_utc=generated_at,
        disclaimer=DISCLAIMER,
        audit_sha256=audit.audit_sha256,
        files_processed=audit.files_processed,
        files_failed=audit.files_failed,
        burned_in_warnings=audit.burned_in_warnings,
        uid_remapping_count=audit.uid_remapping_count,
        actions_used=actions,
        audit_trail_clauses=trail,
        guidance_references=guidance,
        regime_disclosures=disclosures,
        output_verification=output_verification,
        manifest_sha256=manifest_hash,
    )


# Accepts both forms because callers split into JSON-loaders (dict) and library users (typed).
def verify_manifest(
    manifest: ComplianceManifest | dict[str, object],
    audit: AuditSummary | dict[str, object],
) -> tuple[bool, list[str]]:
    """Verify a manifest matches its audit. Returns ``(ok, reasons)``.

    ``reasons`` is empty when ``ok`` is true. Otherwise it lists the
    specific integrity failures so an auditor can act on them.
    """
    reasons: list[str] = []

    m = manifest.as_dict() if isinstance(manifest, ComplianceManifest) else dict(manifest)
    a = audit.as_dict() if isinstance(audit, AuditSummary) else dict(audit)

    expected_audit_sha = a.get("audit_sha256")
    if m.get("audit_sha256") != expected_audit_sha:
        reasons.append(
            f"audit_sha256 mismatch: manifest={m.get('audit_sha256')!r} "
            f"audit={expected_audit_sha!r}"
        )

    for field_name in ("files_processed", "files_failed", "burned_in_warnings", "uid_remapping_count"):
        if m.get(field_name) != a.get(field_name):
            reasons.append(
                f"{field_name} mismatch: manifest={m.get(field_name)!r} "
                f"audit={a.get(field_name)!r}"
            )

    declared_hash = m.get("manifest_sha256")
    regime_section = m.get("regime")
    regime_code = (
        regime_section.get("code") if isinstance(regime_section, dict) else None
    )
    payload_for_hash = {
        "manifest_format_version": m.get("manifest_format_version"),
        "tool_name": m.get("tool_name"),
        "tool_version": m.get("tool_version"),
        "ps315_profile": m.get("ps315_profile"),
        "output_classification": m.get("output_classification"),
        "regime_code": regime_code,
        "generated_at_utc": m.get("generated_at_utc"),
        "audit_sha256": m.get("audit_sha256"),
        "files_processed": m.get("files_processed"),
        "files_failed": m.get("files_failed"),
        "burned_in_warnings": m.get("burned_in_warnings"),
        "uid_remapping_count": m.get("uid_remapping_count"),
        "actions_used": m.get("actions_used"),
        "audit_trail_clauses": m.get("audit_trail_clauses"),
        "guidance_references": m.get("guidance_references"),
        "regime_disclosures": m.get("regime_disclosures"),
        "output_verification": m.get("output_verification"),
    }
    recomputed = _hash_payload(payload_for_hash)
    if recomputed != declared_hash:
        reasons.append(
            f"manifest_sha256 invalid: declared={declared_hash!r} "
            f"recomputed={recomputed!r} (manifest has been tampered with "
            f"or generated with a different tool version)"
        )

    return (len(reasons) == 0, reasons)


def render_markdown(manifest: ComplianceManifest) -> str:
    """Markdown rendering of the manifest. Used for QMS attachments and IRB folders."""
    regime = manifest.regime
    lines: list[str] = [
        f"# Compliance Manifest: {regime.code.upper()}",
        "",
        f"> {manifest.disclaimer}",
        "",
        "## Regulatory regime",
        "",
        f"- **Regime:** {regime.full_name}",
        f"- **Jurisdiction:** {regime.jurisdiction}",
        f"- **Enforcement date:** {regime.enforcement_date}",
    ]
    if manifest.days_to_enforcement is not None:
        lines.append(
            f"- **Days remaining at generation:** {manifest.days_to_enforcement}"
        )
    lines.extend([
        f"- **Canonical text:** {regime.canonical_url}",
        "",
        "## Run summary",
        "",
        f"- **Tool:** {manifest.tool_name} {manifest.tool_version}",
        f"- **PS3.15 profile:** {manifest.ps315_profile}",
        f"- **Generated (UTC):** {manifest.generated_at_utc}",
        f"- **Files processed:** {manifest.files_processed}",
        f"- **Files failed:** {manifest.files_failed}",
        f"- **Burned-in PHI warnings:** {manifest.burned_in_warnings}",
        f"- **Distinct UIDs remapped:** {manifest.uid_remapping_count}",
        f"- **Audit SHA-256:** `{manifest.audit_sha256}`",
        f"- **Manifest SHA-256:** `{manifest.manifest_sha256}`",
        "",
        "## Output classification & re-identification risk",
        "",
        f"- **Classification:** `{manifest.output_classification}` "
        "(NOT anonymous; see GDPR Art. 4(5))",
        "",
        f"> {manifest.risk_statement}",
        "",
        "## PS3.15 actions applied (with regulatory citation)",
        "",
    ])
    for action in manifest.actions_used:
        lines.extend([
            f"### Action `{action.code}`: applied {action.count} time(s)",
            "",
        ])
        if not action.clauses:
            lines.append("_No clauses cited for this action under the selected regime._")
        for clause in action.clauses:
            lines.extend([
                f"- **{clause.citation}**: *{clause.short_title}*",
                f"  > {clause.summary}",
                f"  [Source]({clause.url})",
            ])
        lines.append("")

    lines.extend([
        "## Audit-trail clauses (apply to the signed log itself)",
        "",
    ])
    for clause in manifest.audit_trail_clauses:
        lines.extend([
            f"- **{clause.citation}**: *{clause.short_title}*",
            f"  > {clause.summary}",
            f"  [Source]({clause.url})",
        ])

    if manifest.regime_disclosures:
        lines.extend(["", "## Regime-specific disclosures", ""])
        for label, body in manifest.regime_disclosures:
            lines.extend([
                f"### {label}",
                "",
                f"> {body}",
                "",
            ])

    lines.extend(["", "## Authoritative guidance applied", ""])
    if not manifest.guidance_references:
        lines.append("_No additional guidance documents registered for this regime._")
    else:
        lines.append(
            "_These post-2024 documents are the state-of-the-art interpretation "
            "regulators apply when auditing. Cited so a reviewer can verify the "
            "tool tracks current practice._"
        )
        lines.append("")
        for ref in manifest.guidance_references:
            lines.extend([
                f"- **{ref.title}**, {ref.publisher} ({ref.published})",
                f"  > {ref.relevance}",
                f"  [Source]({ref.url})",
            ])

    lines.extend(["", "## Independent output verification", ""])
    if manifest.output_verification is None:
        lines.extend([
            "_Not performed for this run._ Run with `--verify-output` to attach "
            "an independent post-anonymization PHI residual scan to the next "
            "manifest.",
        ])
    else:
        verification = manifest.output_verification
        status = "PASSED (no PHI residuals detected)" if verification.passed else "FAILED"
        lines.extend([
            f"- **Result:** {status}",
            f"- **Files in sample:** {verification.files_scanned} of "
            f"{verification.files_total} total",
            f"- **Tags checked per file (independent list):** "
            f"{verification.metadata_tags_checked_per_file}",
            f"- **Pixel OCR scan:** "
            f"{'enabled' if verification.pixel_ocr_enabled else 'disabled'} "
            f"(pytesseract available: {verification.pixel_ocr_available})",
            f"- **Residuals found:** {len(verification.residuals)}",
            "",
            "_The independent tag list is curated from HIPAA Safe Harbor "
            "§164.514(b)(2) and the TCIA de-identification checklist. It is "
            "intentionally NOT derived from the same internal table used by the "
            "anonymizer, to break the self-attestation problem._",
        ])
        if verification.residuals:
            lines.extend([
                "",
                "| File | Tag | Label | HIPAA category | Excerpt | Layer |",
                "|------|-----|-------|----------------|---------|-------|",
            ])
            for r in verification.residuals[:25]:  # cap; rest in JSON
                excerpt = r.value_excerpt.replace("|", "\\|")
                lines.append(
                    f"| `{r.file}` | `{r.tag}` | {r.tag_label} | "
                    f"{r.hipaa_category} | `{excerpt}` | {r.layer} |"
                )
            if len(verification.residuals) > 25:
                lines.append(
                    f"\n_... and {len(verification.residuals) - 25} more (see "
                    "`compliance_manifest.json`)._"
                )

    lines.extend([
        "",
        "## Verification",
        "",
        "To verify this manifest against its audit log:",
        "",
        "```bash",
        "dcm-anon --verify-manifest compliance_manifest.json \\",
        "  --audit anonymization_audit.json",
        "```",
        "",
        f"Manifest format: v{manifest.manifest_format_version}.",
        "",
    ])
    return "\n".join(lines)


def _load_json_dict(path: str, label: str) -> dict[str, object]:
    with open(path, encoding="utf-8") as fh:
        data: object = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{label} file {path!r} is not a JSON object")
    return data


def load_manifest_dict(path: str) -> dict[str, object]:
    """Load a manifest JSON file as a dict (loose schema)."""
    return _load_json_dict(path, "Manifest")


def load_audit_dict(path: str) -> dict[str, object]:
    """Load an audit JSON file as a dict (loose schema)."""
    return _load_json_dict(path, "Audit")


def supported_regimes() -> tuple[str, ...]:
    """Sorted tuple of regime codes accepted by --manifest-mode."""
    return tuple(sorted(REGIMES.keys()))


__all__ = [
    "ActionUsage",
    "ComplianceManifest",
    "build_manifest",
    "load_audit_dict",
    "load_manifest_dict",
    "render_markdown",
    "supported_regimes",
    "verify_manifest",
]
