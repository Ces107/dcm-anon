# Post-mortem: PHI leak via Original Attributes Sequence (v0.3.5)

**Status:** fixed in v0.3.5 before any public release. No production impact (project was still pre-launch).

**Date detected:** 2026-05-18.
**Discovered by:** pre-release adversarial review (5 parallel red-team subagents).

## What happened

PS3.15 mandates action `X` (remove) on `(0400,0561) OriginalAttributesSequence`. PACS systems (Merge, Agfa IMPAX, Philips IntelliSpace) populate this SQ with pre-coercion original values of every attribute the PACS modified during ingestion: original `PatientName`, original `PatientID`, original `StudyDate`, etc.

Pre-v0.3.5, `(0400,0561)` was missing from `PHI_TAGS`. The pipeline did not target it. The independent verifier (`verify_output._scan_metadata`) did not recurse into Sequence items, so the manifest reported `passed=True` with the original PHI sitting in the nested SQ.

End result: a study anonymised from a PACS-origin source would carry the original PHI in the audit trail SQ, while the manifest and verifier both attested clean.

## Vector and scope

- Triggered only on DICOMs that already passed through a PACS ingestion step (Merge / Agfa / IntelliSpace and similar). Bare-modality output (DICOM straight from the scanner) does not populate this SQ.
- Affected: any direct call to `anonymize_file` or `anonymize_path` on such DICOMs in versions 0.3.0 through 0.3.4.
- Not affected: pre-public-release. No external user ran v0.3.0-0.3.4 against real PACS data (project private until v0.3.5).

## Why the tests missed it

The original test fixture in `tests/conftest.py` synthesises DICOMs from scratch and does not populate `OriginalAttributesSequence`. A `(0400,0561)`-bearing fixture was not in the test corpus. The PS3.15 reference table that seeded `PHI_TAGS` covered the 2018 edition, where this SQ is mentioned but its full leak surface (nested SQs propagating original values) was not explicit.

## Fix

1. Added `(0400,0561) OriginalAttributesSequence` with action `X` to `PHI_TAGS` (along with 18 other Basic Profile and retired tags that were missing from the 2018-era table, bringing the total to 143 explicit entries plus curve/overlay range masks).
2. Made `verify_output._scan_metadata` recurse into `Sequence` items so PHI surviving inside any nested SQ is detected by the independent verifier.
3. `pipeline._scrub_dataset` already recursed into sequences via `_recurse_into_sequences`; the fix closed the verifier gap, and adding `(0400,0561)` to `PHI_TAGS` caused the pipeline to delete the SQ outright (action X).
4. `TestTagTableIntegrity` in `tests/test_anonymize.py` asserts that required tags are present in `PHI_TAGS` and that all action codes are valid. `TestSequenceRecursion` asserts that PHI inside nested sequences is scrubbed. Both classes now transitively cover this fix.

## What prevents recurrence

The independent verifier's PHI tag list is sourced from HIPAA Safe Harbor §164.514(b)(2) plus the TCIA de-identification checklist (different source-of-truth from `phi_table.py`), so a similar omission would have to occur in two independent curations simultaneously to slip through silently.

For future PS3.15 Table E.1-1 amendments: re-verify against the latest published table on each major dcm-anon release.
