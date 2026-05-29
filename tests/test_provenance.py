"""PS3.15 de-identification provenance attributes (CF-09).

Output must self-identify as de-identified: (0012,0062)=YES, a method text, and
a CID 7050 code sequence containing ONLY the options actually exercised. Stamping
a code for a pass that did not run is false provenance.
"""
from __future__ import annotations

from pathlib import Path

from pydicom import dcmread

from dcm_anon import UIDMapper, anonymize_file
from tests.conftest import _make_synthetic_dcm


def _method_text(ds: object) -> str:
    """DeidentificationMethod is multi-valued LO; flatten to one string."""
    value = ds.DeidentificationMethod  # type: ignore[attr-defined]
    if isinstance(value, str):
        return value
    return " | ".join(str(v) for v in value)


def test_provenance_attributes_written_for_basic_profile(tmp_path: Path) -> None:
    src = tmp_path / "in.dcm"
    _make_synthetic_dcm(src)
    out = tmp_path / "out.dcm"

    anonymize_file(src, out, UIDMapper(salt="t"))

    ds = dcmread(out)
    assert ds.PatientIdentityRemoved == "YES"            # (0012,0062)
    method = _method_text(ds)                            # (0012,0063)
    assert "dcm-anon" in method
    assert "Basic" in method
    # No value may exceed the LO 64-char limit.
    assert all(len(str(v)) <= 64 for v in ds.DeidentificationMethod)

    seq = ds.DeidentificationMethodCodeSequence          # (0012,0064)
    codes = {item.CodeValue for item in seq}
    assert codes == {"113100"}, f"expected only Basic Profile, got {codes}"
    item = seq[0]
    assert item.CodingSchemeDesignator == "DCM"
    assert item.CodeMeaning == "Basic Application Confidentiality Profile"


def test_keep_private_does_not_falsely_claim_basic_profile(tmp_path: Path) -> None:
    src = tmp_path / "in.dcm"
    _make_synthetic_dcm(src)
    out = tmp_path / "out.dcm"

    anonymize_file(src, out, UIDMapper(salt="t"), keep_private=True)

    ds = dcmread(out)
    assert ds.PatientIdentityRemoved == "YES"
    # Private retained => NOT Basic-Profile conformant => 113100 must NOT appear.
    assert "NOT Basic Profile conformant" in _method_text(ds)
    assert "DeidentificationMethodCodeSequence" not in ds or not list(
        ds.get("DeidentificationMethodCodeSequence", [])
    )
