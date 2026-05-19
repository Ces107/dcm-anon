# Contributing to dcm-anon

This is a CLI tool for DICOM anonymization. The correctness bar is high: a wrong action code or a missed tag leaks PHI. Contributions must be grounded in the DICOM standard.

**In scope:** bug fixes, PS3.15 tag corrections (with standard citation), test coverage, documentation.

**Not in scope (planned for hosted API):** pixel OCR, DICOM SR scanning, private-tag profiles, GUI.

If you are unsure, open an issue first.

## How to file issues

1. Check existing issues; duplicates will be closed.
2. For **incorrect PHI handling** (wrong tag, wrong action code): cite the exact row
   in DICOM PS3.15 Table E.1-1 (current edition at
   https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_e.html).
3. For **pydicom API misuse**: link to the relevant pydicom release notes or API docs.
4. For **test failures**: include the Python version, pydicom version, and the full
   pytest output.

## Running tests locally

```bash
# Install all dev dependencies
pip install -e ".[dev]"

# Run the full suite with coverage
pytest tests/ -v --cov=dcm_anon --cov-report=term-missing

# Lint
ruff check dcm_anon/ tests/ spaces/

# Type check
mypy dcm_anon/ --strict
```

Tests must pass on Python 3.10, 3.11, and 3.12 before any PR is merged.
Coverage must remain ≥80%.

## Pull request checklist

- [ ] Tests added or updated for the change.
- [ ] `ruff check` passes with no errors.
- [ ] `mypy --strict` passes with no errors.
- [ ] CHANGELOG.md updated under the `[Unreleased]` section.
- [ ] If adding a new PHI tag: DICOM PS3.15 citation included in the PR description.

Commit style: plain English imperative, one logical change per commit. Examples:
- `add (0008,0020) Study Date to PHI_TAGS with action X`
- `fix file_meta MediaStorageSOPInstanceUID remap consistency`
- `add sequence recursion for SQ children`

## Code style

Run ruff and mypy before pushing. That's the bar.
