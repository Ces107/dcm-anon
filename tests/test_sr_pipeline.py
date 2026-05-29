"""Integration: the SR content scrubber wired into the pipeline (CF-03).

Unit behaviour of the walker lives in test_sr.py; these assert the pipeline
wiring — the fail-closed SR gate, that --scrub-sr clears it and actually scrubs
the content tree on the same dataset, and that Clean Structured Content (113104)
is stamped ONLY when the SR pass ran.
"""
from __future__ import annotations

from pathlib import Path

from pydicom import dcmread
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from dcm_anon import UIDMapper, anonymize_file
from dcm_anon.safety import RISK_SR_CONTENT
from tests.conftest import _make_synthetic_dcm


def _sr_variant(tmp_path: Path) -> Path:
    base = tmp_path / "base.dcm"
    _make_synthetic_dcm(base)
    ds = dcmread(base)
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.88.11"  # Basic Text SR
    text_item = Dataset()
    text_item.ValueType = "TEXT"
    text_item.TextValue = "Patient SSN 123-45-6789, email a@b.com, seen 01/02/2023"
    ds.ContentSequence = Sequence([text_item])
    out = tmp_path / "sr.dcm"
    ds.save_as(out, enforce_file_format=True)
    return out


def _provenance_codes(ds: object) -> set[str]:
    seq = getattr(ds, "DeidentificationMethodCodeSequence", None)
    if seq is None:
        return set()
    return {item.CodeValue for item in seq}


class TestSrPipeline:
    def test_sr_without_scrub_is_fail_closed(self, tmp_path: Path) -> None:
        src = _sr_variant(tmp_path)
        rec = anonymize_file(src, tmp_path / "out.dcm", UIDMapper(salt="t"))
        assert RISK_SR_CONTENT in rec.unresolved_risks
        assert rec.sr_touches == []

    def test_scrub_sr_clears_gate_and_redacts_text(self, tmp_path: Path) -> None:
        src = _sr_variant(tmp_path)
        out = tmp_path / "out.dcm"
        rec = anonymize_file(src, out, UIDMapper(salt="t"), scrub_sr=True)

        assert RISK_SR_CONTENT not in rec.unresolved_risks
        assert rec.sr_touches  # at least the TEXT node was redacted

        result = dcmread(out)
        text = str(result.ContentSequence[0].TextValue)
        assert "123-45-6789" not in text
        assert "a@b.com" not in text
        # Clean Structured Content provenance is stamped only because SR ran.
        assert "113104" in _provenance_codes(result)

    def test_no_sr_run_does_not_claim_113104(self, tmp_path: Path) -> None:
        src = _sr_variant(tmp_path)
        out = tmp_path / "out.dcm"
        # Waive the gate WITHOUT scrubbing: 113104 must NOT be claimed.
        anonymize_file(src, out, UIDMapper(salt="t"), allow_sr=True)
        assert "113104" not in _provenance_codes(dcmread(out))
