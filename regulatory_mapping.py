"""Regulatory clause mapping for DICOM anonymization actions.

Pure data — no behaviour. Maps each PS3.15 Basic Profile action code
(X / Z / U / D) to the specific regulatory clauses it implements under
the EU AI Act, HIPAA Safe Harbor, and GDPR, plus the authoritative
post-2024 guidance that interprets those clauses.

The citations in this module were verified verbatim against the
canonical source (EUR-Lex, eCFR via Cornell LII, gdpr-info.eu) on
2026-05-13. Every clause text quoted in a clause's ``summary`` field
is a paraphrase suitable for human review; the ``url`` points to the
canonical source for verbatim verification.

The wedge that makes this module valuable is correctness, not
volume: a compliance officer reading the manifest must be able to
open the regulation in another tab, find the cited paragraph, and
confirm the mapping holds. Sloppy citations destroy the moat.

This module is NOT legal advice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class RegulatoryClause:
    """One regulatory clause cited by an action code."""

    regime: str
    citation: str
    short_title: str
    summary: str
    url: str


@dataclass(frozen=True)
class GuidanceReference:
    """Post-2024 authoritative guidance interpreting one or more clauses.

    Distinguished from ``RegulatoryClause``: a clause is binding regulation;
    a guidance reference is interpretation that regulators apply (EDPB,
    MDCG, NIST, ICO, etc.). The manifest cites both so a reader can verify
    we are tracking current state-of-the-art interpretation, not just the
    raw text of the regulation.
    """

    regime: str
    publisher: str
    title: str
    published: str
    url: str
    relevance: str


@dataclass(frozen=True)
class RegimeMetadata:
    """Top-level metadata for a regulatory regime."""

    code: str
    full_name: str
    jurisdiction: str
    enforcement_date: str
    canonical_url: str


# ---------------------------------------------------------------------------
# Regime registry
# ---------------------------------------------------------------------------

EU_AI_ACT: Final = RegimeMetadata(
    code="eu-ai-act",
    full_name="Regulation (EU) 2024/1689 — Artificial Intelligence Act",
    jurisdiction="European Union",
    # Currently binding date for standalone high-risk AI (Annex III) under
    # the AI Act as enacted: 2026-08-02. A provisional political agreement
    # ("Digital Omnibus on AI", Council + Parliament negotiators, 7 May 2026)
    # proposes deferral to 2027-12-02 (standalone Annex III) and 2028-08-02
    # (AI embedded in MDR/IVDR Class IIb/III). As of 2026-05-16 the Omnibus
    # has NOT been formally adopted and NOT been published in the OJEU —
    # the 2026-08-02 date therefore remains the legally binding one.
    enforcement_date="2026-08-02",
    canonical_url="https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
)

HIPAA: Final = RegimeMetadata(
    code="hipaa",
    full_name="HIPAA Privacy Rule — 45 CFR Part 164, Subpart E",
    jurisdiction="United States",
    enforcement_date="2003-04-14",
    canonical_url="https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164",
)

GDPR: Final = RegimeMetadata(
    code="gdpr",
    full_name="Regulation (EU) 2016/679 — General Data Protection Regulation",
    jurisdiction="European Union",
    enforcement_date="2018-05-25",
    canonical_url="https://eur-lex.europa.eu/eli/reg/2016/679/oj",
)

REGIMES: Final[dict[str, RegimeMetadata]] = {
    EU_AI_ACT.code: EU_AI_ACT,
    HIPAA.code: HIPAA,
    GDPR.code: GDPR,
}


# ---------------------------------------------------------------------------
# Per-action clause mapping
#
# Citations were re-verified 2026-05-13 against EUR-Lex, eCFR, and
# gdpr-info.eu. Key correction: AI Act Art. 10(5) is NOT cited for
# general de-identification because that paragraph is the narrow
# bias-detection exception. The correct AI Act hooks for general de-id
# are Art. 10(1)-10(3) for data governance and Art. 12 + Art. 18 for
# the audit trail / technical file retention.
# ---------------------------------------------------------------------------

_ACTION_X_CLAUSES: Final = [
    RegulatoryClause(
        regime=EU_AI_ACT.code,
        citation="Art. 10(2)(b) + 10(2)(c) + 10(3)",
        short_title="Data governance — collection, cleaning, representativeness",
        summary=(
            "Art. 10(2)(b) requires documenting 'the original purpose of the "
            "data collection'; Art. 10(2)(c) lists 'cleaning, updating, "
            "enrichment and aggregation' as data-preparation operations to "
            "be documented; Art. 10(3) mandates training sets be 'relevant, "
            "sufficiently representative, and to the best extent possible, "
            "free of errors'. Tag removal implements the cleaning step and "
            "the manifest documents which tags were removed and why."
        ),
        url="https://artificialintelligenceact.eu/article/10/",
    ),
    RegulatoryClause(
        regime=HIPAA.code,
        citation="45 CFR 164.514(b)(2)(i)",
        short_title="Safe Harbor — removal of 18 identifier categories",
        summary=(
            "Safe Harbor requires that all 18 listed identifier categories "
            "(A) Names; (B) Geographic subdivisions smaller than a State; "
            "(C) Dates more specific than year; … (R) Any other unique "
            "identifying number, characteristic, or code) be 'removed'. "
            "PS3.15 action X implements the removal step for the DICOM "
            "tags that map to these categories (PatientName→A, "
            "InstitutionAddress→B, StudyDate→C, DeviceSerialNumber→R, etc.)."
        ),
        url="https://www.ecfr.gov/current/title-45/section-164.514",
    ),
    RegulatoryClause(
        regime=GDPR.code,
        citation="Art. 5(1)(c)",
        short_title="Data minimisation",
        summary=(
            "Personal data shall be 'adequate, relevant and limited to "
            "what is necessary in relation to the purposes for which they "
            "are processed (data minimisation)'. Removing PHI tags not "
            "needed for the downstream AI / research purpose implements "
            "this principle directly."
        ),
        url="https://gdpr-info.eu/art-5-gdpr/",
    ),
]

_ACTION_Z_CLAUSES: Final = [
    RegulatoryClause(
        regime=EU_AI_ACT.code,
        citation="Art. 10(1) (data governance) — applied via GDPR Art. 32",
        short_title="Appropriate data governance",
        summary=(
            "Art. 10(1) requires 'data governance and management practices "
            "appropriate for the intended purpose'. For general de-"
            "identification (outside the bias-detection exception of "
            "Art. 10(5)), the AI Act delegates the specific technical "
            "safeguard requirement to GDPR Art. 32(1)(a). Zero-replacement "
            "neutralises an identifier-bearing free-text or coded field."
        ),
        url="https://artificialintelligenceact.eu/article/10/",
    ),
    RegulatoryClause(
        regime=HIPAA.code,
        citation="45 CFR 164.514(b)(2)(i)",
        short_title="Safe Harbor — identifier neutralisation",
        summary=(
            "Where outright removal would break DICOM schema constraints "
            "(e.g. a Type 2 element that must be present), neutralising "
            "the value to empty satisfies the Safe Harbor identifier-"
            "removal requirement provided the residual value carries no "
            "identifying information."
        ),
        url="https://www.ecfr.gov/current/title-45/section-164.514",
    ),
    RegulatoryClause(
        regime=GDPR.code,
        citation="Art. 32(1)(a) + Art. 4(5)",
        short_title="Pseudonymisation as a technical safeguard",
        summary=(
            "Art. 32(1)(a) lists pseudonymisation as an appropriate "
            "technical measure; Art. 4(5) defines pseudonymisation as "
            "processing such that data 'can no longer be attributed to "
            "a specific data subject without the use of additional "
            "information ... kept separately'. Z-action produces a non-"
            "identifying placeholder."
        ),
        url="https://gdpr-info.eu/art-32-gdpr/",
    ),
]

_ACTION_U_CLAUSES: Final = [
    RegulatoryClause(
        regime=EU_AI_ACT.code,
        citation="Art. 10(1) (data governance) — applied via GDPR Art. 4(5)",
        short_title="Pseudonymous identifier remapping",
        summary=(
            "Art. 10(1) requires appropriate data governance. For UID "
            "remapping the operative technical definition comes from "
            "GDPR Art. 4(5): the new UID enables longitudinal linkage "
            "without exposing the original identifier; the salt (kept "
            "separately) is the 'additional information' that GDPR "
            "Art. 4(5) requires to be controlled."
        ),
        url="https://artificialintelligenceact.eu/article/10/",
    ),
    RegulatoryClause(
        regime=HIPAA.code,
        citation="45 CFR 164.514(c)",
        short_title="Re-identification code under HIPAA",
        summary=(
            "Verbatim: 'A covered entity may assign a code … to allow "
            "information de-identified under this section to be re-"
            "identified … provided that the code … is not derived from "
            "or related to information about the individual and is not "
            "otherwise capable of being translated so as to identify the "
            "individual; and the covered entity does not use or disclose "
            "the code or other means of record identification for any "
            "other purpose, and does not disclose the mechanism for re-"
            "identification.' Salted-hash UID remap with a withheld salt "
            "satisfies the derivation prohibition exactly."
        ),
        url="https://www.ecfr.gov/current/title-45/section-164.514",
    ),
    RegulatoryClause(
        regime=GDPR.code,
        citation="Art. 4(5)",
        short_title="Pseudonymisation — referential integrity preserved",
        summary=(
            "Pseudonymisation 'in such a manner that the personal data "
            "can no longer be attributed to a specific data subject "
            "without the use of additional information, provided that "
            "such additional information is kept separately and is "
            "subject to technical and organisational measures'. UID "
            "remapping with a separately-held salt is the textbook "
            "implementation; EDPB Guidelines 01/2025 specify that the "
            "salt / mapping table must live in a separate 'pseudonymisation "
            "domain' with access controls."
        ),
        url="https://gdpr-info.eu/art-4-gdpr/",
    ),
]

_ACTION_D_CLAUSES: Final = [
    RegulatoryClause(
        regime=EU_AI_ACT.code,
        citation="Art. 10(1) (data governance) — applied via GDPR Art. 32(1)(a)",
        short_title="Dummy placeholder — schema-preserving neutralisation",
        summary=(
            "Where DICOM Value Representation forbids an empty value, a "
            "fixed clinically-plausible-but-non-identifying dummy (e.g. "
            "PatientBirthDate=19000101) preserves parser compatibility "
            "while neutralising the identifier. Justified under AI Act "
            "Art. 10(1) data governance and GDPR Art. 32(1)(a) technical "
            "measures."
        ),
        url="https://artificialintelligenceact.eu/article/10/",
    ),
    RegulatoryClause(
        regime=HIPAA.code,
        citation="45 CFR 164.514(b)(2)(i)",
        short_title="Safe Harbor — non-identifying schema-preserving substitute",
        summary=(
            "The substituted dummy value must not itself be identifying. "
            "Tool emits canonical placeholders (ANON for names, 19000101 "
            "for dates) chosen because they carry no per-subject "
            "information and are documented in the audit log."
        ),
        url="https://www.ecfr.gov/current/title-45/section-164.514",
    ),
    RegulatoryClause(
        regime=GDPR.code,
        citation="Art. 32(1)(a) + Recital 26",
        short_title="Technical safeguard — irreversible substitute",
        summary=(
            "Art. 32(1)(a) requires appropriate technical safeguards. "
            "Recital 26's 'means reasonably likely to be used' test: when "
            "the dummy is sufficiently decoupled from the original value "
            "and no separately-held lookup permits reversal, the "
            "substituted data is no longer personal data."
        ),
        url="https://gdpr-info.eu/art-32-gdpr/",
    ),
]

ACTION_CLAUSES: Final[dict[str, list[RegulatoryClause]]] = {
    "X": _ACTION_X_CLAUSES,
    "Z": _ACTION_Z_CLAUSES,
    "U": _ACTION_U_CLAUSES,
    "D": _ACTION_D_CLAUSES,
}


# ---------------------------------------------------------------------------
# Cross-cutting audit-trail clauses
#
# These apply unconditionally (NOT under the Art. 10(5) bias-detection
# exception). They are the correct hooks for the SIGNED audit log.
# ---------------------------------------------------------------------------

AUDIT_TRAIL_CLAUSES: Final[dict[str, list[RegulatoryClause]]] = {
    EU_AI_ACT.code: [
        RegulatoryClause(
            regime=EU_AI_ACT.code,
            citation="Art. 11 + Annex IV — technical documentation",
            short_title="Technical documentation of training-data preparation",
            summary=(
                "Art. 11 requires high-risk AI system providers to draw "
                "up technical documentation as set out in Annex IV before "
                "the system is placed on the market and to keep it up to "
                "date. Annex IV Section 2(d) calls for documentation of "
                "the data-preparation operations applied to training, "
                "validation and testing data — exactly what the signed "
                "de-identification audit log evidences. This is the "
                "primary hook for the audit trail under the AI Act."
            ),
            url="https://artificialintelligenceact.eu/article/11/",
        ),
        RegulatoryClause(
            regime=EU_AI_ACT.code,
            citation="Art. 18 — documentation retention",
            short_title="10-year technical-file retention",
            summary=(
                "The technical documentation and quality management "
                "system documents shall be kept at the disposal of the "
                "national competent authorities for a period of 10 years "
                "after the AI system has been placed on the market. The "
                "manifest is part of that documentation."
            ),
            url="https://artificialintelligenceact.eu/article/18/",
        ),
        RegulatoryClause(
            regime=EU_AI_ACT.code,
            citation="Art. 12 — record-keeping (secondary, pre-deployment)",
            short_title="Logging — secondary citation, lifecycle alignment",
            summary=(
                "Art. 12 governs runtime event logging in a deployed "
                "high-risk AI system over its operational lifetime "
                "(inference events). The signed de-identification audit "
                "log is a PRE-DEPLOYMENT data-preparation artifact, not a "
                "runtime event log per Art. 12(1)(a); it is cited here as "
                "a secondary alignment to the lifecycle-logging principle "
                "the AI Act establishes. The primary documentation hooks "
                "are Art. 11 (above) and Art. 18 (retention)."
            ),
            url="https://artificialintelligenceact.eu/article/12/",
        ),
    ],
    HIPAA.code: [
        RegulatoryClause(
            regime=HIPAA.code,
            citation="45 CFR 164.312(b)",
            short_title="Audit controls",
            summary=(
                "Implement hardware, software, and/or procedural "
                "mechanisms that record and examine activity in "
                "information systems that contain or use electronic "
                "protected health information. The tamper-evident audit "
                "chain implements this control for the de-identification "
                "step."
            ),
            url="https://www.ecfr.gov/current/title-45/section-164.312",
        ),
    ],
    GDPR.code: [
        RegulatoryClause(
            regime=GDPR.code,
            citation="Art. 30",
            short_title="Records of processing activities",
            summary=(
                "Each controller shall maintain a record of processing "
                "activities under its responsibility, including "
                "'where possible, the general description of the "
                "technical and organisational security measures' "
                "(Art. 30(1)(g)). The manifest is the per-batch "
                "processing record for the de-identification operation."
            ),
            url="https://gdpr-info.eu/art-30-gdpr/",
        ),
        RegulatoryClause(
            regime=GDPR.code,
            citation="Art. 5(2)",
            short_title="Accountability",
            summary=(
                "The controller shall be 'responsible for, and be able "
                "to demonstrate compliance with' the principles in "
                "Art. 5(1). The signed manifest is the demonstration "
                "artifact for the pseudonymisation and data "
                "minimisation principles."
            ),
            url="https://gdpr-info.eu/art-5-gdpr/",
        ),
    ],
}


# ---------------------------------------------------------------------------
# Authoritative guidance — post-2024 interpretive documents
#
# These do not REPLACE the clauses above; they are the state-of-the-art
# INTERPRETATION that regulators (EDPB, MDCG, NIST, ICO) apply when
# auditing. Citing them proves the tool tracks current practice.
# ---------------------------------------------------------------------------

AUTHORITATIVE_GUIDANCE: Final[dict[str, list[GuidanceReference]]] = {
    EU_AI_ACT.code: [
        GuidanceReference(
            regime=EU_AI_ACT.code,
            publisher="MDCG / European Commission",
            title="MDCG 2025-6 / AIB 2025-1 — Interplay between MDR/IVDR and the AI Act",
            published="2025-06",
            url=(
                "https://health.ec.europa.eu/document/download/"
                "b78a17d7-e3cd-4943-851d-e02a2f22bbb4_en?filename="
                "mdcg_2025-6_en.pdf"
            ),
            relevance=(
                "First official guidance linking AI Act Art. 10 data "
                "governance obligations to MDR Annex II technical file. "
                "Allows a single technical file to cover both regimes for "
                "SaMD that trains on patient imaging data."
            ),
        ),
        GuidanceReference(
            regime=EU_AI_ACT.code,
            publisher="European Commission — AI Office",
            title="General-Purpose AI Code of Practice (Final) — context only",
            published="2025-07-10",
            url="https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai",
            relevance=(
                "Context only — applies to providers of general-purpose AI "
                "models under AI Act Art. 53(1)(d). Narrow-domain SaMD (e.g. "
                "a dermatology classifier trained on DICOM) is high-risk "
                "Annex III, NOT a GPAI provider, so the GPAI Training Data "
                "Disclosure Template does not apply by default. Cite the "
                "Code only if your system independently qualifies as a GPAI "
                "model under AI Act Art. 3(63)."
            ),
        ),
    ],
    HIPAA.code: [
        GuidanceReference(
            regime=HIPAA.code,
            publisher="NIST",
            title="SP 800-66 Revision 2 — Implementing the HIPAA Security Rule",
            published="2024-02",
            url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-66r2.pdf",
            relevance=(
                "Current authoritative implementation guide for 45 CFR "
                "164.312(b). §5 sample activities explicitly cover "
                "automated de-identification tools — the manifest "
                "format reflects 800-66r2 recommendations."
            ),
        ),
        GuidanceReference(
            regime=HIPAA.code,
            publisher="HHS Office for Civil Rights",
            title="Guidance Regarding Methods for De-identification of Protected Health Information",
            published="2012-11-26",
            url=(
                "https://www.hhs.gov/sites/default/files/ocr/privacy/hipaa/"
                "understanding/coveredentities/De-identification/"
                "hhs_deid_guidance.pdf"
            ),
            relevance=(
                "Canonical OCR guidance interpreting 164.514(b). Still "
                "the reference document for what counts as Safe Harbor "
                "removal vs. inadequate neutralisation."
            ),
        ),
    ],
    GDPR.code: [
        GuidanceReference(
            regime=GDPR.code,
            publisher="European Data Protection Board",
            title=(
                "Guidelines 01/2025 on Pseudonymisation "
                "(v.1.0, draft for public consultation; "
                "consultation closed 14 March 2025, final version pending)"
            ),
            published="2025-01-17",
            url=(
                "https://www.edpb.europa.eu/our-work-tools/documents/"
                "public-consultations/2025/guidelines-012025-"
                "pseudonymisation_en"
            ),
            relevance=(
                "Defines the 'pseudonymisation domain': the salt / mapping "
                "table must be held in a separate environment with "
                "documented access control. This is the state-of-the-art "
                "interpretation EU DPAs apply to Art. 4(5)."
            ),
        ),
        GuidanceReference(
            regime=GDPR.code,
            publisher="ENISA",
            title="Deploying Pseudonymisation Techniques (Health Sector)",
            published="2022-03-24",
            url=(
                "https://www.enisa.europa.eu/publications/"
                "deploying-pseudonymisation-techniques"
            ),
            relevance=(
                "Most recent ENISA technical guidance on pseudonymisation "
                "for health data; the reference document EU DPAs cite "
                "when evaluating technical adequacy."
            ),
        ),
        GuidanceReference(
            regime=GDPR.code,
            publisher="Gobierno de España (CCN-CERT)",
            title=(
                "Esquema Nacional de Seguridad — Real Decreto 311/2022, "
                "Nivel ALTO (CAT-ALTA) technical measures"
            ),
            published="2022-05-04",
            url="https://www.boe.es/eli/es/rd/2022/05/03/311/con",
            relevance=(
                "Spanish national security framework mandatory for "
                "public-sector data controllers (incl. SNS public hospitals) "
                "handling Category 3 / 'datos de salud' personal data. ENS "
                "Nivel ALTO requires audit trails, pseudonymisation, and "
                "documented technical measures; the manifest and signed "
                "audit log satisfy ENS CAT-ALTA technical security measures "
                "[op.exp.8 registro de actividad, mp.info.3 cifrado, "
                "mp.info.6 limpieza de documentos] in combination with the "
                "controller's organisational measures. This is the relevant "
                "domestic-law backstop for any AEPD-supervised Spanish "
                "public hospital deployment."
            ),
        ),
    ],
}


# ---------------------------------------------------------------------------
# Post-Cegedim defensive — re-identification risk framing
# ---------------------------------------------------------------------------

# CNIL decision SAN-2024-013 (Cegedim Santé, €800,000, 5 September 2024)
# sanctioned Cegedim for (1) processing health data without the CNIL
# authorisation required by Art. 66 of the French Data Protection Act,
# and (2) unlawful processing under GDPR Art. 5(1)(a), because Cegedim
# relied on a claimed anonymisation to bypass the need for an Art. 9
# lawful basis when the data were only pseudonymous. The fine did not
# punish a documentation gap about output classification per se; it
# punished the downstream consequence — absence of a lawful basis — that
# the false anonymisation claim enabled. The PSEUDONYMOUS_RISK_STATEMENT
# below addresses the upstream factual gap (correct classification of the
# output); the GDPR_ART9_DISCLOSURE further down addresses the downstream
# legal gap (lawful-basis obligation that remains with the controller).

PSEUDONYMOUS_RISK_STATEMENT: Final = (
    "Output classification: PSEUDONYMOUS (not anonymous) under GDPR "
    "Art. 4(5). DICOM tags carrying direct identifiers (HIPAA Safe Harbor "
    "18 categories) are removed (action X), neutralised (action Z), or "
    "remapped (action U for UIDs, action D for schema-bound dummies). "
    "UID remapping uses a deterministic salted hash; the salt is held "
    "separately by the controller and is not embedded in any output file. "
    "Re-identification is possible only by combining the output with the "
    "withheld salt, in line with GDPR Art. 4(5) and EDPB Guidelines "
    "01/2025 (pseudonymisation-domain model). For Safe Harbor compliance, "
    "no persistent linking identifier remains in the output dataset that "
    "is derived from individual-level attributes (45 CFR 164.514(c)(1))."
)


# HIPAA distinguishes two de-identification methods (§164.514(b)):
# (1) Expert Determination — requires "a person with appropriate knowledge
#     of and experience with generally accepted statistical and scientific
#     principles" to determine that re-identification risk is very small.
# (2) Safe Harbor — mechanical removal of 18 specified identifier
#     categories. No expert sign-off required.
#
# dcm-anon implements Safe Harbor only. Expert Determination requires a
# human statistician's signature on a risk assessment that this tool
# cannot produce. Surfacing this distinction explicitly in the manifest
# prevents a covered entity from mistakenly relying on the tool output
# as Expert Determination evidence.
EXPERT_DETERMINATION_DISCLAIMER: Final = (
    "HIPAA method: SAFE HARBOR ONLY (45 CFR 164.514(b)(2)). This tool "
    "implements the mechanical Safe Harbor method — removal of the 18 "
    "identifier categories listed in §164.514(b)(2)(i). It does NOT "
    "constitute Expert Determination under §164.514(b)(1), which requires "
    "a qualified human statistician to apply generally accepted "
    "statistical principles and determine that the risk of re-"
    "identification is very small (per HHS OCR de-identification guidance, "
    "2012). If your use case requires Expert Determination — e.g. retaining "
    "tags otherwise removed by Safe Harbor — engage a qualified expert and "
    "attach their signed determination separately."
)


# GDPR enforcement against health data processors uniformly begins with
# "what is your Art. 9(2) lawful basis for processing special-category
# personal data?" — not with "is your pseudonymisation technique
# adequate?" The CNIL/Cegedim Santé decision SAN-2024-013 turned on
# exactly this question: the false anonymisation claim removed Cegedim's
# only argument for processing without an Art. 9 ground. The manifest
# cites Art. 4(5) + Art. 32(1)(a), which defend technique adequacy but
# are silent on the threshold lawful-basis question. Surfacing the Art. 9
# question explicitly — and disclosing that the tool does NOT establish
# the lawful basis (the controller must) — closes the gap a DPA auditor
# would otherwise exploit first.
GDPR_ART9_DISCLOSURE: Final = (
    "GDPR Art. 9 lawful basis: NOT ESTABLISHED BY THIS TOOL. Article 9(1) "
    "prohibits processing of special categories of personal data (incl. "
    "health) unless one of the Art. 9(2) grounds applies (e.g. (a) "
    "explicit consent, (i) public health, (j) scientific research with "
    "Art. 89(1) safeguards). The data controller must independently "
    "establish and document the Art. 9(2) ground BEFORE processing. The "
    "compliance manifest covers the Art. 4(5) pseudonymisation technique "
    "and the Art. 5/30/32 governance obligations applied AFTER lawfulness "
    "is established. It does not substitute for the Art. 9(2) "
    "determination."
)


# Regulatory urgency framing: surface the live state of AI Act enforcement.
# Under the AI Act as enacted (Regulation (EU) 2024/1689), high-risk AI
# obligations under Annex III apply from 2026-08-02 and that date remains
# binding law today. A provisional political agreement ("Digital Omnibus
# on AI", Council-Parliament negotiators, 7 May 2026) would defer Annex III
# obligations to 2027-12-02 and AI embedded in MDR/IVDR Class IIb/III to
# 2028-08-02, but formal adoption and OJEU publication are pending as of
# 2026-05-16. The manifest exposes both the live binding date and the
# pending deferral so a reader cannot accuse the tool either of pretending
# to a deadline that has shifted, or of treating an unadopted political
# agreement as enforceable law.
AI_ACT_DEADLINE_CONTEXT: Final = (
    "EU AI Act enforcement (as of 2026-05-16): under Regulation (EU) "
    "2024/1689 as enacted, high-risk AI obligations for Annex III "
    "standalone systems apply from 2026-08-02 and that date remains "
    "legally binding. A provisional political agreement (\"Digital "
    "Omnibus on AI\", Council-Parliament negotiators, 7 May 2026) "
    "proposes deferral to 2027-12-02 (Annex III standalone) and "
    "2028-08-02 (AI embedded in MDR/IVDR Class IIb/III medical devices); "
    "formal adoption and OJEU publication are still pending. Verify "
    "the live status before relying on the deferred dates. The "
    "manifest's Art. 10 citations are valid under both the current and "
    "the proposed timelines."
)


DISCLAIMER: Final = (
    "ENGINEERING ARTIFACT — NOT LEGAL ADVICE. This document is generated by "
    "an open-source tool (dcm-anon). It cites regulatory clauses verbatim "
    "to facilitate review by your Quality Management System (QMS) and "
    "legal counsel. The tool does not certify compliance, does not act as "
    "a notified body, and does not relieve the data controller of "
    "independent obligations under the cited regulations. Verify all "
    "citations against the canonical source before submission to any "
    "regulator or auditor. Citations re-verified 2026-05-13 against "
    "EUR-Lex, eCFR, and gdpr-info.eu."
)


def get_regime(code: str) -> RegimeMetadata:
    """Resolve a regime code (case-insensitive) to its metadata."""
    key = code.strip().lower()
    if key not in REGIMES:
        raise ValueError(
            f"Unknown regulatory regime {code!r}. "
            f"Available: {sorted(REGIMES.keys())}"
        )
    return REGIMES[key]


def clauses_for_action(action_code: str, regime: str) -> list[RegulatoryClause]:
    """Return the clauses citing *action_code* under *regime*."""
    if action_code not in ACTION_CLAUSES:
        raise KeyError(
            f"Unknown action code {action_code!r}. "
            f"Expected one of {sorted(ACTION_CLAUSES.keys())}"
        )
    regime_meta = get_regime(regime)
    return [c for c in ACTION_CLAUSES[action_code] if c.regime == regime_meta.code]


def audit_trail_clauses_for(regime: str) -> list[RegulatoryClause]:
    """Return the cross-cutting audit-log clauses for *regime*."""
    regime_meta = get_regime(regime)
    return AUDIT_TRAIL_CLAUSES[regime_meta.code]


def guidance_for(regime: str) -> list[GuidanceReference]:
    """Return the authoritative guidance documents for *regime*."""
    regime_meta = get_regime(regime)
    return AUTHORITATIVE_GUIDANCE.get(regime_meta.code, [])


__all__ = [
    "ACTION_CLAUSES",
    "AI_ACT_DEADLINE_CONTEXT",
    "AUDIT_TRAIL_CLAUSES",
    "AUTHORITATIVE_GUIDANCE",
    "DISCLAIMER",
    "EU_AI_ACT",
    "EXPERT_DETERMINATION_DISCLAIMER",
    "GDPR",
    "GDPR_ART9_DISCLOSURE",
    "HIPAA",
    "PSEUDONYMOUS_RISK_STATEMENT",
    "REGIMES",
    "GuidanceReference",
    "RegimeMetadata",
    "RegulatoryClause",
    "audit_trail_clauses_for",
    "clauses_for_action",
    "get_regime",
    "guidance_for",
]
