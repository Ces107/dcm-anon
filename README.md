# dcm-anon

**OSS DICOM anonymizer with a verbatim-cited, machine-verifiable compliance manifest — for research-data sharing under GDPR Art. 35 DPIA and HIPAA Safe Harbor.**

[![CI](https://github.com/Ces107/dcm-anon/actions/workflows/test.yml/badge.svg)](https://github.com/Ces107/dcm-anon/actions/workflows/test.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20267652.svg)](https://doi.org/10.5281/zenodo.20267652)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](pyproject.toml)
[![Manifest format](https://img.shields.io/badge/manifest_format-v1.2-blueviolet)](manifest.py)

---

## Why this exists

GDPR Art. 35 makes a DPIA mandatory for **large-scale processing of health
data**, and best practice — endorsed by the EDPS, the EDPB pseudonymisation
guidelines (01/2025), and HHS OCR — is to **de-identify at the source site**
before moving research data off-prem. Doing that defensibly means:

1. A traceable mapping from each tag you removed to the **specific clause**
   that obliges you to remove it.
2. An **independent second opinion** that the output does not still contain
   PHI.
3. An **audit trail** that a regulator, IRB, or ethics committee can verify
   without your help.

Most DICOM anonymizers do step 1 implicitly and skip steps 2 and 3. `dcm-anon`
emits all three as first-class artifacts of every run.

> **Context.** This tool is open-sourced as a research artifact accompanying
> ongoing work on fairness-aware Software-as-a-Medical-Device (SaMD) — see
> the author's TFG on inter-hospital fairness in dermatology AI
> ([UPV RiuNet](https://riunet.upv.es/handle/10251/226903)). The compliance-
> manifest layer was built because cross-hospital data preparation kept
> tripping on the same legal-traceability gap.

---

## What it does

Implements the **DICOM PS3.15 Basic Application Level Confidentiality
Profile** (Table E.1-1, 2024 edition; **143 explicit tags covering the mandatory Basic Profile plus retired tags still common in legacy archives and the original-attributes audit trail; curve groups (50xx,xxxx) and overlay groups (60xx,xxxx) handled by range mask, not enumerated**). Five properties:

1. **UID consistency across files.** Anonymize a CT study directory and the
   Study/Series/SOP UIDs remain coherent — slices are still a usable study,
   not 200 orphan files. `file_meta.MediaStorageSOPInstanceUID` is remapped
   to match the dataset-level `SOPInstanceUID`, so DICOMDIR and WADO-RS
   references stay intact.

2. **Audit log out-of-the-box.** Every modified tag is recorded with its
   PS3.15 action code (`X`/`Z`/`U`/`D`), source SHA-256, and UTC timestamp.
   Drop it in your IRB folder.

3. **Nested PHI in Sequence items is scrubbed.** Tags inside
   `RequestAttributesSequence`, `ReferencedStudySequence`, and any other SQ
   element are recursed into and cleaned — not silently skipped.

4. **Compliance manifest — `--manifest-mode [gdpr|hipaa|eu-ai-act]`.** Emits
   a tamper-evident JSON + Markdown artifact that maps each PS3.15 action to
   the specific regulatory clauses it implements (verbatim citations
   re-verified against EUR-Lex / eCFR / gdpr-info.eu on 2026-05-13). Each
   regime carries a defensive disclosure tailored to the failure mode
   regulators actually pursue first: GDPR → Art. 9(2) lawful-basis disclosure
   (controller establishes it independently); HIPAA → Safe-Harbor-only
   declaration (does NOT substitute for Expert Determination); EU AI Act →
   enforcement-date context. The binding date in force as of release is
   2026-08-02 (Annex III high-risk obligations under Reg. (EU) 2024/1689);
   the Digital Omnibus political agreement of 7 May 2026 proposes deferring
   to 2027-12-02 / 2028-08-02 for SaMD embedded in MDR/IVDR but has not yet
   been formally adopted or published in the OJEU.

5. **Independent output verification — `--verify-output`.** After the run,
   re-reads the anonymized files using a **separate** PHI tag list (curated
   from HIPAA Safe Harbor §164.514(b)(2) + TCIA checklist, NOT derived from
   the internal table). Result embedded in the manifest, covered by the SHA
   chain. Defeats the "tool vouches for itself" problem.

```bash
# Single file
dcm-anon input.dcm out/

# Directory (all *.dcm, preserving subdirectory structure)
dcm-anon /data/study_0001 /data/anon/study_0001

# Deterministic UIDs — same salt + same source = same output every run
dcm-anon /data/study_0001 /data/anon/study_0001 --salt cohort-A-2024

# Preview without writing files (audit log still emitted)
dcm-anon /data/study_0001 /data/anon/study_0001 --dry-run

# Continue past malformed DICOMs; collect them in the audit "errors" list
dcm-anon /data/study_0001 /data/anon/study_0001 --continue-on-error

# Whitelist tags (use sparingly — kept tags break the strict-profile claim)
dcm-anon input.dcm out/ --keep 0010,0010 --keep 0008,0090

# Markdown summary alongside the JSON audit log
dcm-anon /data/study out/ --report-md report.md
```

---

## Install

```bash
pip install dcm-anonymizer
# CLI command stays `dcm-anon`. Distribution name on PyPI is `dcm-anonymizer`
# because `dcm-anon` collides with a similar-named legacy project.
# Or, from source:
pip install -e ".[dev]"
```

Runtime dependency: `pydicom>=2.4`. Optional: `pytesseract` (plus the system `tesseract` binary) for pixel-data PHI scanning via `--verify-output-pixel-ocr`. The default is strict — if pytesseract is unavailable the CLI raises `PixelOCRUnavailableError` rather than silently producing a green manifest; pass `--no-strict-ocr` to opt into a metadata-only fallback.

---

## Compliance manifest

The manifest answers the single question every reviewer asks:
*"how do I prove this de-identification step satisfies the regulation?"*
It maps every PS3.15 action that ran on your data to the specific regulatory
clauses it implements, with verbatim citations and links to canonical text.

### Usage

```bash
# GDPR Art. 4(5) pseudonymisation + Art. 32(1)(a) technical safeguard
dcm-anon /data/study out/ --manifest-mode gdpr --verify-output

# HIPAA Safe Harbor (45 CFR 164.514(b)(2))
dcm-anon /data/study out/ --manifest-mode hipaa --verify-output

# EU AI Act Art. 10 data governance
# (binding date 2026-08-02; Digital Omnibus deferral to 2027-12-02 / 2028-08-02
# is a provisional political agreement only, not yet adopted)
dcm-anon /data/study out/ --manifest-mode eu-ai-act --verify-output

# Verify an existing manifest against its audit (e.g. on the auditor's machine)
dcm-anon --verify-manifest compliance_manifest.json \
                    --audit anonymization_audit.json
```

Three files land alongside `anonymization_audit.json`:

```
out/
├── COMPLIANCE_MANIFEST.md       Human-readable. Attach to your tech file.
├── compliance_manifest.json     Structured + SHA-chained. For auditors / CI.
└── anonymization_audit.json     The per-tag log the manifest signs over.
```

### What the manifest contains

- **Tool + PS3.15 profile + generation timestamp** (post-Cegedim defensive
  stamp).
- **Regulatory regime metadata** + enforcement-date context (live counter
  for AI Act).
- **Output classification:** explicitly `pseudonymous` (NOT anonymous) under
  GDPR Art. 4(5), with a risk statement reflecting the CNIL / Cegedim Santé
  decision SAN-2024-013 (€800K, 5 September 2024). The violation there was
  Art. 5(1)(a) GDPR + Art. 66 French DPA — unlawful processing of health
  data because a false anonymisation claim was used as a substitute for a
  lawful basis under Art. 9. The manifest's pseudonymous label and Art. 9
  disclosure address the upstream factual gap that drove that enforcement;
  they are not a substitute for the controller establishing an Art. 9(2)
  ground.
- **Per-action clauses.** For each PS3.15 action (X/Z/U/D) used in the run:
  count, citation, short title, verbatim regulatory summary. Examples:
  - Action `U` (UID remap) under HIPAA cites **45 CFR 164.514(c)** —
    "re-identification code".
  - Action `Z` (zero) under GDPR cites **Art. 32(1)(a) + Art. 4(5)**.
  - Action `X` (remove) under EU AI Act cites **Art. 10(2)(b) + 10(2)(c)
    + 10(3)** — *not* Art. 10(5), which is the narrow bias-detection
    exception.
- **Audit-trail clauses.** Clauses that justify the existence of the signed
  log itself: AI Act Art. 12 + Art. 18, HIPAA 164.312(b), GDPR Art. 30 +
  Art. 5(2).
- **Authoritative guidance applied.** Post-2024 docs that regulators apply
  in audits: EDPB Guidelines 01/2025 (pseudonymisation-domain model — draft
  for public consultation; final version pending), MDCG 2025-6 (MDR ↔ AI Act
  interplay for SaMD), NIST SP 800-66r2, HHS OCR de-id guidance, ENISA
  health-sector pseudonymisation. The GPAI Code of Practice is referenced
  only as context — it applies under AI Act Art. 53(1)(d) to providers of
  general-purpose AI models, not to narrow-domain SaMD; cite it only if
  the system also qualifies as a GPAI provider under Art. 3(63).
- **Independent output verification** (when `--verify-output` is set):
  files scanned, tag list size, residuals found. Counted in the SHA chain.
- **Two SHA-256 hashes:** `audit_sha256` (over the per-file log) and
  `manifest_sha256` (over the manifest payload including `audit_sha256` and
  the verification block). Tampering either layer fails verification.

### Disclaimer

The manifest is an **engineering artifact, not legal advice**. It does not
certify compliance and does not replace review by your Quality Management
System and legal counsel. Cited regulatory text must be independently
verified against the canonical source before submission to any regulator
or notified body.

### Note for Spanish public-sector hospitals (ENS)

Public-sector data controllers in Spain (including SNS hospitals) are
subject to the **Esquema Nacional de Seguridad** ([Real Decreto 311/2022](https://www.boe.es/eli/es/rd/2022/05/03/311/con))
in addition to GDPR. ENS system categorisation is impact-based (Annex I,
Art. 40 of RD 311/2022) — it is not derived automatically from data type.
Processing health data in an SNS context will typically result in a
**Nivel ALTO** categorisation, given the potential for serious harm if
confidentiality, integrity, or availability is compromised. Under that
classification, the signed audit log and verbatim-cited manifest produced
by this tool address the CAT-ALTA technical security measures `op.exp.8`
(registro de actividad), `mp.info.3` (cifrado) and `mp.info.6` (limpieza
de documentos) in combination with the controller's organisational measures.
ENS does NOT replace GDPR or any third-country regime (HIPAA, etc.); it is
the domestic-law backstop AEPD-supervised entities are audited against.

### Verification (auditor workflow)

```bash
# Independent party, with only the JSON files, can verify integrity:
dcm-anon \
  --verify-manifest path/to/compliance_manifest.json \
  --audit path/to/anonymization_audit.json
# → PASS: manifest ... matches audit ...
# (exit code 0; non-zero on any tamper / mismatch with itemised reasons)
```

---

## Architecture

Single-responsibility modules; `anonymize.py` re-exports the public API.

```
phi_table.py          PS3.15 Table E.1-1 reference data.
actions.py            Action(str, Enum) — X / Z / U / D. ActionRegistry.
uid_mapper.py         Random or salted-deterministic UID remap (SHA-256(salt+orig) → 2.25.xxx).
audit.py              Frozen dataclasses (AuditRecord / AuditSummary / ProcessingError).
                      audit_sha256 — tamper-evident hash. render_markdown_report.
pipeline.py           AnonymizationConfig dataclass; anonymize_file / anonymize_path.
                      Point-tag actions + curve/overlay range scrub + SQ recursion.
cli.py                Argparse + main. All user-facing flags.
regulatory_mapping.py Verbatim-cited regulatory clause data per regime.
manifest.py           COMPLIANCE_MANIFEST.{md,json} builder + SHA chain.
verify_output.py      Independent PHI scanner (separate tag list).
anonymize.py          Public API surface.
```

### Python API

```python
from anonymize import anonymize_path, AnonymizationConfig

cfg = AnonymizationConfig(salt="cohort-A", continue_on_error=True)
summary = anonymize_path("/data/study", "/data/anon", config=cfg)

print(summary.files_processed, summary.audit_sha256)
for record in summary.records:
    print(record.source, len(record.tags_modified))
```

---

## Comparison with other tools

| Feature | dcm-anon | pydicom example script | dcm4che `deidentify` | dicom-anon (chop-dbhi) | Kitware/dicom-anonymizer |
|---|---|---|---|---|---|
| PS3.15 Table E.1-1 coverage | 125 tags + range masks, 2024 ed. | ~10 tags (example only) | Full (Java, complex) | Partial (varies) | Full |
| UID consistency across files | Yes | No | Yes | Partial | Yes |
| `file_meta` UID consistency | Yes | No | Yes | Unknown | Unknown |
| Sequence (SQ) recursion | Yes | No | Yes | No | Yes |
| Deterministic UID remapping | `--salt` | No | Config hash | No | No |
| Audit log with action codes | JSON, per-tag | No | XML logs | No | No |
| **Verbatim-cited compliance manifest** | **Yes (GDPR / HIPAA / AI Act)** | No | No | No | No |
| Independent output verification | Yes | No | No | No | No |
| Burned-in PHI detection | Flag + optional OCR | No | Flag only | No | No |
| Zero runtime dependencies | `pydicom` only | `pydicom` | Java 11+ | Yes | Yes |
| License | MIT | BSD | MPL 1.1 | Apache 2.0 | BSD-3-Clause |

---

## Limitations (what this tool does NOT do)

These are documented gaps, not hidden bugs:

- **Pixel-level OCR redaction.** If `BurnedInAnnotation = YES`, the audit
  log warns you. Pixel data is NOT modified by default. Pixel OCR is on
  the hosted roadmap.
- **Private tag scrubbing.** The standard says remove private attributes
  (`X`), but identifying which private groups contain PHI requires
  vendor-specific knowledge. This tool does not claim to handle private
  tags. See `SECURITY.md`.
- **DICOM SR / Structured Report content scanning.** Free-text inside SR
  sequences may contain PHI; the tool does not parse SR semantics.
- **DICOMDIR update.** Directory records in a DICOMDIR are not updated
  after UID remapping. Regenerate the DICOMDIR after anonymization.
- **Big-endian transfer syntaxes.** Rare in practice; not tested.

---

## Tests

```bash
pytest -v --cov=. --cov-report=term-missing
```

132 tests, coverage ≥80% gated in CI. Suite covers: per-tag PHI removal,
UID consistency, file-meta SOP UID parity, sequence recursion, deterministic
remap, multi-frame DICOM, burned-in flag detection, batch directory
processing, cross-file UID linkage, manifest SHA-chain integrity, manifest
tamper detection, independent verification correctness.

---

## Examples

```bash
# 1. Download public test DICOMs (pydicom test data, no real PHI)
python examples/download_test_dicom.py

# 2. Run the annotated example (before/after comparison + audit log)
python examples/run_example.py

# 3. Same with deterministic UIDs
python examples/run_example.py --salt my-project-2024
```

A hosted interactive demo runs at [huggingface.co/spaces/cpereiro/dcm-anon](https://huggingface.co/spaces/cpereiro/dcm-anon)
(synthetic DICOM only — please do not upload real patient data to the public demo).

---

## Citing

If you use this tool in a publication, please cite via the Zenodo DOI:

```bibtex
@software{dcm_anon,
  author       = {Pereiro García, César},
  title        = {{dcm-anon: DICOM anonymizer with verbatim-cited compliance manifest}},
  year         = {2026},
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.20267652},
  url          = {https://github.com/Ces107/dcm-anon},
}
```

---

## Hosted service — preparing

A managed version with batch processing, S3-source support, private-tag
handling, SR scanning, SLA, and retained audit logs is in preparation for
single-team research labs.

→ **[Reserve early access at the landing page](https://ces107.github.io/dcm-anon/#early-access)** — or email **[plusultra.dev@proton.me](mailto:plusultra.dev@proton.me?subject=dcm-anon%20early%20access)** directly. Every email gets a personal reply within a week.

---

## License

MIT.
