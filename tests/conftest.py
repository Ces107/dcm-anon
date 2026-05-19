"""Shared pytest fixtures for dcm-anon tests."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import UID, ExplicitVRLittleEndian, generate_uid


def _make_synthetic_dcm(
    path: Path,
    *,
    burned_in: bool = False,
    with_sequences: bool = False,
    study_uid: str | None = None,
    series_uid: str | None = None,
    num_frames: int = 1,
) -> Dataset:
    """Synthetic DICOM for tests; burned_in=True sets BurnedInAnnotation=YES."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sop_uid = generate_uid()
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.2")  # CT Image Storage
    meta.MediaStorageSOPInstanceUID = UID(sop_uid)
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(str(path), Dataset(), file_meta=meta, preamble=b"\0" * 128)

    # SOP identifiers
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.SOPInstanceUID = sop_uid

    # Patient PHI
    ds.PatientName = "DOE^JOHN^WILLIAM"
    ds.PatientID = "MRN-12345"
    ds.PatientBirthDate = "19800615"
    ds.PatientSex = "M"
    ds.PatientAge = "043Y"
    ds.PatientComments = "Referred by GP"

    # Study / series PHI
    ds.StudyInstanceUID = study_uid or generate_uid()
    ds.SeriesInstanceUID = series_uid or generate_uid()
    ds.StudyDate = "20231105"
    ds.SeriesDate = "20231105"
    ds.AcquisitionDate = "20231105"
    ds.ContentDate = "20231105"
    ds.StudyTime = "120000.000000"
    ds.SeriesTime = "120100.000000"
    ds.ContentTime = "120200.000000"
    ds.StudyID = "STUDY-001"
    ds.AccessionNumber = "ACC-98765"
    ds.StudyDescription = "Chest CT with contrast"
    ds.SeriesDescription = "Axial 5mm slice"

    # Institution PHI
    ds.InstitutionName = "Hospital Universitari i Politecnic La Fe"
    ds.InstitutionAddress = "Av. Fernando Abril Martorell 106, Valencia"
    ds.InstitutionalDepartmentName = "Radiology"
    ds.ReferringPhysicianName = "DR^HOUSE^GREGORY"
    ds.PerformingPhysicianName = "DR^SMITH^JANE"
    ds.OperatorsName = "TECH^OPERATOR"

    # Device PHI
    ds.DeviceSerialNumber = "SN-20230101-0042"
    ds.StationName = "CT-SCANNER-01"

    # Modality + image geometry (non-PHI but needed for valid CT)
    ds.Modality = "CT"
    ds.FrameOfReferenceUID = generate_uid()
    ds.InstanceNumber = "1"
    ds.SliceLocation = "0.0"
    ds.NumberOfFrames = str(num_frames)

    # Pixel data placeholder
    ds.Rows = 4
    ds.Columns = 4
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 12
    ds.HighBit = 11
    ds.PixelRepresentation = 0
    ds.PixelData = b"\x00\x00" * (4 * 4 * num_frames)

    # Burned-in annotation flag
    ds.BurnedInAnnotation = "YES" if burned_in else "NO"

    if with_sequences:
        # RequestAttributesSequence — common sequence containing PHI
        req_item = Dataset()
        req_item.RequestedProcedureDescription = "Chest X-Ray follow-up"
        req_item.ScheduledProcedureStepDescription = "Axial CT"
        req_item.AccessionNumber = "REF-ACC-11111"  # nested PHI: Accession Number
        req_item.ReferencedSOPInstanceUID = generate_uid()  # nested UID
        ds.RequestAttributesSequence = Sequence([req_item])

        # ReferencedStudySequence — another common sequence with PHI
        ref_study_item = Dataset()
        ref_study_item.ReferencedSOPClassUID = "1.2.840.10008.3.1.2.3.1"
        ref_study_item.ReferencedSOPInstanceUID = generate_uid()  # nested UID PHI
        ds.ReferencedStudySequence = Sequence([ref_study_item])

    ds.save_as(path, enforce_file_format=True)
    return ds


@pytest.fixture
def synthetic_dcm(tmp_path: Path) -> Dataset:
    return _make_synthetic_dcm(tmp_path / "test.dcm")


@pytest.fixture
def synthetic_dcm_with_sequences(tmp_path: Path) -> Dataset:
    return _make_synthetic_dcm(tmp_path / "seq.dcm", with_sequences=True)


@pytest.fixture
def synthetic_dcm_burned_in(tmp_path: Path) -> Dataset:
    return _make_synthetic_dcm(tmp_path / "burned.dcm", burned_in=True)


@pytest.fixture
def synthetic_study_dir(tmp_path: Path) -> tuple[Path, str]:
    """Two DICOMs sharing the same StudyInstanceUID."""
    shared_study = generate_uid()
    src = tmp_path / "in"
    src.mkdir()
    _make_synthetic_dcm(src / "a.dcm", study_uid=shared_study)
    _make_synthetic_dcm(src / "b.dcm", study_uid=shared_study)
    return src, shared_study
