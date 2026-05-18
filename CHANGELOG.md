# Changelog

All notable changes to dcm-anon are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

*(nothing yet)*

---

## [0.3.2] — 2026-05-18

### Changed (packaging only — no functional changes)

- **Distribution name on PyPI is `dcm-anonymizer`** (the slug `dcm-anon` is
  refused by PyPI because of similar-name collisions with two legacy projects
  `dcmanon` and `dicom-anon`). The CLI command, the import path, and the
  project branding remain `dcm-anon`. Install with `pip install dcm-anonymizer`.
- **Re-tagged release to trigger Zenodo DOI minting** after the GitHub-Zenodo
  webhook was activated. v0.3.1 shipped just before webhook activation and
  therefore has no DOI; v0.3.2 is functionally identical and is the first
  release with a citable DOI.

---

## [0.3.1] — 2026-05-13

### Changed (hardened from 5-agent adversarial red team)

- **EU AI Act enforcement date corrected to 2027-12-02** (standalone high-risk
  AI) / **2028-08-02** (SaMD embedded in MDR/IVDR Class IIb/III), reflecting the
  Digital Omnibus agreement (Council + Parliament, 7 May 2026). Previous draft
  cited the now-deferred 2026-08-02 deadline. The manifest now carries an
  explicit `EU AI Act enforcement context` disclosure section noting the
  deferral so a reader cannot accuse the tool of pretending to a deadline that
  no longer exists.
- **HIPAA manifest now carries a Safe-Harbor-only declaration.** The
  `HIPAA method declaration` regime disclosure states explicitly that
  §164.514(b)(2) is implemented and §164.514(b)(1) Expert Determination requires
  a qualified human statistician — defending against the documented failure
  mode where covered entities mistake mechanical tool output for Expert
  Determination evidence.
- **GDPR manifest now carries an Art. 9 lawful-basis disclosure.** The
  `GDPR Art. 9 lawful basis` regime disclosure states that the tool does NOT
  establish the Art. 9(2) ground required to process special-category health
  data — addressing the gap that DPAs (CNIL, ICO, AEPD) pursue first in
  enforcement actions, before evaluating pseudonymisation adequacy.

### Added

- `regulatory_mapping.EXPERT_DETERMINATION_DISCLAIMER`, `GDPR_ART9_DISCLOSURE`,
  `AI_ACT_DEADLINE_CONTEXT` — three new module-level constants surfacing the
  defensive disclosures.
- `ComplianceManifest.regime_disclosures: list[tuple[str, str]]` — the new
  schema field carrying regime-specific disclosures. Covered by the SHA chain.
- Independent PHI tag scanner expanded **36 → 42 tags**. Added: `OperatorsName`
  (0008,1070), `PatientComments` (0010,4000), `AdmittingDiagnosesDescription`
  (0008,1080), `PatientReligiousPreference` (0010,21F0), `SpecialNeeds`
  (0038,0050), `ScheduledPerformingPhysicianName` (0040,0006). All were flagged
  by Red Team #5 as Table E.1-1 PS3.15 tags missing from the independent list,
  which would have let a class of residuals slip past `--verify-output`.
- `verify_output.PixelOCRUnavailableError`. When `pixel_ocr=True` and
  `pytesseract`/`tesseract` is missing, `scan_outputs(...)` now raises by
  default (`strict_ocr=True`). Silent degradation produced a false green
  manifest — a worse failure mode than a clean crash. Callers who explicitly
  want metadata-only fallback can pass `strict_ocr=False`.
- New test class `TestCrossFileUIDLinkage` verifying that the same source UID
  appearing in multiple files of a batch (RT-STRUCT-style scenario) is
  remapped to the same new UID — regression-proof against the radiotherapy
  failure mode Red Team #5 identified.
- New tests for regime-specific disclosures, expanded tag list, OCR strict
  failure mode. Test suite grows **125 → 132 tests** (all passing).

### Fixed

- Manifest format version bumped to **1.2** to reflect the new
  `regime_disclosures` schema field.

### Documentation

- README hero rewritten. Removed dependence on the now-deferred
  2026-08-02 deadline. Wedge is now framed around the perennial Safe Harbor
  + GDPR pseudonymisation evidence gap. EU AI Act remains a regime option but
  no longer the urgency hook.

### Red team artifacts

- 5 parallel adversarial agents (buyer existence, regulatory rejection,
  clone speed, distribution failure, technical edge cases) attacked v0.3.0.
  Findings + verdicts logged in `state/spawn-log.jsonl`. Two existential
  findings (Digital Omnibus deadline collapse, throwaway-HN distribution
  unreachable) drove the v0.3.1 changes and a strategy-level rethink of
  the launch plan.

---

## [0.3.0] — 2026-05-13

### Added (features)

- **`--manifest-mode [eu-ai-act|hipaa|gdpr]`**: emit a regulator-clause-cited
  compliance manifest (`compliance_manifest.json` + `COMPLIANCE_MANIFEST.md`)
  after anonymization. Each PS3.15 action code (X/Z/U/D) is mapped to the
  verbatim regulatory clauses it implements, plus the relevant audit-trail
  clauses (AI Act Art. 12 + Art. 18, HIPAA 45 CFR 164.312(b), GDPR Art. 30 +
  Art. 5(2)). Manifest carries its own SHA-256 chained from `audit_sha256`,
  so any tampering with either layer is detectable.
- **`--verify-output`**: after anonymization, run an independent post-run
  PHI residual scan over a sample of output files (default 10). Uses a
  separate PHI tag list curated from HIPAA Safe Harbor §164.514(b)(2) and
  the TCIA de-identification checklist — explicitly NOT derived from the
  internal `phi_table`, to break the self-attestation problem. Result is
  embedded in the manifest and covered by the SHA chain.
- **`--verify-output-sample N`** + **`--verify-output-pixel-ocr`**: tune
  sample size or enable pytesseract OCR scanning of pixel data (optional
  dependency; silently degrades if `pytesseract` / `tesseract` is missing).
- **`--verify-manifest MANIFEST.json --audit AUDIT.json`**: separate mode
  that re-computes the manifest SHA chain against an audit log, reports
  PASS / FAIL with itemised reasons, exits non-zero on any mismatch.
- **Authoritative-guidance registry**: each regime ships its post-2024
  state-of-the-art interpretation docs (EU AI Act → MDCG 2025-6 + GPAI
  Code of Practice; HIPAA → NIST SP 800-66r2 + HHS OCR de-id guidance;
  GDPR → EDPB Guidelines 01/2025 on Pseudonymisation + ENISA health-sector
  guidance). Embedded in the manifest under `guidance_references`.
- **Output classification + re-identification risk statement**: every
  manifest explicitly labels the output as `pseudonymous` (NOT anonymous)
  under GDPR Art. 4(5), with a verbatim risk statement addressing the
  CNIL/Cegedim Santé enforcement pattern (€800K fine, September 2024).
- **`scan_outputs(...)`** and **`build_manifest(...)`** are part of the
  public Python API; `from anonymize import …` exposes them.

### Changed

- **Regulatory mapping completely re-verified.** Citations re-verified
  verbatim against EUR-Lex, eCFR (Cornell LII), and gdpr-info.eu on
  2026-05-13. **Critical correction:** EU AI Act Art. 10(5) was misapplied
  in earlier drafts — it is the *bias-detection exception*, not a general
  data-governance hook. Action X now cites Art. 10(2)(b) + 10(2)(c) +
  10(3). Actions Z / U / D delegate to GDPR Art. 32(1)(a) + Art. 4(5) (or
  Art. 32(1)(a) + Recital 26 for dummies). Audit trail moved to Art. 12
  (record-keeping) + Art. 18 (10-year technical-file retention).
- README has a new **Compliance manifest** section with worked example
  output, regime selection guidance, and the verification workflow.
- CI workflow now lints and type-checks the full module list (`ruff .`
  and explicit mypy invocation across 10 modules).

### Added (modules)

- `regulatory_mapping.py` — pure-data registry of regimes, action-to-clause
  maps, audit-trail clauses, authoritative guidance, the pseudonymous risk
  statement, and the disclaimer.
- `manifest.py` — `ComplianceManifest` dataclass, `build_manifest()`,
  `verify_manifest()`, `render_markdown()`, JSON loaders.
- `verify_output.py` — `scan_outputs()` independent PHI residual scanner
  with optional pixel OCR pass.
- `test_manifest.py` — 59 tests covering regimes, clauses, audit trail,
  guidance, verification, manifest build/verify/render, and the four CLI
  paths.

### Tests + tooling

- Test suite grows 66 → 125 (all passing).
- Coverage 92.5% → 88.9% (drop is the un-tested OCR path in
  `verify_output`; rest of the codebase is 89-100%).
- Manifest format version: **1.1**.

---

## [0.2.0] — 2026-05-05

### Added (features)

- **`--dry-run`**: process files in memory and emit the audit log without writing
  anonymized outputs to disk. Useful for previewing what an anonymization run will
  do before committing.
- **`--continue-on-error`**: a malformed DICOM no longer aborts the batch. Each
  failure is captured in the audit `errors` list with the source path, exception
  type, and message. Non-zero exit code surfaces the failure.
- **`--keep GGGG,EEEE`** (repeatable): whitelist a tag by hex `(group, element)`.
  Skipped tags are not modified and do not appear in `tags_modified`.
- **`--quiet` / `--verbose`**: control logging verbosity.
- **`--report-md PATH`**: emit a human-readable Markdown summary in addition to
  the JSON audit log. Designed for IRB submissions.
- **`--version`**: prints `dcm-anon 0.2.0` and exits.
- **Audit log signing**: every audit summary now includes `audit_sha256`, the
  SHA-256 of the canonical-JSON encoding of the records list. Tamper-evident.
- **Optional progress bar**: when `tqdm` is installed (`pip install dcm-anonymizer[progress]`)
  and stdout is a TTY, batch runs show a per-file progress bar. Falls back to a
  stderr counter when `tqdm` is unavailable.

### Changed (architecture — SOLID refactor)

- Split the monolithic `anonymize.py` into single-responsibility modules:
  - `phi_table.py` — PS3.15 reference data (PHI tag table, placeholders, curve groups).
  - `actions.py` — `Action(str, Enum)` replaces magic-string codes (`"X"`/`"Z"`/...);
    `ActionRegistry` provides an open dispatch table per the Open/Closed Principle.
  - `uid_mapper.py` — `UIDMapper` (random or salted-deterministic UID remapping).
  - `audit.py` — typed `@dataclass(frozen=True)` records: `AuditRecord`,
    `AuditSummary`, `ProcessingError`. Replaces the previous `dict[str, object]`
    return type that disabled static analysis.
  - `pipeline.py` — `anonymize_file` / `anonymize_path` orchestration + the new
    `AnonymizationConfig` dataclass for callers passing many options.
  - `cli.py` — argparse + main entry point.
  - `anonymize.py` — public-facing re-export module (backward-compatible).
- Coverage rose from 83% (single file) to **92%** across 7 modules, demonstrating
  that splitting improved testability.
- Public API now exposes typed dataclasses for `AuditRecord` and `AuditSummary`.
  Use `record.tags_modified` (attribute access) instead of `record["tags_modified"]`
  (dict access). For JSON serialisation, call `.as_dict()` on either dataclass.

### Migration from 0.1.0

```python
# before
record = anonymize_file(src, dst, mapper)
print(record["tags_modified"])
json.dumps(record)

# after (typed)
record = anonymize_file(src, dst, mapper)
print(record.tags_modified)
json.dumps(record.as_dict())
```

CLI behaviour is unchanged for existing flag combinations; new flags are additive.

---

## [0.1.0] — 2026-05-05

### Added

- Initial release of `anonymize.py` implementing DICOM PS3.15 (2024 edition)
  Basic Application Level Confidentiality Profile.
- **PHI tag list:** 90+ tags from PS3.15 Table E.1-1, including Study/Series dates,
  Patient Sex, Device Serial Number, Institution Code Sequence, Operators' Name,
  Protocol Name, Request Attributes Sequence, and others missing from earlier
  drafts.
- **Sequence recursion:** PHI tags nested inside Sequence (SQ) items are now
  scrubbed recursively at any depth. Previously nested PHI in sequences such as
  `RequestAttributesSequence` and `ReferencedStudySequence` was silently skipped.
- **File-meta consistency:** `file_meta.MediaStorageSOPInstanceUID` is now remapped
  to the same new UID as the dataset-level `SOPInstanceUID`. Previously these could
  diverge, breaking DICOMDIR and WADO-RS references.
- **Deterministic UID remapping** via `--salt` / `UIDMapper(salt=...)`: identical
  `(salt, original_uid)` pairs always produce the same output UID, enabling
  reproducible anonymization of longitudinal datasets across separate runs.
- **Curve / Overlay wild-card scrubbing:** elements in groups `50xx` and `60xx`
  are deleted, matching the PS3.15 requirement for Curve Data and Overlay Data.
- **`conftest.py`** with a rich synthetic DICOM fixture including sequences,
  multi-frame, burned-in flags, and shared Study UIDs.
- **Full test suite** with 30+ test cases covering:
  - Per-tag PHI removal
  - UID remapping and file-meta consistency
  - Deterministic remap with/without salt
  - Sequence recursion and nested PHI
  - Multi-frame DICOM
  - Burned-in annotation detection
  - Batch `anonymize_path` behavior
  - Tag table integrity assertions
- **CI workflow** (`.github/workflows/test.yml`): pytest on Python 3.10/3.11/3.12,
  ruff lint, mypy strict type check, ≥80% line coverage gate.
- **`pyproject.toml`** with ruff, mypy, pytest, and coverage configuration.
- **`CONTRIBUTING.md`**, **`SECURITY.md`**, and examples.

### Fixed

- `anonymize.py` previously set `ds.is_little_endian` and `ds.is_implicit_VR`
  directly on the `FileDataset` object — these attributes are deprecated in
  pydicom ≥3.0 and will be removed in v4.0. Replaced with
  `save_as(..., enforce_file_format=True)`.
- Action code for `(0020,0010) Study ID` was incorrectly `"X"` (delete); the
  standard requires `"Z"` (replace with placeholder), as Study ID is a Type-2
  attribute in many IODs.
- Action code for `(0008,0080) Institution Name` was `"X"` only; the full standard
  code is `X/Z/D`. The most conservative action (X) is applied, which is conformant.
- `(0008,0082) Institution Code Sequence` was missing from the tag list.
- `(0008,1072) Operator Identification Sequence` was missing.
- `(0008,1049) Physician(s) of Record Identification Sequence` was missing.
- `(0010,0040) Patient's Sex` was missing (standard requires `Z`).
- `(0008,0020)` through `(0008,0033)` Study/Series/Acquisition/Content dates and
  times were all missing; added with correct actions.
- `(0018,1000) Device Serial Number` action was `"X"`; standard is `X/Z/D`
  (X applied, which is conformant).
- `(0008,1195) Transaction UID` and `(0008,0017) Acquisition UID` were missing.
- `(0002,0003) Media Storage SOP Instance UID` (file-meta tag) was handled
  separately but inconsistently; now handled inside `anonymize_file` to guarantee
  UID parity with dataset-level `SOPInstanceUID`.

### Known limitations (documented)

- Private tags: not scrubbed beyond the basic profile. The standard says `X` for
  private attributes as a group, but identifying which private tags contain PHI
  requires vendor-specific knowledge. See `SECURITY.md`.
- Pixel-level OCR: `BurnedInAnnotation = YES` is flagged in the audit log but the
  pixel data is not modified. Pixel OCR redaction is on the hosted API roadmap.
- DICOM SR (Structured Report) content sequences: not scanned for free-text PHI.
- DICOMDIR: directory records are not updated to reflect remapped UIDs. If you
  anonymize a dataset that includes a DICOMDIR, regenerate it after anonymization.
