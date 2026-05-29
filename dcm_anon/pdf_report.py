"""Professional PDF compliance report for a dcm-anon run.

Output target: an auditor (DPO, IRB reviewer, Notified Body assessor) or
the operator who launched the anonymization can open the PDF on its own
and answer the questions a compliance review actually asks:

- What was processed, by what tool version, when?
- Which DICOM tags were modified, under what PS3.15 action, with what
  regulatory citation?
- Was an independent residual scan performed?
- Is the audit trail tamper-evident? What are the chain hashes?
- What disclaimers and regime-specific disclosures apply?

The PDF is the printable evidence pack; the JSON and Markdown stay as the
machine-readable + IRB-folder companions.

Hard requirement: pure-Python output. We use reportlab (no LaTeX, no
external binaries, no system fonts beyond what reportlab ships). The
``[pdf]`` install extra brings reportlab in; absent that, the import
fails at use-site, not at import-time of the rest of the package.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from dcm_anon.audit import AuditSummary

if TYPE_CHECKING:
    from dcm_anon.manifest import ComplianceManifest


_RL_IMPORT_HINT = (
    "PDF report generation requires the [pdf] extra. Install with:\n"
    "    pip install 'dcm-anonymizer[pdf]'\n"
    "or pip install reportlab"
)


def _require_reportlab() -> None:
    """Fail fast with an actionable hint if reportlab is absent."""
    try:
        import reportlab  # noqa: F401
    except ImportError as exc:  # pragma: no cover — exercised manually
        raise ImportError(_RL_IMPORT_HINT) from exc


# Brand palette (institution-neutral, print-safe).
_INK = "#1a1f2c"
_INK_MUTED = "#525766"
_ACCENT = "#3C5280"
_ACCENT_LIGHT = "#E7EDF6"
_WARN = "#A05A2C"
_OK = "#2D7A3F"


def _truncate_sha(sha: str, head: int = 12, tail: int = 8) -> str:
    if not sha or len(sha) <= head + tail + 3:
        return sha
    return f"{sha[:head]}...{sha[-tail:]}"


def _esc(value: object) -> str:
    """Escape a string for ReportLab Paragraph (XML-ish HTML subset)."""
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_pdf(
    audit: AuditSummary,
    manifest: ComplianceManifest | None,
    output_path: Path,
    *,
    max_record_rows: int = 50,
    max_residual_rows: int = 25,
) -> Path:
    """Render the audit (+ optional manifest) to a professional PDF.

    Returns the output path on success. Raises ``ImportError`` if the
    ``[pdf]`` extra is not installed.
    """
    _require_reportlab()
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        HRFlowable,
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontSize=22,
        leading=26,
        textColor=colors.HexColor(_INK),
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=styles["Normal"],
        fontSize=12,
        leading=15,
        textColor=colors.HexColor(_INK_MUTED),
        spaceAfter=10,
        alignment=TA_LEFT,
    )
    h1_style = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontSize=15,
        leading=18,
        textColor=colors.HexColor(_ACCENT),
        spaceBefore=12,
        spaceAfter=6,
        alignment=TA_LEFT,
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=12,
        leading=15,
        textColor=colors.HexColor(_INK),
        spaceBefore=8,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor(_INK),
        spaceAfter=4,
        alignment=TA_JUSTIFY,
    )
    body_left = ParagraphStyle(
        "BodyLeft",
        parent=body_style,
        alignment=TA_LEFT,
    )
    mono_small = ParagraphStyle(
        "MonoSmall",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        fontName="Courier",
        textColor=colors.HexColor(_INK),
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    callout_style = ParagraphStyle(
        "Callout",
        parent=body_style,
        backColor=colors.HexColor(_ACCENT_LIGHT),
        borderColor=colors.HexColor(_ACCENT),
        borderWidth=0.6,
        borderPadding=8,
        leftIndent=2,
        rightIndent=2,
        spaceBefore=4,
        spaceAfter=8,
    )
    cover_label = ParagraphStyle(
        "CoverLabel",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor(_INK_MUTED),
        spaceAfter=1,
        alignment=TA_LEFT,
    )
    cover_value = ParagraphStyle(
        "CoverValue",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=13,
        textColor=colors.HexColor(_INK),
        fontName="Helvetica-Bold",
        spaceAfter=8,
        alignment=TA_LEFT,
    )
    story: list[object] = []

    # ---------- cover page ----------
    cover_subtitle_bits: list[str] = []
    if manifest is not None:
        cover_subtitle_bits.append(
            f"Regime: {_esc(manifest.regime.full_name)} ({_esc(manifest.regime.jurisdiction)})"
        )
    cover_subtitle_bits.append(
        "Output classification: PSEUDONYMOUS (NOT anonymous per GDPR Art. 4(5))"
    )
    if audit.dry_run:
        cover_subtitle_bits.append("DRY RUN — no files written")

    story.append(Paragraph("DICOM Anonymization Compliance Report", title_style))
    story.append(Paragraph(" · ".join(cover_subtitle_bits), subtitle_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor(_ACCENT)))
    story.append(Spacer(1, 8 * mm))

    # Two-column key/value block on the cover.
    tool_version = manifest.tool_version if manifest is not None else audit.version
    generated_at = manifest.generated_at_utc if manifest is not None else "n/a (audit-only PDF)"
    manifest_sha = manifest.manifest_sha256 if manifest is not None else None
    regime_url = manifest.regime.canonical_url if manifest is not None else None
    days_left = manifest.days_to_enforcement if manifest is not None else None

    def _kv(label: str, value: str) -> Table:
        # Zero the default 6 pt horizontal cell padding so the full colWidth is
        # usable text budget; otherwise a 64-char manifest_sha256 can straddle
        # the column boundary on the cover (TD-052).
        kv = Table(
            [[Paragraph(_esc(label), cover_label)],
             [Paragraph(_esc(value), cover_value)]],
            colWidths=[8.5 * cm],
        )
        kv.setStyle(
            TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ])
        )
        return kv

    cover_left = [
        _kv("Tool", f"dcm-anon {tool_version}"),
        _kv("Generated (UTC)", generated_at),
        _kv("Files processed", str(audit.files_processed)),
        _kv("Files failed", str(audit.files_failed)),
    ]
    cover_right = [
        _kv("Burned-in PHI warnings", str(audit.burned_in_warnings)),
        _kv("Distinct UIDs remapped", str(audit.uid_remapping_count)),
        _kv("Audit SHA-256", _truncate_sha(audit.audit_sha256, 16, 12)),
        _kv("Manifest SHA-256", _truncate_sha(manifest_sha, 16, 12) if manifest_sha else "n/a"),
    ]
    cover_table = Table(
        [[col_l, col_r] for col_l, col_r in zip(cover_left, cover_right, strict=True)],
        colWidths=[8.5 * cm, 8.5 * cm],
    )
    cover_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    story.append(cover_table)
    story.append(Spacer(1, 6 * mm))

    if manifest is not None:
        regime_lines = [
            f"<b>Enforcement date:</b> {_esc(manifest.regime.enforcement_date)}",
        ]
        if days_left is not None:
            regime_lines.append(f"<b>Days until enforcement at generation:</b> {days_left}")
        if regime_url:
            regime_lines.append(f"<b>Canonical text:</b> {_esc(regime_url)}")
        story.append(Paragraph(" · ".join(regime_lines), body_left))
        story.append(Spacer(1, 4 * mm))

    if manifest is not None:
        story.append(Paragraph(_esc(manifest.risk_statement), callout_style))
    else:
        story.append(Paragraph(
            "This PDF documents the engineering operation only. "
            "Compliance disclosures (GDPR Art. 9 lawful basis, HIPAA method declaration, "
            "EU AI Act enforcement context) require running with --manifest-mode.",
            callout_style,
        ))

    story.append(PageBreak())

    # ---------- section: run summary ----------
    story.append(Paragraph("1. Run summary", h1_style))
    summary_rows: list[list[object]] = [
        ["Tool version", Paragraph(_esc(f"dcm-anon {tool_version}"), body_left)],
        ["PS3.15 profile", Paragraph(
            _esc(manifest.ps315_profile if manifest is not None else "Basic Application Level Confidentiality Profile"),
            body_left,
        )],
        ["Files processed", str(audit.files_processed)],
        ["Files failed", str(audit.files_failed)],
        ["Burned-in PHI warnings (HTTP 422 in vault)", str(audit.burned_in_warnings)],
        ["Distinct UIDs remapped", str(audit.uid_remapping_count)],
        ["Dry run", "YES" if audit.dry_run else "no"],
        ["Audit SHA-256",
         Paragraph(f"<font face='Courier' size='9'>{_esc(audit.audit_sha256)}</font>", body_left)],
    ]
    if manifest is not None:
        summary_rows.append([
            "Manifest SHA-256",
            Paragraph(f"<font face='Courier' size='9'>{_esc(manifest.manifest_sha256)}</font>", body_left),
        ])
    summary_table = Table(summary_rows, colWidths=[5.5 * cm, 11.5 * cm])
    summary_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(_ACCENT_LIGHT)),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd5e2")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dde2ec")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(_INK)),
        ])
    )
    story.append(summary_table)

    # ---------- section: per-file records ----------
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("2. Per-file action summary", h1_style))
    record_count = len(audit.records)
    story.append(Paragraph(
        f"{record_count} files in audit; showing first {min(max_record_rows, record_count)}. "
        f"Full machine-readable record in <font face='Courier'>anonymization_audit.json</font>.",
        body_left,
    ))
    record_table_data: list[list[object]] = [[
        Paragraph("<b>#</b>", body_left),
        Paragraph("<b>Source</b>", body_left),
        Paragraph("<b>Tags modified</b>", body_left),
        Paragraph("<b>Burned-in PHI?</b>", body_left),
        Paragraph("<b>Output</b>", body_left),
    ]]
    for idx, rec in enumerate(audit.records[:max_record_rows], start=1):
        out_label = rec.output or "(dry-run)"
        burn_label = "YES" if rec.burned_in_phi_warning else "no"
        burn_color = _WARN if rec.burned_in_phi_warning else _INK_MUTED
        record_table_data.append([
            str(idx),
            Paragraph(f"<font face='Courier' size='8.5'>{_esc(rec.source)}</font>", body_left),
            str(len(rec.tags_modified)),
            Paragraph(f"<font color='{burn_color}'>{burn_label}</font>", body_left),
            Paragraph(f"<font face='Courier' size='8.5'>{_esc(out_label)}</font>", body_left),
        ])
    if record_count > max_record_rows:
        record_table_data.append([
            "",
            Paragraph(
                f"<i>... and {record_count - max_record_rows} more records "
                f"(see <font face='Courier'>anonymization_audit.json</font>).</i>",
                body_left,
            ),
            "", "", "",
        ])
    record_table = Table(
        record_table_data,
        colWidths=[1.0 * cm, 7.0 * cm, 2.5 * cm, 2.5 * cm, 4.0 * cm],
        repeatRows=1,
    )
    record_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_ACCENT_LIGHT)),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd5e2")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dde2ec")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ])
    )
    story.append(record_table)

    if audit.errors:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("2.1 Errors", h2_style))
        err_data: list[list[object]] = [[
            Paragraph("<b>Source</b>", body_left),
            Paragraph("<b>Error type</b>", body_left),
            Paragraph("<b>Message</b>", body_left),
        ]]
        for err in audit.errors:
            err_data.append([
                Paragraph(f"<font face='Courier' size='8.5'>{_esc(err.source)}</font>", body_left),
                Paragraph(f"<font face='Courier' size='8.5'>{_esc(err.error_type)}</font>", body_left),
                Paragraph(_esc(err.error_message), body_left),
            ])
        err_table = Table(err_data, colWidths=[6 * cm, 4 * cm, 7 * cm], repeatRows=1)
        err_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fde9d8")),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2bf95")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#eed3a8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ])
        )
        story.append(err_table)

    # ---------- section: PS3.15 actions + regulatory citations ----------
    if manifest is not None:
        story.append(PageBreak())
        story.append(Paragraph("3. PS3.15 actions and regulatory citations", h1_style))
        story.append(Paragraph(
            f"Action codes follow DICOM PS3.15 Table E.1-1. Citations below are "
            f"resolved under the <b>{_esc(manifest.regime.code.upper())}</b> regime; "
            f"see canonical text at <font face='Courier' size='9'>{_esc(manifest.regime.canonical_url)}</font>.",
            body_left,
        ))
        story.append(Spacer(1, 3 * mm))
        for action in manifest.actions_used:
            block: list[object] = [
                Paragraph(
                    f"Action <font face='Courier'>{_esc(action.code)}</font> "
                    f"— applied <b>{action.count}</b> time(s)",
                    h2_style,
                ),
            ]
            if not action.clauses:
                block.append(Paragraph(
                    "<i>No clauses cited for this action under the selected regime.</i>",
                    body_left,
                ))
            for clause in action.clauses:
                block.append(Paragraph(
                    f"<b>{_esc(clause.citation)}</b> — <i>{_esc(clause.short_title)}</i>",
                    body_left,
                ))
                block.append(Paragraph(_esc(clause.summary), body_left))
                block.append(Paragraph(
                    f"<font face='Courier' size='8.5'>{_esc(clause.url)}</font>",
                    body_left,
                ))
                block.append(Spacer(1, 2 * mm))
            story.append(KeepTogether(block))

        # Audit-trail clauses (only when present, else the heading orphans).
        if manifest.audit_trail_clauses:
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph("3.1 Audit-trail clauses", h2_style))
            story.append(Paragraph(
                "These clauses cover the signed audit log itself, not the per-tag action.",
                body_left,
            ))
            for clause in manifest.audit_trail_clauses:
                story.append(Paragraph(
                    f"<b>{_esc(clause.citation)}</b> — <i>{_esc(clause.short_title)}</i>",
                    body_left,
                ))
                story.append(Paragraph(_esc(clause.summary), body_left))
                story.append(Paragraph(
                    f"<font face='Courier' size='8.5'>{_esc(clause.url)}</font>",
                    body_left,
                ))
                story.append(Spacer(1, 2 * mm))

    # ---------- section: regime-specific disclosures ----------
    if manifest is not None and manifest.regime_disclosures:
        story.append(PageBreak())
        story.append(Paragraph("4. Regime-specific disclosures", h1_style))
        for label, body in manifest.regime_disclosures:
            story.append(Paragraph(_esc(label), h2_style))
            story.append(Paragraph(_esc(body), callout_style))

    # ---------- section: independent output verification ----------
    if manifest is not None and manifest.output_verification is not None:
        story.append(PageBreak())
        story.append(Paragraph("5. Independent output verification", h1_style))
        verification = manifest.output_verification
        status_color = _OK if verification.passed else _WARN
        status_text = "PASSED (no PHI residuals detected)" if verification.passed else "FAILED"
        story.append(Paragraph(
            f"<b>Result:</b> <font color='{status_color}'>{status_text}</font>",
            body_left,
        ))
        v_rows: list[list[object]] = [
            ["Files in sample", f"{verification.files_scanned} of {verification.files_total} total"],
            ["Tags checked per file (independent list)",
             str(verification.metadata_tags_checked_per_file)],
            ["Pixel OCR scan",
             "enabled" if verification.pixel_ocr_enabled else "disabled"],
            ["pytesseract available", str(verification.pixel_ocr_available)],
            ["Residuals found", str(len(verification.residuals))],
        ]
        v_table = Table(v_rows, colWidths=[7 * cm, 10 * cm])
        v_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(_ACCENT_LIGHT)),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd5e2")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dde2ec")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ])
        )
        story.append(v_table)
        story.append(Paragraph(
            "<i>The independent tag list is curated from HIPAA Safe Harbor "
            "&sect;164.514(b)(2) and the TCIA de-identification checklist. "
            "It is intentionally NOT derived from the same internal table used by "
            "the anonymizer, in order to break the self-attestation problem.</i>",
            body_left,
        ))
        if verification.residuals:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph("5.1 Residuals detected", h2_style))
            res_data: list[list[object]] = [[
                Paragraph("<b>File</b>", body_left),
                Paragraph("<b>Tag</b>", body_left),
                Paragraph("<b>Label</b>", body_left),
                Paragraph("<b>HIPAA cat.</b>", body_left),
                Paragraph("<b>Layer</b>", body_left),
                Paragraph("<b>Excerpt</b>", body_left),
            ]]
            for r in verification.residuals[:max_residual_rows]:
                res_data.append([
                    Paragraph(f"<font face='Courier' size='8.5'>{_esc(r.file)}</font>", body_left),
                    Paragraph(f"<font face='Courier' size='8.5'>{_esc(r.tag)}</font>", body_left),
                    Paragraph(_esc(r.tag_label), body_left),
                    Paragraph(_esc(r.hipaa_category), body_left),
                    Paragraph(_esc(r.layer), body_left),
                    Paragraph(f"<font face='Courier' size='8.5'>{_esc(r.value_excerpt)}</font>", body_left),
                ])
            extras = len(verification.residuals) - max_residual_rows
            if extras > 0:
                res_data.append(["", Paragraph(
                    f"<i>... and {extras} more residuals in <font face='Courier'>compliance_manifest.json</font>.</i>",
                    body_left,
                ), "", "", "", ""])
            res_table = Table(
                res_data,
                colWidths=[3.5 * cm, 2.0 * cm, 3.0 * cm, 2.5 * cm, 2.0 * cm, 4.0 * cm],
                repeatRows=1,
            )
            res_table.setStyle(
                TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fde9d8")),
                    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2bf95")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#eed3a8")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ])
            )
            story.append(res_table)

    # ---------- section: authoritative guidance ----------
    if manifest is not None and manifest.guidance_references:
        story.append(PageBreak())
        story.append(Paragraph("6. Authoritative guidance applied", h1_style))
        story.append(Paragraph(
            "Post-2024 documents that regulators apply when assessing the practice. "
            "Cited so a reviewer can verify the tool tracks current interpretation.",
            body_left,
        ))
        story.append(Spacer(1, 3 * mm))
        for ref in manifest.guidance_references:
            story.append(Paragraph(
                f"<b>{_esc(ref.title)}</b> — {_esc(ref.publisher)} ({_esc(ref.published)})",
                body_left,
            ))
            story.append(Paragraph(_esc(ref.relevance), body_left))
            story.append(Paragraph(
                f"<font face='Courier' size='8.5'>{_esc(ref.url)}</font>",
                body_left,
            ))
            story.append(Spacer(1, 2 * mm))

    # ---------- section: verification + disclaimer ----------
    story.append(PageBreak())
    story.append(Paragraph("7. How to verify this report", h1_style))
    if manifest is not None:
        story.append(Paragraph(
            "This PDF is the printable evidence pack. The authoritative artefacts are "
            "the JSON manifest and the JSON audit log; both are SHA-256 chained. "
            "To verify the manifest against its audit on an independent machine:",
            body_left,
        ))
        story.append(Paragraph(
            "<font face='Courier' size='9'>"
            "dcm-anon --verify-manifest compliance_manifest.json --audit anonymization_audit.json"
            "</font>",
            mono_small,
        ))
        story.append(Paragraph(
            "A successful verification recomputes the canonical SHA-256 of the manifest "
            "payload and asserts it matches the declared <font face='Courier'>manifest_sha256</font>, "
            "and asserts that file counts and the <font face='Courier'>audit_sha256</font> on the "
            "manifest match the supplied audit. Any retroactive edit of either file makes the chain fail.",
            body_left,
        ))
    else:
        story.append(Paragraph(
            "This PDF was generated from an audit log only (no compliance manifest). "
            "Re-run the anonymization with <font face='Courier'>--manifest-mode "
            "{gdpr|hipaa|eu-ai-act}</font> to attach regulatory citations and a verifiable manifest hash.",
            body_left,
        ))

    if manifest is not None:
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph("8. Disclaimer", h1_style))
        story.append(Paragraph(_esc(manifest.disclaimer), callout_style))

    # ---------- footer template ----------
    audit_sha_short = _truncate_sha(audit.audit_sha256, 10, 6)

    def _on_page(canvas: Any, _doc: Any) -> None:
        page_num = canvas.getPageNumber()
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor(_INK_MUTED))
        canvas.drawString(
            2 * cm,
            1.2 * cm,
            f"dcm-anon | audit {audit_sha_short} | page {page_num}",
        )
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="DICOM Anonymization Compliance Report",
        author="dcm-anon",
        subject=(
            f"Compliance report - "
            f"{manifest.regime.code if manifest is not None else 'audit-only'}"
        ),
    )
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return output_path


__all__ = ["render_pdf"]
