# Security Policy

## Scope

dcm-anon is a **local command-line tool and Python library** for DICOM anonymization.
It does not run a server, expose a network interface, or handle authentication.
The attack surface is therefore limited to:

1. Malformed or adversarially crafted DICOM files fed to the `dcm-anon` CLI.
2. Path-traversal via crafted `dst` paths in the Python API.
3. Incorrect PHI removal — a tag present in a DICOM file that is NOT stripped when it should be.

## What qualifies as a security issue

- **PHI disclosure**: a tag that the DICOM PS3.15 Basic Profile requires to be
  removed or replaced is NOT being removed or replaced by this tool.
- **Path traversal**: the output path calculation writes files outside the intended
  destination directory.
- **Arbitrary code execution**: a crafted DICOM file causes execution of unintended
  code (this would be a pydicom vulnerability; report to pydicom first and CC me).

## What does NOT qualify

- The tool not handling pixel-level OCR redaction — this is a documented limitation,
  not a vulnerability.
- Private tags not being scrubbed — this is a documented limitation of the Basic
  Profile scope. Institutions requiring private-tag handling should implement a
  custom profile.
- Missing tags from supplemental confidentiality profiles (Clean Descriptors, Retain
  UIDs, etc.) — the tool only implements the Basic Profile.

## Responsible disclosure

Please report security issues by email to **plusultra.dev@proton.me** with subject
`[dcm-anon] security`, or via the GitHub Security Advisories tab on
`https://github.com/Ces107/dcm-anon`.

Include:
- A description of the issue.
- A minimal reproducible DICOM file or synthetic reproduction steps.
- The expected versus actual behavior with reference to the relevant DICOM standard section.

I aim to respond within 5 business days and to issue a patch within 14 days for
confirmed PHI-disclosure issues.

## No bug bounty

This is an open-source project with no commercial entity behind it. I cannot offer
monetary rewards, but I will credit responsible disclosers in the CHANGELOG.
