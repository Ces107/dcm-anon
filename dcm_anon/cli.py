"""CLI entry point for dcm-anon. Pure I/O glue: argv → AnonymizationConfig → run → write audit/manifest."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dcm_anon.audit import render_markdown_report
from dcm_anon.manifest import (
    build_manifest,
    load_audit_dict,
    load_manifest_dict,
    render_markdown,
    supported_regimes,
    verify_manifest,
)
from dcm_anon.pipeline import (
    AnonymizationConfig,
    ProgressCallback,
    anonymize_path,
    parse_keep_tag,
)
from dcm_anon.verify_output import VerificationResult, scan_outputs

LOG = logging.getLogger("dcmanon")

# Sentinel for ``--pdf-report auto`` (derive default report path under <dst>).
# Detected from the RAW argument string at parse time, before Path-wrapping, so
# the check is exact and platform-independent (a real file literally named
# "auto" still resolves to a Path via _pdf_report_arg).
PDF_REPORT_AUTO = "auto"


def _pdf_report_arg(value: str) -> str | Path:
    """argparse ``type`` for --pdf-report: keep the 'auto' sentinel, else Path."""
    if value == PDF_REPORT_AUTO:
        return PDF_REPORT_AUTO
    return Path(value)


def build_arg_parser(version: str) -> argparse.ArgumentParser:
    """Build the argparse parser. Public so tests can introspect choices."""
    parser = argparse.ArgumentParser(
        prog="dcm-anon",
        description=(
            "DICOM anonymizer. PS3.15 Basic Application Level Confidentiality "
            "Profile, with optional compliance manifest."
        ),
        epilog="See README.md for tags, regulatory mapping, and known limits.",
    )

    # positional
    parser.add_argument("src", type=Path, nargs="?",
                        help="Input .dcm file or directory (omit with --verify-manifest)")
    parser.add_argument("dst", type=Path, nargs="?",
                        help="Output directory (omit with --verify-manifest)")

    # anonymization options
    parser.add_argument("--salt", type=str, default=None,
                        help="Deterministic-UID salt (same salt + same source = same UIDs)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process files in memory and emit audit, but do NOT write outputs")
    parser.add_argument("--continue-on-error", action="store_true",
                        help="Skip malformed DICOMs instead of aborting")
    parser.add_argument("--keep", action="append", default=[], metavar="GGGG,EEEE",
                        help="Whitelist a tag (hex group,element); repeatable")

    # audit output
    parser.add_argument("--audit-log", type=Path, default=None,
                        help="Audit JSON path (default: <dst>/anonymization_audit.json)")
    parser.add_argument("--report-md", type=Path, default=None,
                        help="Optional human-readable Markdown summary path")

    # compliance manifest
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
        "--pdf-report",
        type=_pdf_report_arg,
        default=None,
        metavar="PATH",
        help=(
            "Also emit a professional PDF audit report at PATH (or 'auto' to "
            "use <dst>/COMPLIANCE_REPORT.pdf). Requires the [pdf] extra: "
            "pip install 'dcm-anonymizer[pdf]'. Works with --manifest-mode "
            "for the regulatory-citation section; without --manifest-mode the "
            "PDF contains the audit summary only."
        ),
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
            "(requires the tesseract binary; raises PixelOCRUnavailableError "
            "if pytesseract or tesseract is missing; use --no-strict-ocr to "
            "fall back to metadata-only scanning)"
        ),
    )
    parser.add_argument(
        "--no-strict-ocr",
        action="store_true",
        help=(
            "When --verify-output-pixel-ocr is set but pytesseract/tesseract "
            "is unavailable, fall back to metadata-only scanning instead of "
            "raising PixelOCRUnavailableError. Off by default: a missing OCR "
            "dependency fails loudly rather than emitting a falsely-green "
            "manifest."
        ),
    )

    # verify-manifest mode
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

    # logging
    parser.add_argument("--quiet", action="store_true", help="Suppress info logging")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", action="version", version=f"dcm-anon {version}")
    return parser


def _build_keep_tags(keep_specs: list[str]) -> frozenset[tuple[int, int]]:
    return frozenset(parse_keep_tag(s) for s in keep_specs) if keep_specs else frozenset()


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


def _validate_anonymize_args(args: argparse.Namespace) -> str | None:
    if args.src is None or args.dst is None:
        return "src and dst are required unless --verify-manifest is used"
    return None


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

    total = 1 if args.src.is_file() else len(list(args.src.rglob("*.dcm")))
    config = AnonymizationConfig(
        salt=args.salt,
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
        keep_tags=keep_tags,
        progress_cb=_build_progress_cb(total, quiet=args.quiet),
    )

    summary = anonymize_path(args.src, args.dst, config=config)
    summary_dict = summary.as_dict()

    log_path = args.audit_log or args.dst / "anonymization_audit.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(summary_dict, indent=2), encoding="utf-8")

    if args.report_md is not None:
        args.report_md.parent.mkdir(parents=True, exist_ok=True)
        args.report_md.write_text(render_markdown_report(summary), encoding="utf-8")

    manifest_obj = None
    if args.manifest_mode is not None:
        verification: VerificationResult | None = None
        if args.verify_output:
            verification = scan_outputs(
                args.dst,
                sample_size=args.verify_output_sample,
                pixel_ocr=args.verify_output_pixel_ocr,
                strict_ocr=not args.no_strict_ocr,
            )
        manifest_obj = build_manifest(
            summary,
            args.manifest_mode,
            output_verification=verification,
        )
        json_path = args.manifest_json or args.dst / "compliance_manifest.json"
        md_path = args.manifest_md or args.dst / "COMPLIANCE_MANIFEST.md"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(manifest_obj.as_dict(), indent=2), encoding="utf-8")
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(manifest_obj), encoding="utf-8")
        LOG.info(
            "manifest emitted regime=%s manifest_sha256=%s json=%s md=%s",
            manifest_obj.regime.code,
            manifest_obj.manifest_sha256[:16] + "...",
            json_path,
            md_path,
        )

    if args.pdf_report is not None:
        pdf_path = (
            args.dst / "COMPLIANCE_REPORT.pdf"
            if args.pdf_report == PDF_REPORT_AUTO
            else args.pdf_report
        )
        try:
            from dcm_anon.pdf_report import render_pdf

            written = render_pdf(summary, manifest_obj, pdf_path)
            LOG.info("pdf report emitted path=%s manifest_mode=%s",
                     written, args.manifest_mode or "none")
        except ImportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

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


def main(argv: list[str] | None = None) -> int:
    from dcm_anon import __version__

    parser = build_arg_parser(__version__)
    args = parser.parse_args(argv)

    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.WARNING
    else:
        log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.verify_manifest is not None:
        return _run_verify_mode(args)
    return _run_anonymize_mode(args)


if __name__ == "__main__":  # pragma: no cover — exercised via `python -m dcm_anon.cli`
    raise SystemExit(main())
