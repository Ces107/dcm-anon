"""Adversarial leak tests for the v0.6.0 deny-by-default model (CF-01/02/11).

These are the acceptance criteria for the structural change from a fixed tag
allowlist to deny-by-default: PHI is planted in the channels the old model was
blind to (vendor private blocks, file_meta AE titles, identifying tags absent
from the table, person-name VRs not enumerated, PHI nested in private SQ) and
the output must come back clean.
"""
from __future__ import annotations

from pathlib import Path

from pydicom import dcmread
from pydicom.dataset import Dataset

from dcm_anon import UIDMapper, anonymize_file
from tests.conftest import _make_synthetic_dcm

# An identifier-bearing Person Name tag deliberately NOT in PHI_TAGS, to prove
# the blanket PN-VR sweep catches names the enumerated table never lists.
_UNKNOWN_PN_TAG = 0x00404037  # Human Performer's Name (PN)


def _plant_adversarial_phi(src: Path) -> Path:
    """Write a DICOM whose PHI lives only in the deny-by-default channels."""
    _make_synthetic_dcm(src, with_sequences=True)
    ds = dcmread(src)

    # File Meta AE title (origin-site fingerprint, HIPAA geographic identifier).
    ds.file_meta.SourceApplicationEntityTitle = "HOSPITAL_PACS_AE"

    # Vendor private blocks (the dominant real-world leak).
    ge = ds.private_block(0x0009, "GEMS_IDEN_01", create=True)
    ge.add_new(0x01, "LO", "PatientSecretGE")
    siemens = ds.private_block(0x0029, "SIEMENS MEDCOM HEADER", create=True)
    siemens.add_new(0x10, "OB", b"SIEMENS_CSA_PHI_BLOB")
    philips = ds.private_block(0x2001, "Philips Imaging DD 001", create=True)
    philips.add_new(0x10, "LO", "PhilipsPrivatePHI")

    # Identifying tags absent from the pre-0.6.0 table.
    ds.add_new(0x00102297, "PN", "Mother^Jane")              # Responsible Person
    ds.add_new(0x00102299, "LO", "Memorial Hospital Trust")  # Responsible Organization
    ds.add_new(0x00321032, "PN", "DR^REQUEST^ER")            # Requesting Physician
    ds.add_new(0x00321066, "LT", "Chest pain, rule out PE")  # Reason for Visit
    ds.add_new(0x00384000, "LT", "Patient John Doe, room 4") # Visit Comments
    ds.add_new(0x01000420, "DT", "20231105120000")           # SOP Authorization DateTime

    # A person-name VR the table does not enumerate (caught only by the sweep).
    ds.add_new(_UNKNOWN_PN_TAG, "PN", "PERFORMER^HUMAN")

    # PHI nested inside a private element within a standard sequence (recursion).
    nested_priv = ds.RequestAttributesSequence[0].private_block(
        0x0011, "ACME LOCAL", create=True
    )
    nested_priv.add_new(0x01, "LO", "NestedPrivatePHI")

    out_src = src.with_name("planted.dcm")
    ds.save_as(out_src, enforce_file_format=True)
    return out_src


def _all_elements(ds: Dataset) -> list:
    """Flatten every data element, recursing into sequence items."""
    elements = []
    for elem in ds:
        elements.append(elem)
        if elem.VR == "SQ" and elem.value:
            for item in elem.value:
                elements.extend(_all_elements(item))
    return elements


class TestDenyByDefault:
    def test_no_private_elements_survive_anywhere(self, tmp_path: Path) -> None:
        src = _plant_adversarial_phi(tmp_path / "base.dcm")
        out = tmp_path / "out.dcm"
        anonymize_file(src, out, UIDMapper(salt="t"))

        result = dcmread(out)
        leaked = [
            f"{e.tag.group:04X},{e.tag.element:04X}"
            for e in _all_elements(result)
            if e.tag.is_private
        ]
        assert leaked == [], f"private elements survived (incl. nested): {leaked}"

    def test_file_meta_ae_title_removed(self, tmp_path: Path) -> None:
        src = _plant_adversarial_phi(tmp_path / "base.dcm")
        out = tmp_path / "out.dcm"
        anonymize_file(src, out, UIDMapper(salt="t"))

        result = dcmread(out)
        assert 0x00020016 not in result.file_meta  # Source Application Entity Title

    def test_newly_covered_identifying_tags_removed(self, tmp_path: Path) -> None:
        src = _plant_adversarial_phi(tmp_path / "base.dcm")
        out = tmp_path / "out.dcm"
        anonymize_file(src, out, UIDMapper(salt="t"))

        result = dcmread(out)
        for tag in (0x00102297, 0x00102299, 0x00321032, 0x00321066, 0x00384000, 0x01000420):
            assert tag not in result, f"identifying tag {tag:08X} survived"

    def test_unknown_person_name_vr_blanked(self, tmp_path: Path) -> None:
        src = _plant_adversarial_phi(tmp_path / "base.dcm")
        out = tmp_path / "out.dcm"
        anonymize_file(src, out, UIDMapper(salt="t"))

        result = dcmread(out)
        # The PN-sweep blanks (keeps the element, empties the value).
        assert str(result[_UNKNOWN_PN_TAG].value) == ""

    def test_keep_private_opt_in_retains_private(self, tmp_path: Path) -> None:
        src = _plant_adversarial_phi(tmp_path / "base.dcm")
        out = tmp_path / "out.dcm"
        anonymize_file(src, out, UIDMapper(salt="t"), keep_private=True)

        result = dcmread(out)
        private = [e for e in _all_elements(result) if e.tag.is_private]
        assert private, "--keep-private must retain private elements when opted in"
