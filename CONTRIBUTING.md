# Contributing to dcm-anon

## Scope of accepted contributions

The primary goal of this project is to be **a correct, auditable implementation of
DICOM PS3.15 Basic Application Level Confidentiality Profile** in Python.

Contributions that will be considered:

- Bug fixes and corrections to the PS3.15 tag list or action codes.
- Additional test coverage (especially edge cases from real DICOM IODs).
- Performance improvements that do not sacrifice correctness.
- Documentation fixes and clarifications.

Contributions that are **out of scope** for the OSS core:

- Pixel-level OCR redaction (this is a research problem; planned for the hosted API tier).
- DICOM SR structured-report content scanning.
- Private tag profiles beyond "delete all private tags" (requires per-vendor knowledge;
  can be addressed via a plugin/hook mechanism in a future release).
- GUI / web UI (CLI is the intended interface for the OSS tool).

If you are unsure whether a contribution fits, open an issue first.

## How to file issues

1. Check existing issues — duplicates will be closed.
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
pytest test_anonymize.py -v --cov=anonymize --cov-report=term-missing

# Lint
ruff check anonymize.py conftest.py test_anonymize.py

# Type check
mypy anonymize.py --strict --ignore-missing-imports
```

Tests must pass on Python 3.10, 3.11, and 3.12 before any PR is merged.
Coverage must remain ≥80%.

## Commit style

Plain English imperative. One logical change per commit.
Examples:
- `add (0008,0020) Study Date to PHI_TAGS with action X`
- `fix file_meta MediaStorageSOPInstanceUID remap consistency`
- `add sequence recursion for SQ children`

## Pull request checklist

- [ ] Tests added or updated for the change.
- [ ] `ruff check` passes with no errors.
- [ ] `mypy --strict` passes with no errors.
- [ ] CHANGELOG.md updated under the `[Unreleased]` section.
- [ ] If adding a new PHI tag: DICOM PS3.15 citation included in the PR description.

## Code style

- `final` on module-level constants (`Final[...]` type hint).
- Functional over imperative where it aids readability.
- Maximum one level of indentation inside functions; extract helpers otherwise.
- No comments except docstrings on public functions and inline citations for
  DICOM standard references.
