"""Command-line interface for dcm-anon.

Pure I/O glue: turn argv into an :class:`AnonymizationConfig`, run
:func:`anonymize_path`, write the audit + report + (optional) compliance
manifest files, return an exit code.

Two top-level modes:

* **Anonymize mode** (default): `dcm-anon <src> <dst> [...]`. Anonymizes
  inputs, emits the audit log, and -- when ``--manifest-mode`` is set --
  emits a compliance manifest plus optional independent output
  verification.
* **Verify mode**: `dcm-anon --verify-manifest M.json --audit A.json`.
  Re-computes the manifest SHA chain against the audit and reports
  PASS / FAIL without touching DICOM data.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from audit import render_markdown_report
from manifest import (
    build_manifest,
    load_audit_dict,
    load_manifest_dict,
    render_markdown,
    supported_regimes,
    verify_manifest,
)
from pipeline import (
    AnonymizationConfig,
    AuditSummary,
    ProgressCallback,
    anonymize_path,
    parse_keep_tag,
)
from verify_output import VerificationResult, scan_outputs

LOG = logging.getLogger("dcmanon")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_arg_parser(version: str) -> argparse.ArgumentParser:
    """Build the argparse parser. Public so tests can introspect choices."""
    parser = argparse.ArgumentParser(
        prog="anonymize",
        description=(
            "DICOM anonymizer — PS3.15 Basic Application Level Confidentiality "
            "Profile, with optional compliance manifest."
        ),
        epilog="See README.md for tags, regulatory mapping, and known limits.",
    )
    _add_anonymize_args(parser)
    _add_manifest_args(parser)
    _add_verify_args(parser)
    parser.add_argument("--quiet", action="store_true", help="Suppress info logging")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", action="version", version=f"dcm-anon {version}")
    return parser


def _add_anonymize_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("src", type=Path, nargs="?",
                        help="Input .dcm file or directory (omit with --verify-manifest)")
    parser.add_argument("dst", type=Path, nargs="?",
                        help="Output directory (omit with --verify-manifest)")
    parser.add_argument("--audit-log", type=Path, default=None,
                        help="Audit JSON path (default: <dst>/anonymization_audit.json)")
    parser.add_argument("--report-md", type=Path, default=None,
                        help="Optional human-readable Markdown summary path")
    parser.add_argument("--salt", type=str, default=None,
                        help="Deterministic-UID salt (same salt + same source = same UIDs)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process files in memory and emit audit, but do NOT write outputs")
    parser.add_argument("--continue-on-error", action="store_true",
                        help="Skip malformed DICOMs instead of aborting")
    parser.add_argument("--keep", action="append", default=[], metavar="GGGG,EEEE",
                        help="Whitelist a tag (hex group,element); repeatable")


def _add_manifest_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--manifest-mode",
        choices=supported_regimes(),
        default=None,
        help=(
            "Emit a compliance manifest under the chosen regulatory regime "
            "(JSON + Markdown). When set, the manifest SHA-256 chain extends "
            "the audit SHA-256."
        ),
    )
    parser.add_argument(
        "--manifest-json",
        type=Path,
        default=None,
        help="Manifest JSON path (default: <dst>/compliance_manifest.json)",
    )
    parser.add_argument(
        "--manifest-md",
        type=Path,
        default=None,
        help="Manifest Markdown path (default: <dst>/COMPLIANCE_MANIFEST.md)",
    )
    parser.add_argument(
        "--verify-output",
        action="store_true",
        help=(
            "Run independent post-anonymization PHI residual scan on output "
            "DICOMs and embed the result in the manifest. Defeats the self-"
            "attestation problem."
        ),
    )
    parser.add_argument(
        "--verify-output-sample",
        type=int,
        default=10,
        metavar="N",
        help="Max files to include in the independent verification sample (default 10)",
    )
    parser.add_argument(
        "--verify-output-pixel-ocr",
        action="store_true",
        help=(
            "Additionally run pytesseract OCR on pixel data of sampled files "
            "(requires the tesseract binary; silently degrades if unavailable)"
        ),
    )


def _add_verify_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--verify-manifest",
        type=Path,
        default=None,
        metavar="MANIFEST.json",
        help=(
            "Switch to verify mode: re-compute the manifest SHA chain against "
            "the supplied audit. With this flag, src/dst are not required."
        ),
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=None,
        metavar="AUDIT.json",
        help="Audit log to verify against (required with --verify-manifest)",
    )


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------

def _resolve_log_level(*, verbose: bool, quiet: bool) -> int:
    if verbose:
        return logging.DEBUG
    if quiet:
        return logging.WARNING
    return logging.INFO


def _build_keep_tags(keep_specs: list[str]) -> frozenset[tuple[int, int]]:
    return frozenset(parse_keep_tag(s) for s in keep_specs) if keep_specs else frozenset()


def _count_targets(src: Path) -> int:
    return 1 if src.is_file() else len(list(src.rglob("*.dcm")))


def _build_progress_cb(total: int, *, quiet: bool) -> ProgressCallback | None:
    if quiet or total <= 1:
        return None
    try:
        from tqdm import tqdm
    except ImportError:
        def stderr_cb(index: int, ttl: int, path: Path) -> None:
            print(f"  [{index}/{ttl}] {path.name}", file=sys.stderr)
        return stderr_cb

    bar = tqdm(total=total, unit="file", desc="anonymizing")

    def tqdm_cb(index: int, ttl: int, path: Path) -> None:
        del index, ttl, path
        bar.update(1)

    return tqdm_cb


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Verify-manifest sub-mode
# ---------------------------------------------------------------------------

def _run_verify_mode(args: argparse.Namespace) -> int:
    if args.audit is None:
        print(
            "error: --verify-manifest requires --audit <path>",
            file=sys.stderr,
        )
        return 2
    manifest_dict = load_manifest_dict(str(args.verify_manifest))
    audit_dict = load_audit_dict(str(args.audit))
    ok, reasons = verify_manifest(manifest_dict, audit_dict)
    if ok:
        print(f"PASS: manifest {args.verify_manifest} matches audit {args.audit}")
        return 0
    print(f"FAIL: manifest {args.verify_manifest} does NOT match audit {args.audit}")
    for reason in reasons:
        print(f"  - {reason}")
    return 1


# ---------------------------------------------------------------------------
# Anonymize sub-mode
# ---------------------------------------------------------------------------

def _validate_anonymize_args(args: argparse.Namespace) -> str | None:
    if args.src is None or args.dst is None:
        return "src and dst are required unless --verify-manifest is used"
    return None


def _maybe_verify_output(args: argparse.Namespace) -> VerificationResult | None:
    if not args.verify_output:
        return None
    return scan_outputs(
        args.dst,
        sample_size=args.verify_output_sample,
        pixel_ocr=args.verify_output_pixel_ocr,
        strict_ocr=True,
    )


def _maybe_emit_manifest(
    args: argparse.Namespace,
    summary: AuditSummary,
    verification: VerificationResult | None,
) -> None:
    if args.manifest_mode is None:
        return
    manifest_obj = build_manifest(
        summary,
        args.manifest_mode,
        output_verification=verification,
    )
    json_path = args.manifest_json or args.dst / "compliance_manifest.json"
    md_path = args.manifest_md or args.dst / "COMPLIANCE_MANIFEST.md"
    _write_json(json_path, manifest_obj.as_dict())
    _write_text(md_path, render_markdown(manifest_obj))
    LOG.info(
        "manifest emitted regime=%s manifest_sha256=%s json=%s md=%s",
        manifest_obj.regime.code,
        manifest_obj.manifest_sha256[:16] + "...",
        json_path,
        md_path,
    )


def _run_anonymize_mode(args: argparse.Namespace) -> int:
    err = _validate_anonymize_args(args)
    if err is not None:
        print(f"error: {err}", file=sys.stderr)
        return 2
    try:
        keep_tags = _build_keep_tags(args.keep)
    except ValueError as exc:
        print(f"error: --keep: {exc}", file=sys.stderr)
        return 2

    config = AnonymizationConfig(
        salt=args.salt,
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
        keep_tags=keep_tags,
        progress_cb=_build_progress_cb(_count_targets(args.src), quiet=args.quiet),
    )

    summary = anonymize_path(args.src, args.dst, config=config)
    summary_dict = summary.as_dict()

    log_path = args.audit_log or args.dst / "anonymization_audit.json"
    _write_json(log_path, summary_dict)
    if args.report_md is not None:
        _write_text(args.report_md, render_markdown_report(summary_dict))

    verification = _maybe_verify_output(args)
    _maybe_emit_manifest(args, summary, verification)

    LOG.info(
        "processed=%d failed=%d burned_in_warnings=%d uid_remaps=%d dry_run=%s audit=%s",
        summary.files_processed,
        summary.files_failed,
        summary.burned_in_warnings,
        summary.uid_remapping_count,
        summary.dry_run,
        log_path,
    )
    return 0 if summary.files_failed == 0 else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    from anonymize import __version__

    parser = build_arg_parser(__version__)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=_resolve_log_level(verbose=args.verbose, quiet=args.quiet),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.verify_manifest is not None:
        return _run_verify_mode(args)
    return _run_anonymize_mode(args)
