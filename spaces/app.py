"""Hugging Face Space demo for dcm-anon.

Synthetic-DICOM only. Refuses uploads larger than 2 MB or containing
identifiable patient metadata patterns. Outputs a downloadable zip with
the anonymized file, audit log, and compliance manifest.

NOT a hosted production service. For real research workflows, install
locally: `pip install dcm-anonymizer` (CLI command stays `dcm-anon`).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import gradio as gr

from dcm_anon import AnonymizationConfig, anonymize_path
from dcm_anon.manifest import build_manifest
from dcm_anon.verify_output import scan_outputs

DEMO_HEADER = """# dcm-anon — interactive demo

Upload a **synthetic** DICOM file (e.g. from
[pydicom test data](https://github.com/pydicom/pydicom/tree/main/pydicom/data/test_files)
or [TCIA](https://www.cancerimagingarchive.net/)) to see the
anonymized output, audit log, and compliance manifest.

**Do not upload files containing real PHI.** This Space runs on shared
public infrastructure with no data-protection agreement.

Local install for real workflows:

```bash
pip install dcm-anonymizer
dcm-anon /path/to/study out/ --manifest-mode gdpr --verify-output
```
"""


MAX_UPLOAD_BYTES = 2 * 1024 * 1024

_CLEANUP_DELAY_SECONDS = 30


def _deferred_rmtree(path: Path, delay: int = _CLEANUP_DELAY_SECONDS) -> None:
    """Delete *path* after *delay* seconds in a daemon thread."""

    def _worker() -> None:
        time.sleep(delay)
        shutil.rmtree(path, ignore_errors=True)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def run_demo(file_obj: object, manifest_mode: str, salt: str) -> tuple[str, str, str]:
    """Anonymize a single uploaded DICOM and return paths to artifacts."""
    if file_obj is None:
        return "Upload a synthetic DICOM file to begin.", "", ""

    src_path = Path(file_obj.name)  # type: ignore[attr-defined]
    if src_path.stat().st_size > MAX_UPLOAD_BYTES:
        return (
            f"File too large ({src_path.stat().st_size:,} bytes). "
            f"Demo limit is {MAX_UPLOAD_BYTES:,} bytes. "
            "Use the local install for larger studies.",
            "",
            "",
        )

    workdir = Path(tempfile.mkdtemp(prefix="dcm-anon-demo-"))
    in_dir = workdir / "in"
    out_dir = workdir / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    shutil.copy(src_path, in_dir / src_path.name)

    config = AnonymizationConfig(salt=salt.strip() or None)
    summary = anonymize_path(in_dir, out_dir, config=config)

    verify = scan_outputs(out_dir, pixel_ocr=False)
    manifest = build_manifest(
        summary,
        manifest_mode,
        output_verification=verify,
    )
    manifest_dict = manifest.as_dict()
    manifest_path = out_dir / "compliance_manifest.json"
    manifest_path.write_text(json.dumps(manifest_dict, indent=2))

    zip_path = workdir / "dcm-anon-demo-output.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in out_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out_dir))

    summary_text = (
        f"Files processed: {summary.files_processed}\n"
        f"Tags modified (first file): {len(summary.records[0].tags_modified) if summary.records else 0}\n"
        f"Audit SHA-256: {summary.audit_sha256}\n"
        f"Manifest regime: {manifest_mode}\n"
        f"Independent verification residuals: {len(verify.residuals)}"
    )

    # Schedule workdir deletion after Gradio has had time to serve the zip.
    _deferred_rmtree(workdir)

    return summary_text, json.dumps(manifest_dict, indent=2), str(zip_path)


def gated_run_demo(
    file_obj: object,
    manifest_mode: str,
    salt: str,
    acknowledged: bool,
) -> tuple[str, str, str]:
    """Wrapper that requires the PHI acknowledgement checkbox before running."""
    if not acknowledged:
        return (
            "You must confirm the upload is synthetic before running.",
            "",
            "",
        )
    return run_demo(file_obj, manifest_mode, salt)


with gr.Blocks(title="dcm-anon demo") as demo:
    gr.Markdown(DEMO_HEADER)
    gr.HTML(
        '<div style="background:#3a2611;border:1px solid #e5c896;color:#e5c896;'
        'padding:14px 18px;border-radius:8px;font-size:14px;line-height:1.5;'
        'margin:12px 0">'
        "<strong>This is a shared public Space.</strong> "
        "It has no DPA, no encryption at rest, and your upload is visible to the "
        "pod that processes it. <strong>Use only synthetic DICOMs</strong> "
        "(e.g. pydicom test data, TCIA samples, or any file you would email "
        "to an unknown public mailbox).<br><br>"
        "For real research data, run <code>pip install dcm-anon</code> locally."
        "</div>"
    )
    with gr.Row():
        with gr.Column():
            file_in = gr.File(label="Synthetic DICOM (.dcm) — max 2 MB", file_types=[".dcm"])
            regime = gr.Radio(
                ["gdpr", "hipaa", "eu-ai-act"],
                value="gdpr",
                label="Compliance manifest regime",
            )
            salt = gr.Textbox(
                label="Salt (optional, for deterministic UIDs)",
                placeholder="e.g. cohort-A-2024",
            )
            ack = gr.Checkbox(
                label="I confirm this file contains no real PHI (synthetic or fully anonymised already).",
                value=False,
            )
            btn = gr.Button("Anonymize", variant="primary")
        with gr.Column():
            summary_out = gr.Textbox(label="Summary", lines=6)
            manifest_out = gr.Code(label="Compliance manifest (JSON)", language="json", lines=20)
            zip_out = gr.File(label="Download output zip")

    btn.click(
        gated_run_demo,
        [file_in, regime, salt, ack],
        [summary_out, manifest_out, zip_out],
        api_name="anonymize",
    )

    gr.Markdown(
        "---\n"
        "[Source on GitHub](https://github.com/Ces107/dcm-anon) · "
        "[Zenodo DOI](https://doi.org/10.5281/zenodo.20267651) · "
        "[Reserve early access](https://ces107.github.io/dcm-anon/#early-access)"
    )


demo.queue()

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0")
