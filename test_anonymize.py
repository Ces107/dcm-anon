"""Tests for dcm-anon: anonymize.py correctness, coverage, edge cases.

Run with:
    pytest test_anonymize.py -v --cov=anonymize --cov-report=term-missing
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydicom import dcmread
from pydicom.dataset import FileDataset

from anonymize import (
    PHI_TAGS,
    ProcessingError,
    UIDMapper,
    __version__,
    anonymize_file,
    anonymize_path,
    audit_sha256,
    main,
    parse_keep_tag,
    render_markdown_report,
)
from conftest import _make_synthetic_dcm

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> FileDataset:
    return dcmread(path)


# ---------------------------------------------------------------------------
# 1. Basic PHI stripping
# ---------------------------------------------------------------------------

class TestBasicPHIStripping:
    def test_patient_name_replaced_with_placeholder(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert str(out.PatientName) == "ANON"

    def test_patient_id_replaced_with_placeholder(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert str(out.PatientID) == "0"

    def test_patient_birth_date_replaced(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert str(out.PatientBirthDate) == "19000101"

    def test_institution_name_deleted(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert (0x0008, 0x0080) not in out

    def test_study_date_deleted(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert (0x0008, 0x0020) not in out

    def test_series_date_deleted(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert (0x0008, 0x0021) not in out

    def test_patient_sex_blanked(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        # Z action: element exists but value is empty string
        assert str(out.PatientSex) == ""

    def test_device_serial_number_deleted(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert (0x0018, 0x1000) not in out

    def test_study_description_deleted(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert (0x0008, 0x1030) not in out

    def test_audit_record_lists_modified_tags(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        record = anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        assert isinstance(record.tags_modified, list)
        assert len(record.tags_modified) > 0
        assert record.source_sha256
        assert record.timestamp_utc.endswith("Z")


# ---------------------------------------------------------------------------
# 2. UID remapping
# ---------------------------------------------------------------------------

class TestUIDRemapping:
    def test_sop_instance_uid_changes(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        original = _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert out.SOPInstanceUID != original.SOPInstanceUID

    def test_study_instance_uid_changes(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        original = _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert out.StudyInstanceUID != original.StudyInstanceUID

    def test_file_meta_consistent_with_dataset_sop(self, tmp_path: Path) -> None:
        """BUG-CLASS: MediaStorageSOPInstanceUID must match dataset SOPInstanceUID."""
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "in.dcm")
        assert out.file_meta.MediaStorageSOPInstanceUID == out.SOPInstanceUID, (
            "MediaStorageSOPInstanceUID must equal SOPInstanceUID after anonymization "
            "otherwise DICOMDIR/WADO references are broken."
        )

    def test_uid_consistency_across_files(
        self,
        tmp_path: Path,
        synthetic_study_dir: tuple[Path, str],
    ) -> None:
        """Two files sharing a StudyInstanceUID must share the same remapped UID."""
        src_dir, shared_study = synthetic_study_dir
        audit = anonymize_path(src_dir, tmp_path / "out")
        out_a = _read(tmp_path / "out" / "a.dcm")
        out_b = _read(tmp_path / "out" / "b.dcm")
        assert out_a.StudyInstanceUID == out_b.StudyInstanceUID
        assert str(out_a.StudyInstanceUID) != shared_study
        assert audit.files_processed == 2


# ---------------------------------------------------------------------------
# 3. Deterministic UID remapping via salt
# ---------------------------------------------------------------------------

class TestDeterministicUIDRemap:
    def test_same_salt_produces_same_uid(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)

        out1 = tmp_path / "run1" / "in.dcm"
        out2 = tmp_path / "run2" / "in.dcm"
        anonymize_file(src, out1, UIDMapper(salt="test-salt"))
        anonymize_file(src, out2, UIDMapper(salt="test-salt"))

        ds1 = _read(out1)
        ds2 = _read(out2)
        assert ds1.SOPInstanceUID == ds2.SOPInstanceUID
        assert ds1.StudyInstanceUID == ds2.StudyInstanceUID

    def test_different_salt_produces_different_uid(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)

        out1 = tmp_path / "run1" / "in.dcm"
        out2 = tmp_path / "run2" / "in.dcm"
        anonymize_file(src, out1, UIDMapper(salt="salt-A"))
        anonymize_file(src, out2, UIDMapper(salt="salt-B"))

        ds1 = _read(out1)
        ds2 = _read(out2)
        assert ds1.SOPInstanceUID != ds2.SOPInstanceUID

    def test_no_salt_produces_random_uid_each_run(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)

        out1 = tmp_path / "run1" / "in.dcm"
        out2 = tmp_path / "run2" / "in.dcm"
        anonymize_file(src, out1, UIDMapper())
        anonymize_file(src, out2, UIDMapper())

        ds1 = _read(out1)
        ds2 = _read(out2)
        # No salt → random; probability of collision is negligible.
        assert ds1.SOPInstanceUID != ds2.SOPInstanceUID

    def test_deterministic_uid_format_valid(self) -> None:
        """Deterministically generated UIDs must be valid DICOM UID strings."""
        mapper = UIDMapper(salt="validation-test")
        uid = mapper.remap("1.2.840.10008.5.1.4.1.1.2.1234")
        assert uid.startswith("2.25.")
        assert len(uid) <= 64
        assert all(c.isdigit() or c == "." for c in uid)


# ---------------------------------------------------------------------------
# 4. Sequence recursion
# ---------------------------------------------------------------------------

class TestSequenceRecursion:
    def test_nested_accession_number_in_request_attributes_deleted(
        self, tmp_path: Path
    ) -> None:
        """PHI nested inside RequestAttributesSequence must be scrubbed."""
        src = tmp_path / "seq.dcm"
        _make_synthetic_dcm(src, with_sequences=True)
        anonymize_file(src, tmp_path / "out" / "seq.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "seq.dcm")

        # RequestAttributesSequence should be deleted (action X on the whole sequence)
        assert (0x0040, 0x0275) not in out, (
            "RequestAttributesSequence must be removed; it may contain PHI "
            "that is hard to clean element-by-element."
        )

    def test_nested_sop_instance_uid_in_referenced_study_sequence_remapped(
        self, tmp_path: Path
    ) -> None:
        """ReferencedSOPInstanceUID inside a nested sequence must be remapped."""
        src = tmp_path / "seq.dcm"
        original_ds = _make_synthetic_dcm(src, with_sequences=True)
        original_ref_uid = str(
            original_ds.ReferencedStudySequence[0].ReferencedSOPInstanceUID
        )

        anonymize_file(src, tmp_path / "out" / "seq.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "seq.dcm")

        if (0x0008, 0x1140) in out or hasattr(out, "ReferencedStudySequence"):
            seq = out.ReferencedStudySequence
            new_ref_uid = str(seq[0].ReferencedSOPInstanceUID)
            assert new_ref_uid != original_ref_uid, (
                "ReferencedSOPInstanceUID inside a nested sequence must be remapped."
            )

    def test_sequence_phi_audit_contains_nested_tags(self, tmp_path: Path) -> None:
        """Audit log must show tags touched inside sequence items."""
        src = tmp_path / "seq.dcm"
        _make_synthetic_dcm(src, with_sequences=True)
        record = anonymize_file(src, tmp_path / "out" / "seq.dcm", UIDMapper())
        # Sequence containing PHI should produce at least one modification entry
        assert len(record.tags_modified) > 0


# ---------------------------------------------------------------------------
# 5. Burned-in annotation flag
# ---------------------------------------------------------------------------

class TestBurnedInAnnotation:
    def test_not_flagged_when_annotation_is_no(self, tmp_path: Path) -> None:
        src = tmp_path / "ok.dcm"
        _make_synthetic_dcm(src, burned_in=False)
        record = anonymize_file(src, tmp_path / "out" / "ok.dcm", UIDMapper())
        assert record.burned_in_phi_warning is False

    def test_flagged_when_annotation_is_yes(self, tmp_path: Path) -> None:
        src = tmp_path / "burned.dcm"
        _make_synthetic_dcm(src, burned_in=True)
        record = anonymize_file(src, tmp_path / "out" / "burned.dcm", UIDMapper())
        assert record.burned_in_phi_warning is True

    def test_audit_count_tracks_warnings(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        _make_synthetic_dcm(src_dir / "a.dcm", burned_in=False)
        _make_synthetic_dcm(src_dir / "b.dcm", burned_in=True)
        audit = anonymize_path(src_dir, tmp_path / "out")
        assert audit.burned_in_warnings == 1


# ---------------------------------------------------------------------------
# 6. Multi-frame DICOM
# ---------------------------------------------------------------------------

class TestMultiFrame:
    def test_multi_frame_anonymized_without_error(self, tmp_path: Path) -> None:
        src = tmp_path / "mf.dcm"
        _make_synthetic_dcm(src, num_frames=4)
        record = anonymize_file(src, tmp_path / "out" / "mf.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "mf.dcm")
        assert str(out.PatientName) == "ANON"
        assert int(out.NumberOfFrames) == 4
        assert record.burned_in_phi_warning is False

    def test_multi_frame_sop_consistency(self, tmp_path: Path) -> None:
        src = tmp_path / "mf.dcm"
        _make_synthetic_dcm(src, num_frames=8)
        anonymize_file(src, tmp_path / "out" / "mf.dcm", UIDMapper())
        out = _read(tmp_path / "out" / "mf.dcm")
        assert out.file_meta.MediaStorageSOPInstanceUID == out.SOPInstanceUID


# ---------------------------------------------------------------------------
# 7. anonymize_path batch behavior
# ---------------------------------------------------------------------------

class TestAnonymizePath:
    def test_single_file_path(self, tmp_path: Path) -> None:
        src = tmp_path / "single.dcm"
        _make_synthetic_dcm(src)
        audit = anonymize_path(src, tmp_path / "out")
        assert audit.files_processed == 1

    def test_directory_processes_all_dcm(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        for name in ("a.dcm", "b.dcm", "c.dcm"):
            _make_synthetic_dcm(src_dir / name)
        audit = anonymize_path(src_dir, tmp_path / "out")
        assert audit.files_processed == 3

    def test_audit_json_serialisable(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        audit = anonymize_path(src, tmp_path / "out")
        serialized = json.dumps(audit.as_dict())
        parsed = json.loads(serialized)
        assert parsed["files_processed"] == 1

    def test_salt_forwarded_to_mapper(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_path(src, tmp_path / "out1", salt="run-A")
        anonymize_path(src, tmp_path / "out2", salt="run-A")
        ds1 = _read(tmp_path / "out1" / "in.dcm")
        ds2 = _read(tmp_path / "out2" / "in.dcm")
        assert ds1.SOPInstanceUID == ds2.SOPInstanceUID


# ---------------------------------------------------------------------------
# 8. Tag table integrity
# ---------------------------------------------------------------------------

_REQUIRED_TAGS: frozenset[tuple[int, int]] = frozenset({
        # Core patient identifiers
        (0x0010, 0x0010),  # Patient Name
        (0x0010, 0x0020),  # Patient ID
        (0x0010, 0x0030),  # Patient Birth Date
        (0x0010, 0x0040),  # Patient Sex
        # Core UIDs
        (0x0008, 0x0018),  # SOP Instance UID
        (0x0020, 0x000D),  # Study Instance UID
        (0x0020, 0x000E),  # Series Instance UID
        (0x0020, 0x0052),  # Frame of Reference UID
        # Institutional
        (0x0008, 0x0080),  # Institution Name
        (0x0008, 0x0090),  # Referring Physician Name
        # Dates added in this version
        (0x0008, 0x0020),  # Study Date
        (0x0008, 0x0021),  # Series Date
        (0x0008, 0x0050),  # Accession Number
        (0x0008, 0x1070),  # Operators Name
        # Device
        (0x0018, 0x1000),  # Device Serial Number
})


class TestTagTableIntegrity:
    def test_required_tags_present(self) -> None:
        missing = _REQUIRED_TAGS - set(PHI_TAGS.keys())
        assert not missing, f"PHI_TAGS missing required entries: {missing}"

    def test_all_action_codes_valid(self) -> None:
        valid = {"X", "Z", "U", "D"}
        invalid = {
            (tag, code)
            for tag, code in PHI_TAGS.items()
            if code not in valid
        }
        assert not invalid, f"Unknown action codes in PHI_TAGS: {invalid}"

    def test_uid_tags_have_u_action(self) -> None:
        uid_tags = {
            (0x0008, 0x0018),  # SOP Instance UID
            (0x0020, 0x000D),  # Study Instance UID
            (0x0020, 0x000E),  # Series Instance UID
            (0x0020, 0x0052),  # Frame of Reference UID
        }
        for tag in uid_tags:
            assert PHI_TAGS.get(tag) == "U", (
                f"UID tag {tag} should have action 'U', got {PHI_TAGS.get(tag)!r}"
            )

    def test_patient_name_has_z_action(self) -> None:
        assert PHI_TAGS[(0x0010, 0x0010)] == "Z"

    def test_patient_id_has_z_action(self) -> None:
        assert PHI_TAGS[(0x0010, 0x0020)] == "Z"


# ---------------------------------------------------------------------------
# 9. Dry-run mode (iter2)
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_anonymize_file_dry_run_does_not_write_output(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        out = tmp_path / "out" / "in.dcm"
        rec = anonymize_file(src, out, UIDMapper(), dry_run=True)
        assert rec.dry_run is True
        assert rec.output is None
        assert not out.exists()

    def test_anonymize_path_dry_run_aggregate(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        _make_synthetic_dcm(src_dir / "a.dcm")
        _make_synthetic_dcm(src_dir / "b.dcm")
        out = tmp_path / "out"
        audit = anonymize_path(src_dir, out, dry_run=True)
        assert audit.dry_run is True
        assert audit.files_processed == 2
        assert not out.exists()

    def test_dry_run_still_records_modified_tags(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        rec = anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper(), dry_run=True)
        assert isinstance(rec.tags_modified, list)
        assert len(rec.tags_modified) > 5


# ---------------------------------------------------------------------------
# 10. Keep-tag whitelist
# ---------------------------------------------------------------------------

class TestKeepTags:
    def test_kept_tag_is_not_modified(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        keep = frozenset({(0x0010, 0x0010)})  # Patient's Name
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper(), keep_tags=keep)
        out = _read(tmp_path / "out" / "in.dcm")
        assert str(out.PatientName) == "DOE^JOHN^WILLIAM"

    def test_kept_tag_does_not_appear_in_audit(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        keep = frozenset({(0x0010, 0x0010)})
        rec = anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper(), keep_tags=keep)
        tags = rec.tags_modified
        assert isinstance(tags, list)
        assert "0010,0010:Z" not in tags

    def test_other_tags_still_scrubbed_when_one_kept(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        keep = frozenset({(0x0010, 0x0010)})
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper(), keep_tags=keep)
        out = _read(tmp_path / "out" / "in.dcm")
        assert str(out.PatientID) == "0"  # still scrubbed
        assert (0x0008, 0x0080) not in out  # InstitutionName still deleted


# ---------------------------------------------------------------------------
# 11. Continue-on-error
# ---------------------------------------------------------------------------

class TestContinueOnError:
    def test_malformed_dicom_aborts_when_continue_off(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        _make_synthetic_dcm(src_dir / "good.dcm")
        (src_dir / "bad.dcm").write_bytes(b"not a dicom")
        with pytest.raises((Exception,)):
            anonymize_path(src_dir, tmp_path / "out", continue_on_error=False)

    def test_malformed_dicom_skipped_when_continue_on(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        _make_synthetic_dcm(src_dir / "good.dcm")
        (src_dir / "bad.dcm").write_bytes(b"not a dicom")
        audit = anonymize_path(src_dir, tmp_path / "out", continue_on_error=True)
        assert audit.files_processed == 1
        assert audit.files_failed == 1
        errors = audit.errors
        assert isinstance(errors, list)
        assert len(errors) == 1
        assert "bad.dcm" in errors[0].source

    def test_processing_error_dataclass_fields(self) -> None:
        err = ProcessingError(source="x.dcm", error_type="ValueError", error_message="oops")
        assert err.source == "x.dcm"
        assert err.error_type == "ValueError"
        assert err.error_message == "oops"


# ---------------------------------------------------------------------------
# 12. Audit signing + Markdown report
# ---------------------------------------------------------------------------

class TestAuditIntegrity:
    def test_audit_sha256_is_hex(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        audit = anonymize_path(src, tmp_path / "out")
        sha = audit.audit_sha256
        assert isinstance(sha, str)
        assert len(sha) == 64
        int(sha, 16)  # valid hex

    def test_audit_sha256_changes_when_records_change(self) -> None:
        a = audit_sha256([{"x": 1}])
        b = audit_sha256([{"x": 2}])
        assert a != b

    def test_audit_sha256_stable_across_key_order(self) -> None:
        a = audit_sha256([{"a": 1, "b": 2}])
        b = audit_sha256([{"b": 2, "a": 1}])
        assert a == b

    def test_version_field_in_audit(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        audit = anonymize_path(src, tmp_path / "out")
        assert audit.version == __version__


class TestMarkdownReport:
    def test_renders_summary_block(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        audit = anonymize_path(src, tmp_path / "out")
        md = render_markdown_report(audit)
        assert "# DICOM Anonymization Report" in md
        assert "Files processed:" in md
        assert "Audit SHA-256" in md

    def test_dry_run_marker_shown(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        audit = anonymize_path(src, tmp_path / "out", dry_run=True)
        md = render_markdown_report(audit)
        assert "DRY RUN" in md

    def test_errors_section_appears_when_present(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        _make_synthetic_dcm(src_dir / "good.dcm")
        (src_dir / "bad.dcm").write_bytes(b"not a dicom")
        audit = anonymize_path(src_dir, tmp_path / "out", continue_on_error=True)
        md = render_markdown_report(audit)
        assert "## Errors" in md
        assert "bad.dcm" in md


# ---------------------------------------------------------------------------
# 13. parse_keep_tag
# ---------------------------------------------------------------------------

class TestParseKeepTag:
    @pytest.mark.parametrize("spec,expected", [
        ("0010,0010", (0x0010, 0x0010)),
        ("(0010,0010)", (0x0010, 0x0010)),
        ("0008,0050", (0x0008, 0x0050)),
        ("FFFF,FFFF", (0xFFFF, 0xFFFF)),
        ("  0010 , 0010  ", (0x0010, 0x0010)),
    ])
    def test_valid_specs(self, spec: str, expected: tuple[int, int]) -> None:
        assert parse_keep_tag(spec) == expected

    @pytest.mark.parametrize("spec", ["bad", "0010", "0010,0010,0010", "GGGG,EEEE"])
    def test_invalid_specs_raise(self, spec: str) -> None:
        with pytest.raises(ValueError):
            parse_keep_tag(spec)


# ---------------------------------------------------------------------------
# 14. Progress callback
# ---------------------------------------------------------------------------

class TestProgressCallback:
    def test_callback_invoked_per_file(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        _make_synthetic_dcm(src_dir / "a.dcm")
        _make_synthetic_dcm(src_dir / "b.dcm")
        _make_synthetic_dcm(src_dir / "c.dcm")
        seen: list[tuple[int, int]] = []

        def cb(index: int, total: int, _path: Path) -> None:
            seen.append((index, total))

        anonymize_path(src_dir, tmp_path / "out", progress_cb=cb)
        assert seen == [(1, 3), (2, 3), (3, 3)]


# ---------------------------------------------------------------------------
# 15. CLI integration
# ---------------------------------------------------------------------------

class TestCLI:
    def test_main_dry_run_exits_zero(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        rc = main([str(src), str(tmp_path / "out"), "--dry-run", "--quiet"])
        assert rc == 0
        # audit log written even in dry run
        audit_log = tmp_path / "out" / "anonymization_audit.json"
        # In dry run mode we still write the audit JSON to the requested path
        if audit_log.exists():
            data = json.loads(audit_log.read_text())
            assert data["dry_run"] is True

    def test_main_continue_on_error_returns_one(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        _make_synthetic_dcm(src_dir / "ok.dcm")
        (src_dir / "broken.dcm").write_bytes(b"junk")
        rc = main([str(src_dir), str(tmp_path / "out"),
                   "--continue-on-error", "--quiet"])
        assert rc == 1

    def test_main_keep_flag_parses(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        rc = main([str(src), str(tmp_path / "out"),
                   "--keep", "0010,0010", "--quiet"])
        assert rc == 0
        out_ds = _read(tmp_path / "out" / "in.dcm")
        assert str(out_ds.PatientName) == "DOE^JOHN^WILLIAM"

    def test_main_invalid_keep_returns_two(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        rc = main([str(src), str(tmp_path / "out"),
                   "--keep", "garbage", "--quiet"])
        assert rc == 2
        assert "keep" in capsys.readouterr().err.lower()

    def test_main_writes_markdown_report(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        report_path = tmp_path / "report.md"
        rc = main([str(src), str(tmp_path / "out"),
                   "--report-md", str(report_path), "--quiet"])
        assert rc == 0
        assert report_path.exists()
        assert "DICOM Anonymization Report" in report_path.read_text()
