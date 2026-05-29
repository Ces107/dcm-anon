"""Stable original→new UID mapping for one anonymization run."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

from pydicom.uid import generate_uid

# DICOM-registered prefix for UUID-derived UIDs (see PS3.5 Annex B).
_DICOM_UID_PREFIX = "2.25."
_MAX_UID_LENGTH = 64
_HEX_BYTES_FOR_UID = 30  # 30 hex chars ≈ 120 bits, safely under 64-char UID limit
_PSEUDONYM_HEX_LEN = 12  # 48 bits — ample to keep distinct patients distinct


@dataclass
class UIDMapper:
    """With a *salt*, UIDs and patient pseudonyms are derived deterministically
    via HMAC-SHA256(key=salt), enabling reproducible anonymization across runs
    (longitudinal cohorts) while keeping the mapping one-way for anyone without
    the salt.

    SECURITY: the salt is a SECRET KEY, not a label. Anyone who holds it can
    recompute the mapping and re-identify the entire cohort, so store it in a
    separate vault from the data. HMAC (not a plain salted hash) gives the keyed
    work factor; low-entropy salts are still weak — use a high-entropy random
    secret. Output is therefore PSEUDONYMOUS, never anonymous.
    """

    salt: str | None = None
    _mapping: dict[str, str] = field(default_factory=dict, repr=False)

    def remap(self, original: str) -> str:
        cached = self._mapping.get(original)
        if cached is not None:
            return cached
        new = self._derive_uid(original) if self.salt else generate_uid()
        self._mapping[original] = new
        return new

    def pseudonym(self, original: str) -> str | None:
        """A stable per-value pseudonym token (HMAC-keyed) when a salt is set,
        else ``None`` (caller falls back to a constant placeholder and loses
        cohort separation). Used for PatientID / PatientName so distinct patients
        stay distinct without being reversible to the source.
        """
        if not self.salt:
            return None
        return self._hmac_hex(original)[:_PSEUDONYM_HEX_LEN].upper()

    def size(self) -> int:
        return len(self._mapping)

    def _hmac_hex(self, original: str) -> str:
        assert self.salt is not None  # only reached when a salt is set
        return hmac.new(self.salt.encode(), original.encode(), hashlib.sha256).hexdigest()

    def _derive_uid(self, original: str) -> str:
        decimal_part = str(int(self._hmac_hex(original)[:_HEX_BYTES_FOR_UID], 16))
        return f"{_DICOM_UID_PREFIX}{decimal_part}"[:_MAX_UID_LENGTH]
