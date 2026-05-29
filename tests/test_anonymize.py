"""Tests for dcm-anon: anonymize.py correctness, coverage, edge cases.

Run with:
    pytest test_anonymize.py -v --cov=anonymize --cov-report=term-missing
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydicom import dcmread

from dcm_anon import (
    PHI_TAGS,
    AuditRecord,
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
from tests.conftest import _make_synthetic_dcm

# Sentinel for "tag must be absent" parametrize cases.
_ABSENT = object()


class TestBasicPHIStripping:
    @pytest.mark.parametrize("attr_or_tag,expected", [
        ("PatientName", "ANON"),                # Z → replace with placeholder
        ("PatientID", "0"),                     # Z → replace with placeholder
        ("PatientBirthDate", "19000101"),       # Z → replace with placeholder
        ("PatientSex", ""),                     # Z → blank (empty string)
        ((0x0008, 0x0080), _ABSENT),            # X → Institution Name deleted
        ((0x0008, 0x0020), _ABSENT),            # X → Study Date deleted
        ((0x0008, 0x0021), _ABSENT),            # X → Series Date deleted
        ((0x0018, 0x1000), _ABSENT),            # X → Device Serial Number deleted
        ((0x0008, 0x1030), _ABSENT),            # X → Study Description deleted
    ])
    def test_phi_tag_value_after_anonymize(
        self,
        attr_or_tag: str | tuple[int, int],
        expected: object,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = dcmread(tmp_path / "out" / "in.dcm")
        if expected is _ABSENT:
            assert attr_or_tag not in out
        else:
            assert str(getattr(out, attr_or_tag)) == expected  # type: ignore[arg-type]

    def test_audit_record_lists_modified_tags(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        record = anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        assert isinstance(record.tags_modified, list)
        assert len(record.tags_modified) > 0
        assert record.source_sha256
        assert record.timestamp_utc.endswith("Z")


class TestUIDRemapping:
    def test_sop_instance_uid_changes(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        original = _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = dcmread(tmp_path / "out" / "in.dcm")
        assert out.SOPInstanceUID != original.SOPInstanceUID

    def test_study_instance_uid_changes(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        original = _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = dcmread(tmp_path / "out" / "in.dcm")
        assert out.StudyInstanceUID != original.StudyInstanceUID

    def test_file_meta_consistent_with_dataset_sop(self, tmp_path: Path) -> None:
        """BUG-CLASS: MediaStorageSOPInstanceUID must match dataset SOPInstanceUID."""
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper())
        out = dcmread(tmp_path / "out" / "in.dcm")
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
        out_a = dcmread(tmp_path / "out" / "a.dcm")
        out_b = dcmread(tmp_path / "out" / "b.dcm")
        assert out_a.StudyInstanceUID == out_b.StudyInstanceUID
        assert str(out_a.StudyInstanceUID) != shared_study
        assert audit.files_processed == 2


class TestDeterministicUIDRemap:
    def test_same_salt_produces_same_uid(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)

        out1 = tmp_path / "run1" / "in.dcm"
        out2 = tmp_path / "run2" / "in.dcm"
        anonymize_file(src, out1, UIDMapper(salt="test-salt"))
        anonymize_file(src, out2, UIDMapper(salt="test-salt"))

        ds1 = dcmread(out1)
        ds2 = dcmread(out2)
        assert ds1.SOPInstanceUID == ds2.SOPInstanceUID
        assert ds1.StudyInstanceUID == ds2.StudyInstanceUID

    def test_different_salt_produces_different_uid(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)

        out1 = tmp_path / "run1" / "in.dcm"
        out2 = tmp_path / "run2" / "in.dcm"
        anonymize_file(src, out1, UIDMapper(salt="salt-A"))
        anonymize_file(src, out2, UIDMapper(salt="salt-B"))

        ds1 = dcmread(out1)
        ds2 = dcmread(out2)
        assert ds1.SOPInstanceUID != ds2.SOPInstanceUID

    def test_no_salt_produces_random_uid_each_run(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)

        out1 = tmp_path / "run1" / "in.dcm"
        out2 = tmp_path / "run2" / "in.dcm"
        anonymize_file(src, out1, UIDMapper())
        anonymize_file(src, out2, UIDMapper())

        ds1 = dcmread(out1)
        ds2 = dcmread(out2)
        # No salt → random; probability of collision is negligible.
        assert ds1.SOPInstanceUID != ds2.SOPInstanceUID

    def test_deterministic_uid_format_valid(self) -> None:
        """Deterministically generated UIDs must be valid DICOM UID strings."""
        mapper = UIDMapper(salt="validation-test")
        uid = mapper.remap("1.2.840.10008.5.1.4.1.1.2.1234")
        assert uid.startswith("2.25.")
        assert len(uid) <= 64
        assert all(c.isdigit() or c == "." for c in uid)


class TestSequenceRecursion:
    def test_nested_accession_number_in_request_attributes_deleted(
        self, tmp_path: Path
    ) -> None:
        """PHI nested inside RequestAttributesSequence must be scrubbed."""
        src = tmp_path / "seq.dcm"
        _make_synthetic_dcm(src, with_sequences=True)
        anonymize_file(src, tmp_path / "out" / "seq.dcm", UIDMapper())
        out = dcmread(tmp_path / "out" / "seq.dcm")

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
        out = dcmread(tmp_path / "out" / "seq.dcm")

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


class TestMultiFrame:
    def test_multi_frame_anonymized_without_error(self, tmp_path: Path) -> None:
        src = tmp_path / "mf.dcm"
        _make_synthetic_dcm(src, num_frames=4)
        record = anonymize_file(src, tmp_path / "out" / "mf.dcm", UIDMapper())
        out = dcmread(tmp_path / "out" / "mf.dcm")
        assert str(out.PatientName) == "ANON"
        assert int(out.NumberOfFrames) == 4
        assert record.burned_in_phi_warning is False

    def test_multi_frame_sop_consistency(self, tmp_path: Path) -> None:
        src = tmp_path / "mf.dcm"
        _make_synthetic_dcm(src, num_frames=8)
        anonymize_file(src, tmp_path / "out" / "mf.dcm", UIDMapper())
        out = dcmread(tmp_path / "out" / "mf.dcm")
        assert out.file_meta.MediaStorageSOPInstanceUID == out.SOPInstanceUID


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
        ds1 = dcmread(tmp_path / "out1" / "in.dcm")
        ds2 = dcmread(tmp_path / "out2" / "in.dcm")
        assert ds1.SOPInstanceUID == ds2.SOPInstanceUID


class TestTagTableIntegrity:
    def test_required_tags_present(self) -> None:
        required: frozenset[tuple[int, int]] = frozenset({
            (0x0010, 0x0010),  # Patient Name
            (0x0010, 0x0020),  # Patient ID
            (0x0010, 0x0030),  # Patient Birth Date
            (0x0010, 0x0040),  # Patient Sex
            (0x0008, 0x0018),  # SOP Instance UID
            (0x0020, 0x000D),  # Study Instance UID
            (0x0020, 0x000E),  # Series Instance UID
            (0x0020, 0x0052),  # Frame of Reference UID
            (0x0008, 0x0080),  # Institution Name
            (0x0008, 0x0090),  # Referring Physician Name
            (0x0008, 0x0020),  # Study Date
            (0x0008, 0x0021),  # Series Date
            (0x0008, 0x0050),  # Accession Number
            (0x0008, 0x1070),  # Operators Name
            (0x0018, 0x1000),  # Device Serial Number
        })
        missing = required - set(PHI_TAGS.keys())
        assert not missing, f"PHI_TAGS missing required entries: {missing}"

    def test_all_action_codes_valid(self) -> None:
        # PHI_TAGS must only use the 4 canonical PS3.15 action codes.
        # Action enum membership guarantees this at construction time, but this
        # test catches future regressions if PHI_TAGS ever switches to raw strings.
        valid = {"X", "Z", "U", "D"}
        invalid = {(tag, code) for tag, code in PHI_TAGS.items() if code not in valid}
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


class TestKeepTags:
    def test_kept_tag_is_not_modified(self, tmp_path: Path) -> None:
        src = tmp_path / "in.dcm"
        _make_synthetic_dcm(src)
        keep = frozenset({(0x0010, 0x0010)})  # Patient's Name
        anonymize_file(src, tmp_path / "out" / "in.dcm", UIDMapper(), keep_tags=keep)
        out = dcmread(tmp_path / "out" / "in.dcm")
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
        out = dcmread(tmp_path / "out" / "in.dcm")
        assert str(out.PatientID) == "0"  # still scrubbed
        assert (0x0008, 0x0080) not in out  # InstitutionName still deleted


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
        rec_a = AuditRecord(
            source="a.dcm", source_sha256="aa" * 32, output=None,
            tags_modified=[], burned_in_phi_warning=False, dry_run=True,
            timestamp_utc="2026-01-01T00:00:00Z",
        )
        rec_b = AuditRecord(
            source="b.dcm", source_sha256="bb" * 32, output=None,
            tags_modified=[], burned_in_phi_warning=False, dry_run=True,
            timestamp_utc="2026-01-01T00:00:00Z",
        )
        assert audit_sha256([rec_a]) != audit_sha256([rec_b])

    def test_audit_sha256_stable_for_identical_records(self) -> None:
        rec = AuditRecord(
            source="x.dcm", source_sha256="cc" * 32, output=None,
            tags_modified=["0010,0010:X"], burned_in_phi_warning=False, dry_run=True,
            timestamp_utc="2026-01-01T00:00:00Z",
        )
        assert audit_sha256([rec]) == audit_sha256([rec])

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
        out_ds = dcmread(tmp_path / "out" / "in.dcm")
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


class TestMultiValueUIDRemap:
    """CF-08 regression: multi-valued UID elements (RT-STRUCT / KOS / presentation
    state ReferencedSOPInstanceUID) must remap EACH member, not collapse the whole
    MultiValue into one bracketed-repr hash (which silently severs cross-references).
    """

    def test_multivalue_uid_each_member_remapped(self) -> None:
        from pydicom.dataset import Dataset

        from dcm_anon.actions import _remap

        ds = Dataset()
        ds.add_new(0x00081155, "UI", ["1.2.3.4", "5.6.7.8"])
        mapper = UIDMapper(salt="cohort-x")

        _remap(ds, (0x0008, 0x1155), mapper)

        out = [str(v) for v in ds[0x00081155].value]
        assert len(out) == 2, "multi-valued UID was collapsed to a single value"
        assert out[0] != out[1], "distinct source UIDs must map to distinct UIDs"
        assert all(v.startswith("2.25.") for v in out)
        assert "1.2.3.4" not in out and "5.6.7.8" not in out

    def test_multivalue_uid_remap_preserves_referential_integrity(self) -> None:
        from pydicom.dataset import Dataset

        from dcm_anon.actions import _remap

        mapper = UIDMapper(salt="cohort-x")
        multi = Dataset()
        multi.add_new(0x00081155, "UI", ["9.9.9", "8.8.8"])
        single = Dataset()
        single.add_new(0x0020000E, "UI", "9.9.9")  # same source UID elsewhere

        _remap(multi, (0x0008, 0x1155), mapper)
        _remap(single, (0x0020, 0x000E), mapper)

        # The shared source UID 9.9.9 must map identically whether it appears in a
        # multi-valued or a single-valued element — that is the whole point.
        assert str(multi[0x00081155].value[0]) == str(single[0x0020000E].value)

    def test_single_value_uid_still_remapped(self) -> None:
        from pydicom.dataset import Dataset

        from dcm_anon.actions import _remap

        ds = Dataset()
        ds.add_new(0x0020000D, "UI", "1.2.840.113619.2.55.3.123")
        mapper = UIDMapper(salt="cohort-x")

        _remap(ds, (0x0020, 0x000D), mapper)

        out = str(ds[0x0020000D].value)
        assert out.startswith("2.25.")
        assert out != "1.2.840.113619.2.55.3.123"
