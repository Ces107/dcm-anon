"""Fail-closed safety gates (CF-04 + CF-10 + face re-id).

A header de-identifier must NOT certify clean what it cannot clear: burned-in
pixels (US/SC), recognizable faces (head CT/MR), and encapsulated documents.
These assert the gate fires (audit risk + CLI exit 3) and that explicit waivers
clear it.
"""
from __future__ import annotations

from pathlib import Path

from pydicom import dcmread

from dcm_anon import UIDMapper, anonymize_file, main
from dcm_anon.safety import RISK_BURNED_IN, RISK_ENCAPSULATED, RISK_FACE
from tests.conftest import _make_synthetic_dcm

_ENCAPSULATED_PDF_SOP = "1.2.840.10008.5.1.4.1.1.104.1"


def _variant(tmp_path: Path, **attrs: object) -> Path:
    """A synthetic DICOM with the given attributes overridden, re-saved."""
    base = tmp_path / "base.dcm"
    _make_synthetic_dcm(base)
    ds = dcmread(base)
    for key, value in attrs.items():
        setattr(ds, key, value)
    out = tmp_path / "variant.dcm"
    ds.save_as(out, enforce_file_format=True)
    return out


def _risks(src: Path, **kwargs: object) -> list[str]:
    rec = anonymize_file(src, src.with_name("out.dcm"), UIDMapper(salt="t"), **kwargs)  # type: ignore[arg-type]
    return rec.unresolved_risks


class TestSafetyGates:
    def test_ultrasound_triggers_burned_in_risk(self, tmp_path: Path) -> None:
        src = _variant(tmp_path, Modality="US", BurnedInAnnotation="NO")
        assert RISK_BURNED_IN in _risks(src)

    def test_head_mr_triggers_face_risk(self, tmp_path: Path) -> None:
        src = _variant(tmp_path, Modality="MR", StudyDescription="Brain MRI without contrast")
        assert RISK_FACE in _risks(src)

    def test_encapsulated_pdf_triggers_risk(self, tmp_path: Path) -> None:
        src = _variant(tmp_path, SOPClassUID=_ENCAPSULATED_PDF_SOP)
        assert RISK_ENCAPSULATED in _risks(src)

    def test_chest_ct_has_no_unresolved_risk(self, tmp_path: Path) -> None:
        # The default synthetic is a chest CT — none of the gates should fire.
        src = _variant(tmp_path)
        assert _risks(src) == []

    def test_waiver_clears_burned_in_risk(self, tmp_path: Path) -> None:
        src = _variant(tmp_path, Modality="US")
        assert _risks(src, allow_burned_in=True) == []

    def test_cli_fails_closed_with_exit_3(self, tmp_path: Path) -> None:
        src = _variant(tmp_path, Modality="US")
        rc = main([str(src), str(tmp_path / "out"), "--quiet"])
        assert rc == 3

    def test_cli_waiver_returns_zero(self, tmp_path: Path) -> None:
        src = _variant(tmp_path, Modality="US")
        rc = main([str(src), str(tmp_path / "out"), "--allow-burned-in", "--quiet"])
        assert rc == 0
