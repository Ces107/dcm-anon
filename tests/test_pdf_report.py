"""Tests for the PDF compliance report.

The PDF stack is the printable evidence pack that an auditor or a DPO can
attach to a procurement package. These tests assert that:

- A run with both audit and manifest produces a valid multi-page PDF.
- A run with only the audit (no manifest) produces a smaller but still
  valid PDF.
- The PDF contains the load-bearing section titles and the audit SHA.
- The CLI ``--pdf-report`` flag wires through end-to-end.

reportlab is an optional install; tests skip cleanly if it is missing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

reportlab = pytest.importorskip("reportlab")
pypdf = pytest.importorskip("pypdf")

from dcm_anon import UIDMapper, anonymize_file  # noqa: E402 — after importorskip
from dcm_anon.audit import AuditSummary  # noqa: E402
from dcm_anon.cli import main as cli_main  # noqa: E402
from dcm_anon.manifest import build_manifest  # noqa: E402
from dcm_anon.pdf_report import render_pdf  # noqa: E402
from tests.conftest import _make_synthetic_dcm  # noqa: E402


@pytest.fixture
def small_audit(tmp_path: Path) -> AuditSummary:
    """Anonymize one synthetic DICOM and return the AuditSummary."""
    src = tmp_path / "synth.dcm"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _make_synthetic_dcm(src, burned_in=False)
    mapper = UIDMapper(salt="pdf-test")
    record = anonymize_file(src, out_dir / "synth.dcm", mapper)
    from dcm_anon.audit import audit_sha256

    return AuditSummary(
        version="0.4.0",
        files_processed=1,
        files_failed=0,
        burned_in_warnings=0,
        uid_remapping_count=mapper.size(),
        dry_run=False,
        records=[record],
        errors=[],
        audit_sha256=audit_sha256([record]),
    )


def _assert_pdf_magic(path: Path) -> None:
    """The first 5 bytes of any conformant PDF are b'%PDF-'."""
    with path.open("rb") as fh:
        head = fh.read(5)
    assert head == b"%PDF-", f"expected %PDF- header, got {head!r} in {path}"


def _read_all_text(path: Path) -> str:
    reader = pypdf.PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_render_pdf_with_manifest_passes_validations(
    tmp_path: Path, small_audit: AuditSummary
) -> None:
    manifest = build_manifest(small_audit, "gdpr", tool_version="0.4.0")
    pdf_path = tmp_path / "report.pdf"

    written = render_pdf(small_audit, manifest, pdf_path)

    assert written == pdf_path
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 2000, "PDF unexpectedly small"
    _assert_pdf_magic(pdf_path)

    reader = pypdf.PdfReader(str(pdf_path))
    assert len(reader.pages) >= 2, "expected at least cover + content page"

    text = _read_all_text(pdf_path)
    # Load-bearing strings — if any of these disappear the procurement
    # value of the report is gone.
    assert "DICOM Anonymization Compliance Report" in text
    assert "Run summary" in text
    assert "PS3.15" in text
    assert "PSEUDONYMOUS" in text
    assert small_audit.audit_sha256 in text or small_audit.audit_sha256[:16] in text
    assert manifest.regime.code.upper() in text or manifest.regime.full_name in text


def test_render_pdf_audit_only_omits_manifest_sections(
    tmp_path: Path, small_audit: AuditSummary
) -> None:
    pdf_path = tmp_path / "audit-only.pdf"
    render_pdf(small_audit, None, pdf_path)

    _assert_pdf_magic(pdf_path)
    text = _read_all_text(pdf_path)
    assert "DICOM Anonymization Compliance Report" in text
    assert "Run summary" in text
    # The regulatory-citations section should NOT appear without manifest.
    assert "PS3.15 actions and regulatory citations" not in text
    # Audit-only mode should explicitly hint the user.
    assert "audit-only" in text or "--manifest-mode" in text


def test_render_pdf_errors_section_renders_when_failures_present(
    tmp_path: Path, small_audit: AuditSummary
) -> None:
    from dataclasses import replace

    from dcm_anon.audit import ProcessingError

    err = ProcessingError(
        source="bad.dcm",
        error_type="InvalidDicomError",
        error_message="File is not a valid DICOM dataset",
    )
    failing = replace(small_audit, files_failed=1, errors=[err])
    pdf_path = tmp_path / "with-errors.pdf"
    render_pdf(failing, None, pdf_path)

    text = _read_all_text(pdf_path)
    assert "Errors" in text
    assert "InvalidDicomError" in text
    assert "bad.dcm" in text


def test_cli_pdf_report_auto_path(tmp_path: Path) -> None:
    """``--pdf-report auto`` writes to <dst>/COMPLIANCE_REPORT.pdf."""
    src = tmp_path / "input.dcm"
    out = tmp_path / "out"
    _make_synthetic_dcm(src, burned_in=False)

    rc = cli_main([
        str(src), str(out),
        "--manifest-mode", "gdpr",
        "--pdf-report", "auto",
        "--quiet",
    ])
    assert rc == 0
    pdf_path = out / "COMPLIANCE_REPORT.pdf"
    assert pdf_path.exists(), f"expected {pdf_path} after --pdf-report auto"
    _assert_pdf_magic(pdf_path)

    # The manifest and audit must also have been written (regression).
    assert (out / "compliance_manifest.json").exists()
    assert (out / "anonymization_audit.json").exists()


def test_cli_pdf_report_explicit_path(tmp_path: Path) -> None:
    src = tmp_path / "input.dcm"
    out = tmp_path / "out"
    explicit_pdf = tmp_path / "custom-name.pdf"
    _make_synthetic_dcm(src, burned_in=False)

    rc = cli_main([
        str(src), str(out),
        "--manifest-mode", "hipaa",
        "--pdf-report", str(explicit_pdf),
        "--quiet",
    ])
    assert rc == 0
    assert explicit_pdf.exists()
    _assert_pdf_magic(explicit_pdf)


def test_cli_pdf_report_without_manifest_still_writes_pdf(tmp_path: Path) -> None:
    """The PDF flag is independent of --manifest-mode (audit-only mode)."""
    src = tmp_path / "input.dcm"
    out = tmp_path / "out"
    _make_synthetic_dcm(src, burned_in=False)

    rc = cli_main([
        str(src), str(out),
        "--pdf-report", "auto",
        "--quiet",
    ])
    assert rc == 0
    pdf_path = out / "COMPLIANCE_REPORT.pdf"
    assert pdf_path.exists()
    _assert_pdf_magic(pdf_path)
    text = _read_all_text(pdf_path)
    assert "audit-only" in text or "--manifest-mode" in text


def test_render_pdf_eu_ai_act_regime(tmp_path: Path, small_audit: AuditSummary) -> None:
    """EU AI Act manifest should surface the enforcement-context disclosure."""
    manifest = build_manifest(small_audit, "eu-ai-act", tool_version="0.4.0")
    pdf_path = tmp_path / "ai-act.pdf"
    render_pdf(small_audit, manifest, pdf_path)
    text = _read_all_text(pdf_path)
    assert "EU AI Act" in text or "AI ACT" in text.upper()
    # The disclosure body talks about enforcement-context; presence is asserted by label.
    assert "enforcement" in text.lower()
