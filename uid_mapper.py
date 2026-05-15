"""Stable original→new UID mapping.

Single responsibility: track UID rewrites for one anonymization run and ensure
that the same original UID always maps to the same output UID within that run
(or across runs, when a salt is provided).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from pydicom.uid import generate_uid

# DICOM-registered prefix for UUID-derived UIDs (see PS3.5 Annex B).
_DICOM_UID_PREFIX = "2.25."
_MAX_UID_LENGTH = 64
_HEX_BYTES_FOR_UID = 30  # 30 hex chars ≈ 120 bits, safely under 64-char UID limit


@dataclass
class UIDMapper:
    """Stable original→new UID mapping.

    With a *salt*, UIDs are derived deterministically via SHA-256, so the same
    salt + same source UID always produces the same output. Useful for
    reproducible anonymization across runs (longitudinal cohorts).
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

    def size(self) -> int:
        return len(self._mapping)

    def _derive_uid(self, original: str) -> str:
        digest = hashlib.sha256(f"{self.salt}\x00{original}".encode()).hexdigest()
        decimal_part = str(int(digest[:_HEX_BYTES_FOR_UID], 16))
        return f"{_DICOM_UID_PREFIX}{decimal_part}"[:_MAX_UID_LENGTH]
