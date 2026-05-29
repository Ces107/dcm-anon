# Security Policy

## Scope

dcm-anon is a **local command-line tool and Python library** for DICOM anonymization.
It does not run a server, expose a network interface, or handle authentication.
The attack surface is limited to:

1. Malformed or adversarially crafted DICOM files fed to the `dcm-anon` CLI.
2. Path-traversal via crafted `dst` paths in the Python API.
3. Incorrect PHI removal: a tag present in a DICOM file that is NOT stripped when it should be.

Security issues:

- **PHI disclosure**: a tag that the DICOM PS3.15 Basic Profile requires to be
  removed or replaced is NOT being removed or replaced by this tool.
- **Path traversal**: the output path calculation writes files outside the intended
  destination directory.
- **Arbitrary code execution**: a crafted DICOM file causes execution of unintended
  code (this would be a pydicom vulnerability; report to pydicom first and CC me).

Not security issues:

- **Burned-in pixel PHI, recognizable faces (head CT/MR), encapsulated PDF/CDA, and
  un-scrubbed SR free text**: these are channels a header de-identifier cannot clear.
  As of v0.6.0 the tool FAILS CLOSED on them (nonzero exit, manifest discloses the
  unresolved risk) rather than silently certifying clean. Shipping such data after an
  explicit `--allow-*` waiver is the user's accepted risk, not a tool vulnerability.
- Missing tags from a LATER DICOM edition than the pinned table: caught only by the
  deny-by-default identifier-VR sweep, not by name. Report a specific leaking tag and
  it will be added.

## The salt is a SECRET KEY (re-identification threat model)

Deterministic mode (`--salt`) derives UIDs and patient pseudonyms via
**HMAC-SHA256 keyed on the salt**. This makes output reproducible for longitudinal
cohorts while keeping it one-way for anyone without the salt. Consequences:

- The salt is **GDPR Art. 4(5) "additional information"**: whoever holds it can
  recompute the entire mapping and **re-identify the whole cohort at once** (not one
  record). Store it in a separate vault from the de-identified data; never commit it,
  log it, or ship it alongside the output.
- Use a **high-entropy random secret**. A guessable salt (e.g. a project name) is
  brute-forceable against the low-entropy, structured UID inputs.
- Output is therefore **PSEUDONYMOUS, not anonymous**. Do not label it "anonymous".
- A leaked or weak salt is a deployment/key-management failure, not a tool bug. A salt
  *derivation* weakness in the tool (e.g. a non-keyed hash, predictable output) IS a
  security issue — report it.

## Responsible disclosure

Please report security issues by email to **plusultra.dev@proton.me** with subject
`[dcm-anon] security`, or via the GitHub Security Advisories tab on
`https://github.com/Ces107/dcm-anon`.

Include:
- A description of the issue.
- A minimal reproducible DICOM file or synthetic reproduction steps.
- The expected versus actual behavior with reference to the relevant DICOM standard section.

I'll try to reply within a week and patch confirmed PHI-disclosure bugs within two weeks. No guarantees: this is a side project, not a product. No bug bounty either, but I will credit responsible disclosures in the CHANGELOG.
