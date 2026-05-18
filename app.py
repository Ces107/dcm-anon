"""Hugging Face Space demo for dcm-anon.

Synthetic-DICOM only. Refuses uploads larger than 5 MB or containing
identifiable patient metadata patterns. Outputs a downloadable zip with
the anonymized file, audit log, and compliance manifest.

NOT a hosted production service. For real research workflows, install
locally: `pip install dcm-anonymizer` (CLI command stays `dcm-anon`).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import gradio as gr

from anonymize import AnonymizationConfig, anonymize_path
from manifest import build_manifest
from verify_output import scan_outputs

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


MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def run_demo(file_obj, manifest_mode: str, salt: str) -> tuple[str, str, str]:
    """Anonymize a single uploaded DICOM and return paths to artifacts."""
    if file_obj is None:
        return "Upload a synthetic DICOM file to begin.", "", ""

    src_path = Path(file_obj.name)
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
    summary = anonymize_path(str(in_dir), str(out_dir), config=config)

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
        f"Independent verification residuals: {verify.residuals_found}"
    )

    return summary_text, json.dumps(manifest_dict, indent=2), str(zip_path)


with gr.Blocks(title="dcm-anon demo") as demo:
    gr.Markdown(DEMO_HEADER)
    with gr.Row():
        with gr.Column():
            file_in = gr.File(label="Synthetic DICOM (.dcm) — max 5 MB", file_types=[".dcm"])
            regime = gr.Radio(
                ["gdpr", "hipaa", "eu-ai-act"],
                value="gdpr",
                label="Compliance manifest regime",
            )
            salt = gr.Textbox(
                label="Salt (optional, for deterministic UIDs)",
                placeholder="e.g. cohort-A-2024",
            )
            btn = gr.Button("Anonymize", variant="primary")
        with gr.Column():
            summary_out = gr.Textbox(label="Summary", lines=6)
            manifest_out = gr.Code(label="Compliance manifest (JSON)", language="json", lines=20)
            zip_out = gr.File(label="Download output zip")

    btn.click(
        run_demo,
        [file_in, regime, salt],
        [summary_out, manifest_out, zip_out],
        api_name="anonymize",
    )

    gr.Markdown(
        "---\n"
        "[Source on GitHub](https://github.com/Ces107/dcm-anon) · "
        "[Zenodo DOI](https://doi.org/10.5281/zenodo.20267652) · "
        "[Reserve early access](https://ces107.github.io/dcm-anon/#early-access)"
    )


demo.queue()

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", show_api=False)
