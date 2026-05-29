"""Public test/demo kit: build synthetic DICOM packed with PHI in every channel
dcm-anon must handle, so a prospect, a DPO, or CI can run a reproducible
completeness proof against their own copy.

NO real patient data — every value is invented. Use it to build a golden study
(see ``examples/verify_golden.py``) or to seed your own conformance corpus.
"""
from __future__ import annotations

from pathlib import Path

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import UID, ExplicitVRLittleEndian, generate_uid

# Basic Text SR SOP class — carries a content tree of free text the flat table
# cannot reach. Chest CT body part keeps the face/burned-in gates from firing so
# the study can demonstrate a FULLY clean pass.
_BASIC_TEXT_SR = "1.2.840.10008.5.1.4.1.1.88.11"


def build_adversarial_study(
    dest_dir: Path,
    *,
    filename: str = "adversarial_phi.dcm",
) -> Path:
    """Write a synthetic DICOM with PHI planted in every channel: standard tags,
    vendor private blocks, identifiers the legacy table missed, nested-sequence
    PHI, and an SR content tree (free text + person name + UID ref). Returns the
    path. Deterministic UIDs are NOT used here (random) so each call is unique.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / filename
    sop_uid = generate_uid()

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = UID(_BASIC_TEXT_SR)
    meta.MediaStorageSOPInstanceUID = UID(sop_uid)
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.SourceApplicationEntityTitle = "HOSPITAL_PACS_AE"  # origin fingerprint

    ds = FileDataset(str(path), Dataset(), file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = _BASIC_TEXT_SR
    ds.SOPInstanceUID = sop_uid
    ds.Modality = "SR"

    # Standard patient + study PHI.
    ds.PatientName = "DOE^JOHN^WILLIAM"
    ds.PatientID = "MRN-12345"
    ds.PatientBirthDate = "19800615"
    ds.PatientSex = "M"
    ds.PatientAddress = "12 Main St, Valencia"
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.StudyDate = "20231105"
    ds.AccessionNumber = "ACC-98765"
    ds.StudyDescription = "Chest CT report"
    ds.InstitutionName = "Hospital Universitari La Fe"
    ds.ReferringPhysicianName = "DR^HOUSE^GREGORY"

    # Identifiers the pre-0.6.0 table missed.
    ds.add_new(0x00102297, "PN", "Mother^Jane")             # Responsible Person
    ds.add_new(0x00321066, "LT", "Chest pain, rule out PE")  # Reason for Visit
    ds.add_new(0x01000420, "DT", "20231105120000")          # SOP Authorization DateTime

    # Vendor private blocks.
    ge = ds.private_block(0x0009, "GEMS_IDEN_01", create=True)
    ge.add_new(0x01, "LO", "PatientSecretGE")
    siemens = ds.private_block(0x0029, "SIEMENS MEDCOM HEADER", create=True)
    siemens.add_new(0x10, "OB", b"SIEMENS_CSA_PHI_BLOB")

    # Nested-sequence PHI.
    req_item = Dataset()
    req_item.AccessionNumber = "REF-ACC-11111"
    req_item.ReferencedSOPInstanceUID = generate_uid()
    nested_priv = req_item.private_block(0x0011, "ACME LOCAL", create=True)
    nested_priv.add_new(0x01, "LO", "NestedPrivatePHI")
    ds.RequestAttributesSequence = Sequence([req_item])

    # SR content tree: free text with SSN/email, a person name, a UID reference.
    text_item = Dataset()
    text_item.ValueType = "TEXT"
    text_item.TextValue = "Patient John Doe, SSN 123-45-6789, email john@example.com"
    pname_item = Dataset()
    pname_item.ValueType = "PNAME"
    pname_item.PersonName = "OBSERVER^CLINICIAN"
    uidref_item = Dataset()
    uidref_item.ValueType = "UIDREF"
    uidref_item.UID = generate_uid()
    ds.ContentSequence = Sequence([text_item, pname_item, uidref_item])

    # Not burned-in, not a head scan — so the only gate is the SR one, cleared by
    # --scrub-sr; the study is meant to come back FULLY clean.
    ds.BurnedInAnnotation = "NO"

    ds.save_as(path, enforce_file_format=True)
    return path
