"""UID + pseudonym hardening (CF-16).

The salt is a secret HMAC key, not a plain hash input, and identity tags get a
stable PER-PATIENT pseudonym so distinct patients stay distinct (the old
'0'/'ANON' constants merged every patient into one record).
"""
from __future__ import annotations

from pathlib import Path

from pydicom import dcmread

from dcm_anon import UIDMapper, anonymize_file
from tests.conftest import _make_synthetic_dcm


class TestUidMapperHardening:
    def test_same_salt_is_deterministic(self) -> None:
        a = UIDMapper(salt="high-entropy-secret")
        b = UIDMapper(salt="high-entropy-secret")
        assert a.remap("1.2.840.113619.2.55.3.1") == b.remap("1.2.840.113619.2.55.3.1")

    def test_different_salt_diverges(self) -> None:
        a = UIDMapper(salt="secret-A")
        b = UIDMapper(salt="secret-B")
        assert a.remap("1.2.840.113619.2.55.3.1") != b.remap("1.2.840.113619.2.55.3.1")

    def test_remapped_uid_does_not_embed_original(self) -> None:
        m = UIDMapper(salt="s")
        out = m.remap("1.2.840.113619.2.55.3.123456789")
        assert out.startswith("2.25.")
        assert "123456789" not in out

    def test_pseudonym_distinct_and_stable(self) -> None:
        m = UIDMapper(salt="s")
        assert m.pseudonym("MRN-0001") != m.pseudonym("MRN-0002")
        assert m.pseudonym("MRN-0001") == m.pseudonym("MRN-0001")

    def test_pseudonym_none_without_salt(self) -> None:
        assert UIDMapper().pseudonym("MRN-0001") is None


class TestPerPatientPseudonyms:
    def _anon_patient(self, tmp_path: Path, pid: str, salt: str | None) -> str:
        src = tmp_path / f"{pid}.dcm"
        _make_synthetic_dcm(src)
        ds = dcmread(src)
        ds.PatientID = pid
        ds.save_as(src, enforce_file_format=True)
        out = tmp_path / f"{pid}-out.dcm"
        anonymize_file(src, out, UIDMapper(salt=salt))
        return str(dcmread(out).PatientID)

    def test_distinct_patients_get_distinct_ids_with_salt(self, tmp_path: Path) -> None:
        a = self._anon_patient(tmp_path, "PATIENT-A", salt="s")
        b = self._anon_patient(tmp_path, "PATIENT-B", salt="s")
        assert a != b
        assert a.startswith("DEID-") and b.startswith("DEID-")

    def test_no_salt_collapses_to_constant(self, tmp_path: Path) -> None:
        a = self._anon_patient(tmp_path, "PATIENT-A", salt=None)
        b = self._anon_patient(tmp_path, "PATIENT-B", salt=None)
        assert a == b == "0"
