"""Tests for the compliance manifest stack.

Covers ``regulatory_mapping``, ``verify_output``, ``manifest``, and the
CLI surface added in v0.3.0.

Run with:
    pytest test_manifest.py -v
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydicom import dcmread

from anonymize import UIDMapper, anonymize_file
from audit import AuditSummary, audit_sha256
from cli import main as cli_main
from conftest import _make_synthetic_dcm
from manifest import (
    _PS315_PROFILE_NAME,
    build_manifest,
    render_markdown,
    supported_regimes,
    verify_manifest,
)
from regulatory_mapping import (
    AUTHORITATIVE_GUIDANCE,
    PSEUDONYMOUS_RISK_STATEMENT,
    audit_trail_clauses_for,
    clauses_for_action,
    get_regime,
    guidance_for,
)
from verify_output import (
    INDEPENDENT_PHI_TAGS,
    PixelOCRUnavailableError,
    independent_tag_list_size,
    scan_outputs,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anonymized_dir(tmp_path: Path) -> tuple[Path, AuditSummary]:
    """Anonymize one synthetic DICOM and return ``(dir, audit_summary)``."""
    src = tmp_path / "in.dcm"
    out = tmp_path / "out"
    out.mkdir()
    _make_synthetic_dcm(src, burned_in=False)
    mapper = UIDMapper(salt="test-cohort")
    record = anonymize_file(src, out / "in.dcm", mapper)
    summary = AuditSummary(
        version="0.3.0",
        files_processed=1,
        files_failed=0,
        burned_in_warnings=0,
        uid_remapping_count=mapper.size(),
        dry_run=False,
        records=[record],
        errors=[],
        audit_sha256=audit_sha256([record]),
    )
    return (out, summary)


# ---------------------------------------------------------------------------
# 1. regulatory_mapping
# ---------------------------------------------------------------------------

class TestRegulatoryRegimes:
    def test_three_regimes_supported(self) -> None:
        assert set(supported_regimes()) == {"eu-ai-act", "hipaa", "gdpr"}

    def test_get_regime_case_insensitive(self) -> None:
        assert get_regime("EU-AI-ACT").code == "eu-ai-act"
        assert get_regime("  hipaa  ").code == "hipaa"

    def test_get_regime_rejects_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unknown regulatory regime"):
            get_regime("ccpa")

    def test_eu_ai_act_enforcement_date_is_currently_binding_law(self) -> None:
        """Annex III high-risk obligations bind from 2026-08-02 under Reg. (EU) 2024/1689.

        The Digital Omnibus on AI (provisional Council-Parliament agreement,
        7 May 2026) would defer this to 2027-12-02 but has NOT been formally
        adopted or published in the OJEU as of 2026-05-16. The manifest must
        cite the actually-binding date, not the proposed-and-pending one.
        """
        regime = get_regime("eu-ai-act")
        assert regime.enforcement_date == "2026-08-02"

    def test_canonical_urls_https(self) -> None:
        for code in supported_regimes():
            assert get_regime(code).canonical_url.startswith("https://")


class TestActionClauses:
    @pytest.mark.parametrize("action", ["X", "Z", "U", "D"])
    @pytest.mark.parametrize("regime", ["eu-ai-act", "hipaa", "gdpr"])
    def test_every_action_has_one_clause_per_regime(self, action: str, regime: str) -> None:
        clauses = clauses_for_action(action, regime)
        assert len(clauses) == 1
        assert clauses[0].regime == regime
        assert clauses[0].url.startswith("https://")

    def test_action_x_for_eu_ai_act_cites_correct_paragraphs(self) -> None:
        """Critical: must NOT cite Art. 10(5) (bias-detection exception)."""
        clauses = clauses_for_action("X", "eu-ai-act")
        citation = clauses[0].citation
        assert "10(2)" in citation
        assert "10(3)" in citation
        assert "10(5)" not in citation

    def test_action_z_for_eu_ai_act_delegates_to_gdpr_32(self) -> None:
        """Critical: AI Act for Z must mention Art. 32 delegation, not Art. 10(5)."""
        clauses = clauses_for_action("Z", "eu-ai-act")
        assert "10(1)" in clauses[0].citation
        assert "GDPR Art. 32" in clauses[0].citation

    def test_action_u_for_hipaa_cites_164_514_c(self) -> None:
        """Critical: UID remap is the textbook 164.514(c) re-identification code."""
        clauses = clauses_for_action("U", "hipaa")
        assert "164.514(c)" in clauses[0].citation

    def test_action_d_for_gdpr_uses_art_32_not_5_1_c(self) -> None:
        """Dummy substitution is a safeguard (Art. 32), not minimisation."""
        clauses = clauses_for_action("D", "gdpr")
        assert "Art. 32(1)(a)" in clauses[0].citation
        assert "Recital 26" in clauses[0].citation

    def test_unknown_action_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            clauses_for_action("Q", "gdpr")


class TestAuditTrailClauses:
    def test_eu_ai_act_audit_trail_uses_art_12_18(self) -> None:
        """Critical: audit trail must cite Art. 12+18, NOT Art. 10(5)(c)/(f)."""
        clauses = audit_trail_clauses_for("eu-ai-act")
        citations = [c.citation for c in clauses]
        assert any("Art. 12" in c for c in citations)
        assert any("Art. 18" in c for c in citations)
        assert not any("10(5)" in c for c in citations)

    def test_hipaa_audit_trail_uses_164_312_b(self) -> None:
        clauses = audit_trail_clauses_for("hipaa")
        assert any("164.312(b)" in c.citation for c in clauses)

    def test_gdpr_audit_trail_uses_art_30_and_5_2(self) -> None:
        clauses = audit_trail_clauses_for("gdpr")
        citations = [c.citation for c in clauses]
        assert any("Art. 30" in c for c in citations)
        assert any("Art. 5(2)" in c for c in citations)


class TestGuidance:
    @pytest.mark.parametrize("regime", ["eu-ai-act", "hipaa", "gdpr"])
    def test_every_regime_has_authoritative_guidance(self, regime: str) -> None:
        refs = guidance_for(regime)
        assert len(refs) >= 1
        for ref in refs:
            assert ref.url.startswith("https://")
            assert ref.published != ""

    def test_gdpr_includes_edpb_pseudonymisation_guidelines(self) -> None:
        refs = guidance_for("gdpr")
        titles = [r.title for r in refs]
        assert any("Pseudonymisation" in t for t in titles)

    def test_eu_ai_act_includes_mdcg_2025_6(self) -> None:
        refs = guidance_for("eu-ai-act")
        titles = [r.title for r in refs]
        assert any("MDCG 2025-6" in t for t in titles)

    def test_hipaa_includes_nist_800_66_r2(self) -> None:
        refs = guidance_for("hipaa")
        titles = [r.title for r in refs]
        assert any("SP 800-66" in t for t in titles)


# ---------------------------------------------------------------------------
# 2. verify_output (independent PHI residual scanner)
# ---------------------------------------------------------------------------

class TestIndependentTagList:
    def test_independent_list_is_substantial(self) -> None:
        """Sanity floor: at least 40 tags drawn from HIPAA Safe Harbor + TCIA."""
        assert independent_tag_list_size() >= 40

    def test_independent_list_covers_18_hipaa_categories(self) -> None:
        """At least 6 of the 18 HIPAA Safe Harbor sub-categories appear."""
        categories = {entry[3] for entry in INDEPENDENT_PHI_TAGS}
        assert len(categories) >= 6

    def test_red_team_5_gaps_now_covered(self) -> None:
        """Tags identified as gaps by Red Team #5 (technical edge cases)."""
        listed_tags = {(g, e) for (g, e, _, _) in INDEPENDENT_PHI_TAGS}
        # Red Team #5 specifically called out these as missing:
        assert (0x0008, 0x1070) in listed_tags  # OperatorsName
        assert (0x0010, 0x4000) in listed_tags  # PatientComments
        assert (0x0008, 0x1080) in listed_tags  # AdmittingDiagnosesDescription
        assert (0x0040, 0x0006) in listed_tags  # ScheduledPerformingPhysicianName


class TestScanOutputs:
    def test_clean_output_passes(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        out_dir, _ = anonymized_dir
        result = scan_outputs(out_dir, sample_size=10)
        assert result.passed
        assert result.files_scanned == 1
        assert result.metadata_tags_checked_per_file >= 30

    def test_tampered_output_flags_residuals(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        """Inject PHI back into an output file, scan, expect residuals."""
        out_dir, _ = anonymized_dir
        target = next(out_dir.glob("*.dcm"))
        ds = dcmread(target)
        ds.PatientName = "Real^Name"
        ds.save_as(target, enforce_file_format=True)
        result = scan_outputs(out_dir, sample_size=10)
        assert not result.passed
        assert any("PatientName" in r.tag_label for r in result.residuals)

    def test_sample_size_zero_scans_nothing(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        out_dir, _ = anonymized_dir
        result = scan_outputs(out_dir, sample_size=0)
        assert result.files_scanned == 0
        assert result.passed  # vacuously

    def test_pixel_ocr_default_off(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        out_dir, _ = anonymized_dir
        result = scan_outputs(out_dir, sample_size=1)
        assert not result.pixel_ocr_enabled

    def test_strict_ocr_raises_when_tesseract_missing(
        self, anonymized_dir: tuple[Path, AuditSummary]
    ) -> None:
        """Red Team #5 fix: false green from silent OCR degradation is unacceptable."""
        out_dir, _ = anonymized_dir
        # pytesseract is not installed in CI; strict_ocr=True must raise.
        with pytest.raises(PixelOCRUnavailableError):
            scan_outputs(out_dir, sample_size=1, pixel_ocr=True, strict_ocr=True)

    def test_strict_ocr_false_degrades_quietly(
        self, anonymized_dir: tuple[Path, AuditSummary]
    ) -> None:
        out_dir, _ = anonymized_dir
        result = scan_outputs(
            out_dir, sample_size=1, pixel_ocr=True, strict_ocr=False
        )
        # No exception; pixel_ocr_available reflects the truth.
        assert result.pixel_ocr_enabled
        # pixel_ocr_available may be True if pytesseract IS installed.
        # We do not assert its value — only that we did not crash.


# ---------------------------------------------------------------------------
# 2b. Cross-file UID linkage (Red Team #5 RT-STRUCT-style attack)
# ---------------------------------------------------------------------------

class TestCrossFileUIDLinkage:
    """RT-STRUCT-style: the same source UID appearing in multiple files of a
    batch must remap to the SAME new UID. ``UIDMapper`` is initialised once
    per :func:`anonymize_path` invocation in :mod:`pipeline`; this test
    locks that invariant against regression.
    """

    def test_same_source_uid_remapped_consistently_across_files(
        self, tmp_path: Path
    ) -> None:
        from anonymize import anonymize_path
        src_dir = tmp_path / "in"
        out_dir = tmp_path / "out"
        src_dir.mkdir()
        # Two files with the SAME StudyInstanceUID — simulates RT-STRUCT
        # referencing the same CT study UID.
        for name in ("a.dcm", "b.dcm"):
            path = src_dir / name
            _make_synthetic_dcm(path, burned_in=False)
        # Force both files to share a StudyInstanceUID by post-editing.
        from pydicom import dcmread
        shared_uid = "1.2.3.4.5.6.7.8.9.0.RT.SHARED.STUDY.UID"
        for name in ("a.dcm", "b.dcm"):
            ds = dcmread(src_dir / name)
            ds.StudyInstanceUID = shared_uid
            ds.save_as(src_dir / name, enforce_file_format=True)

        anonymize_path(src_dir, out_dir, salt="rt-test")

        out_a = dcmread(out_dir / "a.dcm")
        out_b = dcmread(out_dir / "b.dcm")
        assert str(out_a.StudyInstanceUID) == str(out_b.StudyInstanceUID), (
            "Shared source StudyInstanceUID must remap to identical new UID "
            "across all files in the same anonymize_path() invocation, "
            "or RT-STRUCT cross-references would break."
        )
        # And the new UID must differ from the original.
        assert str(out_a.StudyInstanceUID) != shared_uid


# ---------------------------------------------------------------------------
# 3. manifest
# ---------------------------------------------------------------------------

class TestBuildManifest:
    def test_build_succeeds_for_each_regime(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        for code in supported_regimes():
            m = build_manifest(summary, code, now="2026-05-13T12:00:00Z", today=date(2026, 5, 13))
            assert m.regime.code == code
            assert m.audit_sha256 == summary.audit_sha256
            assert len(m.manifest_sha256) == 64

    def test_days_to_enforcement_positive_for_eu_ai_act(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "eu-ai-act", today=date(2026, 5, 13))
        # Under Reg. (EU) 2024/1689 as enacted: 2026-05-13 -> 2026-08-02 = 81 days.
        assert m.days_to_enforcement == 81

    def test_days_to_enforcement_none_after_deadline(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "eu-ai-act", today=date(2030, 1, 1))
        assert m.days_to_enforcement is None

    def test_classification_is_pseudonymous(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "gdpr")
        assert m.output_classification == "pseudonymous"
        assert m.risk_statement == PSEUDONYMOUS_RISK_STATEMENT

    def test_ps315_profile_name_recorded(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "gdpr")
        assert m.ps315_profile == _PS315_PROFILE_NAME

    def test_action_counts_match_audit(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "gdpr")
        total = sum(a.count for a in m.actions_used)
        # Total counted actions should equal total tags_modified across records
        from_audit = sum(len(r.tags_modified) for r in summary.records)
        assert total == from_audit

    def test_guidance_refs_attached(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        for code in supported_regimes():
            m = build_manifest(summary, code)
            assert len(m.guidance_references) == len(AUTHORITATIVE_GUIDANCE[code])

    def test_hipaa_carries_expert_determination_disclaimer(
        self, anonymized_dir: tuple[Path, AuditSummary]
    ) -> None:
        """Red Team #2 fix: tool ≠ HIPAA Expert Determination expert."""
        _, summary = anonymized_dir
        m = build_manifest(summary, "hipaa")
        labels = [label for label, _ in m.regime_disclosures]
        assert any("HIPAA method declaration" in label for label in labels)
        body = next(body for label, body in m.regime_disclosures if "HIPAA" in label)
        assert "SAFE HARBOR ONLY" in body
        assert "164.514(b)(2)" in body
        assert "164.514(b)(1)" in body  # references Expert Determination

    def test_gdpr_carries_art9_disclosure(
        self, anonymized_dir: tuple[Path, AuditSummary]
    ) -> None:
        """Red Team #2 fix: missing Art. 9 lawful basis was the gap a DPA hits first."""
        _, summary = anonymized_dir
        m = build_manifest(summary, "gdpr")
        labels = [label for label, _ in m.regime_disclosures]
        assert any("Art. 9" in label for label in labels)
        body = next(body for label, body in m.regime_disclosures if "Art. 9" in label)
        assert "NOT ESTABLISHED BY THIS TOOL" in body
        assert "Art. 9(2)" in body

    def test_eu_ai_act_carries_deadline_context(
        self, anonymized_dir: tuple[Path, AuditSummary]
    ) -> None:
        """Red Team #1 fix: Digital Omnibus moved the deadline; surface it."""
        _, summary = anonymized_dir
        m = build_manifest(summary, "eu-ai-act")
        labels = [label for label, _ in m.regime_disclosures]
        assert any("enforcement context" in label.lower() for label in labels)
        body = next(
            body for label, body in m.regime_disclosures
            if "enforcement context" in label.lower()
        )
        assert "Digital Omnibus" in body
        # The body must mention both the currently-binding date and the
        # proposed-but-pending deferred dates to be defensible to a DPO.
        assert "2026-08-02" in body
        assert "2027-12-02" in body
        assert "2028-08-02" in body


class TestVerifyManifest:
    def test_clean_manifest_verifies(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "eu-ai-act")
        ok, reasons = verify_manifest(m, summary)
        assert ok
        assert reasons == []

    def test_tampered_field_detected(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "eu-ai-act")
        manifest_dict = m.as_dict()
        manifest_dict["files_processed"] = 999
        ok, reasons = verify_manifest(manifest_dict, summary)
        assert not ok
        assert any("files_processed mismatch" in r for r in reasons)
        assert any("manifest_sha256 invalid" in r for r in reasons)

    def test_audit_sha_mismatch_detected(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "eu-ai-act")
        manifest_dict = m.as_dict()
        manifest_dict["audit_sha256"] = "0" * 64
        ok, reasons = verify_manifest(manifest_dict, summary)
        assert not ok
        assert any("audit_sha256 mismatch" in r for r in reasons)

    def test_verify_accepts_dict_inputs(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "gdpr")
        ok, _ = verify_manifest(m.as_dict(), summary.as_dict())
        assert ok


class TestManifestWithVerification:
    def test_verification_embedded_in_hash(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        out_dir, summary = anonymized_dir
        verification = scan_outputs(out_dir, sample_size=10)
        m_with = build_manifest(summary, "gdpr", output_verification=verification)
        m_without = build_manifest(
            summary, "gdpr", output_verification=None,
            now=m_with.generated_at_utc, today=date(2026, 5, 13),
        )
        # Different verification payloads at the same generation time
        # must produce different manifest hashes.
        assert m_with.manifest_sha256 != m_without.manifest_sha256

    def test_verification_round_trips_through_verify(
        self, anonymized_dir: tuple[Path, AuditSummary]
    ) -> None:
        out_dir, summary = anonymized_dir
        verification = scan_outputs(out_dir, sample_size=10)
        m = build_manifest(summary, "gdpr", output_verification=verification)
        ok, _ = verify_manifest(m, summary)
        assert ok


class TestMarkdownRender:
    def test_render_includes_classification_block(
        self, anonymized_dir: tuple[Path, AuditSummary]
    ) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "eu-ai-act", today=date(2026, 5, 13))
        md = render_markdown(m)
        assert "Output classification" in md
        assert "pseudonymous" in md
        # 2026-05-13 -> 2026-08-02 (current binding AI Act enforcement) = 81 days.
        assert "**Days remaining at generation:** 81" in md
        assert "EDPB Guidelines 01/2025" in md or "MDCG 2025-6" in md

    def test_render_includes_disclaimer(self, anonymized_dir: tuple[Path, AuditSummary]) -> None:
        _, summary = anonymized_dir
        m = build_manifest(summary, "gdpr")
        md = render_markdown(m)
        assert "ENGINEERING ARTIFACT" in md
        assert "NOT LEGAL ADVICE" in md

    def test_render_includes_verification_section(
        self, anonymized_dir: tuple[Path, AuditSummary]
    ) -> None:
        out_dir, summary = anonymized_dir
        verification = scan_outputs(out_dir, sample_size=10)
        m = build_manifest(summary, "gdpr", output_verification=verification)
        md = render_markdown(m)
        assert "Independent output verification" in md
        assert "PASSED" in md


# ---------------------------------------------------------------------------
# 4. CLI integration
# ---------------------------------------------------------------------------

class TestManifestCLI:
    def test_emits_both_manifest_files(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src, burned_in=False)
        dst = tmp_path / "out"
        rc = cli_main([
            str(src), str(dst),
            "--manifest-mode", "eu-ai-act",
            "--quiet",
        ])
        assert rc == 0
        assert (dst / "compliance_manifest.json").exists()
        assert (dst / "COMPLIANCE_MANIFEST.md").exists()
        data = json.loads((dst / "compliance_manifest.json").read_text())
        assert data["regime"]["code"] == "eu-ai-act"
        assert data["output_classification"] == "pseudonymous"

    def test_verify_output_attached(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src, burned_in=False)
        dst = tmp_path / "out"
        rc = cli_main([
            str(src), str(dst),
            "--manifest-mode", "gdpr",
            "--verify-output",
            "--quiet",
        ])
        assert rc == 0
        data = json.loads((dst / "compliance_manifest.json").read_text())
        assert data["output_verification"]["passed"] is True
        assert data["output_verification"]["files_scanned"] >= 1

    def test_verify_manifest_pass(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src, burned_in=False)
        dst = tmp_path / "out"
        cli_main([str(src), str(dst), "--manifest-mode", "hipaa", "--quiet"])
        rc = cli_main([
            "--verify-manifest", str(dst / "compliance_manifest.json"),
            "--audit", str(dst / "anonymization_audit.json"),
            "--quiet",
        ])
        assert rc == 0

    def test_verify_manifest_fail_on_tamper(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src, burned_in=False)
        dst = tmp_path / "out"
        cli_main([str(src), str(dst), "--manifest-mode", "hipaa", "--quiet"])
        manifest_path = dst / "compliance_manifest.json"
        data = json.loads(manifest_path.read_text())
        data["files_processed"] = 42
        manifest_path.write_text(json.dumps(data))
        rc = cli_main([
            "--verify-manifest", str(manifest_path),
            "--audit", str(dst / "anonymization_audit.json"),
            "--quiet",
        ])
        assert rc == 1

    def test_verify_manifest_missing_audit_returns_2(self, tmp_path: Path) -> None:
        fake = tmp_path / "fake.json"
        fake.write_text("{}")
        rc = cli_main(["--verify-manifest", str(fake), "--quiet"])
        assert rc == 2

    def test_invalid_regime_rejected_by_argparse(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src, burned_in=False)
        with pytest.raises(SystemExit):
            cli_main([str(src), str(tmp_path / "out"), "--manifest-mode", "ccpa"])
