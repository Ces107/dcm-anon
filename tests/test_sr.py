"""Tests for dcm_anon.sr — the SR content-tree PHI scrubber.

Builds synthetic in-memory DICOM SR datasets with pydicom (no real patient
data, no file I/O). Verifies the public contract: TextValue PHI redaction,
the conservative profile, UIDREF remap through the SHARED UIDMapper, PNAME
blanking, date/time blanking, and SR detection.
"""
from __future__ import annotations

import re

import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import UID, ExplicitVRLittleEndian, generate_uid

from dcm_anon.sr import (
    SR_TEXT_VALUE_TAG,
    SR_UID_VALUE_TAG,
    SrConfig,
    detect_phi_spans,
    has_sr_content,
    scrub_sr_content,
)
from dcm_anon.uid_mapper import UIDMapper

# Tag aliases for assertions.
_TEXT_TAG = (0x0040, 0xA160)
_PNAME_TAG = (0x0040, 0xA123)
_DATE_TAG = (0x0040, 0xA121)
_TIME_TAG = (0x0040, 0xA122)
_DATETIME_TAG = (0x0040, 0xA120)


# ---------------------------------------------------------------------------
# Synthetic SR builders
# ---------------------------------------------------------------------------


def _content_item(value_type: str) -> Dataset:
    item = Dataset()
    item.ValueType = value_type
    item.RelationshipType = "CONTAINS"
    concept = Dataset()
    concept.CodeValue = "121070"
    concept.CodingSchemeDesignator = "DCM"
    concept.CodeMeaning = f"Test {value_type}"
    item.ConceptNameCodeSequence = Sequence([concept])
    return item


def _text_item(text: str) -> Dataset:
    item = _content_item("TEXT")
    item.TextValue = text
    return item


def _pname_item(name: str) -> Dataset:
    item = _content_item("PNAME")
    item.PersonName = pydicom.valuerep.PersonName(name)
    return item


def _date_item(date: str) -> Dataset:
    item = _content_item("DATE")
    item.Date = date
    return item


def _time_item(time: str) -> Dataset:
    item = _content_item("TIME")
    item.Time = time
    return item


def _datetime_item(dt: str) -> Dataset:
    item = _content_item("DATETIME")
    item.DateTime = dt
    return item


def _uidref_item(uid: str) -> Dataset:
    item = _content_item("UIDREF")
    item.UID = uid
    return item


def _code_item() -> Dataset:
    item = _content_item("CODE")
    code = Dataset()
    code.CodeValue = "T-D0050"
    code.CodingSchemeDesignator = "SRT"
    code.CodeMeaning = "Liver"
    item.ConceptCodeSequence = Sequence([code])
    return item


def _container_item(children: list[Dataset]) -> Dataset:
    item = _content_item("CONTAINER")
    item.ContinuityOfContent = "SEPARATE"
    item.ContentSequence = Sequence(children)
    return item


def build_sr(uidref_uid: str | None = None) -> pydicom.FileDataset:
    """A Basic Text SR with PHI in TEXT, a PNAME, DATE, TIME, DATETIME, UIDREF,
    a CODE node, and a nested container with an email in its TextValue."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.88.11")  # Basic Text SR
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = pydicom.FileDataset("synthetic_sr.dcm", {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.88.11"
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "SR"
    ds.ValueType = "CONTAINER"
    ds.ContinuityOfContent = "SEPARATE"

    children: list[Dataset] = [
        _text_item("Patient John Doe (SSN: 123-45-6789) was seen on 01/23/1985."),
        _text_item("No abnormalities detected in the study region."),
        _pname_item("Radiologist^James^^^"),
        _date_item("20240101"),
        _time_item("143000.000000"),
        _datetime_item("20240101143000"),
        _code_item(),
        _container_item([_text_item("Patient email: test@example.com")]),
    ]
    if uidref_uid is not None:
        children.append(_uidref_item(uidref_uid))

    ds.ContentSequence = Sequence(children)
    return ds


def build_plain_image() -> Dataset:
    """A plain CT image dataset with NO SR content tree."""
    ds = Dataset()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.Modality = "CT"
    ds.PatientName = "DOE^JOHN"
    ds.Rows = 4
    ds.Columns = 4
    return ds


def _all_text_values(ds: Dataset) -> list[str]:
    values: list[str] = []
    for elem in ds.iterall():
        if elem.tag.group == 0x0040 and elem.tag.element == 0xA160:
            values.append(str(elem.value))
    return values


def _all_pname_values(ds: Dataset) -> list[str]:
    values: list[str] = []
    for elem in ds.iterall():
        if elem.tag.group == 0x0040 and elem.tag.element == 0xA123:
            values.append(str(elem.value))
    return values


# ---------------------------------------------------------------------------
# has_sr_content
# ---------------------------------------------------------------------------


class TestHasSrContent:
    def test_true_for_sr(self) -> None:
        assert has_sr_content(build_sr()) is True

    def test_false_for_plain_image(self) -> None:
        assert has_sr_content(build_plain_image()) is False

    def test_false_for_empty_content_sequence(self) -> None:
        ds = Dataset()
        ds.ContentSequence = Sequence([])
        assert has_sr_content(ds) is False


# ---------------------------------------------------------------------------
# Default profile: regex PHI redaction
# ---------------------------------------------------------------------------


class TestDefaultProfile:
    def test_ssn_redacted(self) -> None:
        ds = build_sr()
        scrub_sr_content(ds, UIDMapper())
        for value in _all_text_values(ds):
            assert re.search(r"\d{3}-\d{2}-\d{4}", value) is None, f"SSN survived: {value!r}"

    def test_email_in_nested_container_redacted(self) -> None:
        ds = build_sr()
        scrub_sr_content(ds, UIDMapper())
        for value in _all_text_values(ds):
            assert "test@example.com" not in value, f"email survived: {value!r}"

    def test_clean_text_preserved(self) -> None:
        ds = build_sr()
        scrub_sr_content(ds, UIDMapper())
        assert any("No abnormalities detected" in v for v in _all_text_values(ds))

    def test_redact_marker_present(self) -> None:
        ds = build_sr()
        scrub_sr_content(ds, UIDMapper())
        assert any("[REDACTED:" in v for v in _all_text_values(ds))

    def test_audit_entries_use_touch_format(self) -> None:
        ds = build_sr()
        touched = scrub_sr_content(ds, UIDMapper())
        assert touched, "expected at least one audit entry"
        for entry in touched:
            assert re.fullmatch(r"[0-9A-F]{4},[0-9A-F]{4}:[A-Z_]+", entry), entry

    def test_audit_contains_redact_text(self) -> None:
        ds = build_sr()
        touched = scrub_sr_content(ds, UIDMapper())
        assert "0040,A160:REDACT_TEXT" in touched


# ---------------------------------------------------------------------------
# Conservative profile: blank all text
# ---------------------------------------------------------------------------


class TestConservativeProfile:
    def test_all_text_blanked(self) -> None:
        ds = build_sr()
        scrub_sr_content(ds, UIDMapper(), SrConfig(profile="conservative"))
        for value in _all_text_values(ds):
            assert value == "", f"conservative profile left text: {value!r}"

    def test_audit_uses_blank_text_action(self) -> None:
        ds = build_sr()
        touched = scrub_sr_content(ds, UIDMapper(), SrConfig(profile="conservative"))
        assert "0040,A160:BLANK_TEXT" in touched
        assert "0040,A160:REDACT_TEXT" not in touched


# ---------------------------------------------------------------------------
# UIDREF remap via the SHARED mapper
# ---------------------------------------------------------------------------


class TestUidrefRemap:
    def test_uidref_remapped_via_same_mapper_as_top_level(self) -> None:
        """A UIDREF inside the SR must map, through the SAME mapper, to the SAME
        value the top-level pipeline would produce for that source UID."""
        source_uid = generate_uid()
        mapper = UIDMapper(salt="cohort-x")

        # Top-level remap (what pipeline does for e.g. SeriesInstanceUID).
        top_level = mapper.remap(str(source_uid))

        ds = build_sr(uidref_uid=str(source_uid))
        scrub_sr_content(ds, mapper, SrConfig())

        sr_uid_values = [
            str(elem.value)
            for elem in ds.iterall()
            if elem.tag.group == 0x0040 and elem.tag.element == 0xA124
        ]
        assert sr_uid_values, "no UIDREF found after scrub"
        assert sr_uid_values[0] == top_level
        assert sr_uid_values[0] != str(source_uid)

    def test_uidref_audit_entry(self) -> None:
        ds = build_sr(uidref_uid=str(generate_uid()))
        touched = scrub_sr_content(ds, UIDMapper(salt="s"))
        assert "0040,A124:REMAP_UIDREF" in touched


# ---------------------------------------------------------------------------
# PNAME / DATE / TIME / DATETIME blanking
# ---------------------------------------------------------------------------


class TestPnameAndTemporal:
    def test_pname_blanked(self) -> None:
        ds = build_sr()
        scrub_sr_content(ds, UIDMapper())
        for value in _all_pname_values(ds):
            assert value == "", f"PNAME survived: {value!r}"

    def test_pname_audit_entry(self) -> None:
        ds = build_sr()
        touched = scrub_sr_content(ds, UIDMapper())
        assert "0040,A123:BLANK_PNAME" in touched

    def test_date_blanked(self) -> None:
        ds = build_sr()
        scrub_sr_content(ds, UIDMapper())
        for elem in ds.iterall():
            if elem.tag.group == 0x0040 and elem.tag.element == 0xA121:
                assert str(elem.value) == ""

    def test_time_blanked(self) -> None:
        ds = build_sr()
        scrub_sr_content(ds, UIDMapper())
        for elem in ds.iterall():
            if elem.tag.group == 0x0040 and elem.tag.element == 0xA122:
                assert str(elem.value) == ""

    def test_datetime_blanked(self) -> None:
        ds = build_sr()
        scrub_sr_content(ds, UIDMapper())
        for elem in ds.iterall():
            if elem.tag.group == 0x0040 and elem.tag.element == 0xA120:
                assert str(elem.value) == ""

    def test_date_time_datetime_audit_entries(self) -> None:
        ds = build_sr()
        touched = scrub_sr_content(ds, UIDMapper())
        assert "0040,A121:BLANK_DATE" in touched
        assert "0040,A122:BLANK_TIME" in touched
        assert "0040,A120:BLANK_DATETIME" in touched


# ---------------------------------------------------------------------------
# Header tags are NOT this module's concern
# ---------------------------------------------------------------------------


class TestHeaderUntouched:
    def test_patient_name_header_not_touched(self) -> None:
        ds = build_sr()
        ds.PatientName = pydicom.valuerep.PersonName("DOE^JOHN")
        scrub_sr_content(ds, UIDMapper())
        assert str(ds.PatientName) == "DOE^JOHN", "module must not touch header PatientName"


# ---------------------------------------------------------------------------
# Config validation + detection helper
# ---------------------------------------------------------------------------


class TestConfigAndDetection:
    def test_unknown_profile_raises(self) -> None:
        ds = build_sr()
        try:
            scrub_sr_content(ds, UIDMapper(), SrConfig(profile="bogus"))
        except ValueError as exc:
            assert "bogus" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected ValueError for unknown profile")

    def test_extra_blacklist_redacts_token(self) -> None:
        ds = Dataset()
        item = _text_item("Reported by Mengele today.")
        ds.ContentSequence = Sequence([item])
        cfg = SrConfig(extra_blacklist=frozenset({"Mengele"}))
        scrub_sr_content(ds, UIDMapper(), cfg)
        assert "Mengele" not in str(ds.ContentSequence[0].TextValue)

    def test_detect_phi_spans_finds_ssn_and_email(self) -> None:
        spans = detect_phi_spans("SSN 123-45-6789 mail a@b.com")
        labels = {s.label for s in spans}
        assert "SSN" in labels
        assert "EMAIL" in labels

    def test_no_phi_returns_empty_touch(self) -> None:
        ds = Dataset()
        ds.ContentSequence = Sequence([_text_item("perfectly clean prose")])
        touched = scrub_sr_content(ds, UIDMapper())
        assert touched == []

    def test_module_tag_constants(self) -> None:
        assert SR_TEXT_VALUE_TAG == _TEXT_TAG
        assert SR_UID_VALUE_TAG == (0x0040, 0xA124)
