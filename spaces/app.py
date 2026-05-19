"""Hugging Face Space demo for dcm-anon.

Synthetic-DICOM only. Refuses uploads larger than 2 MB. Outputs a
downloadable zip with the anonymized file, audit log, and compliance
manifest.

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

# Monkey-patch gradio_client schema handler before gradio imports.
# Upstream bug: get_type raises TypeError on bool schemas (additionalProperties: True).
# Affects /info endpoint -> "No API found" in HF Space UI. Present in 4.x and 5.x.
import gradio_client.utils as _gru

_orig_get_type = _gru.get_type
_orig_json_to_py = _gru._json_schema_to_python_type


def _patched_get_type(schema: object) -> str:
    if isinstance(schema, bool):
        return "Any" if schema else "Never"
    return _orig_get_type(schema)  # type: ignore[arg-type]


def _patched_json_to_py(schema: object, defs: object) -> str:
    if isinstance(schema, bool):
        return "Any" if schema else "Never"
    return _orig_json_to_py(schema, defs)  # type: ignore[arg-type]


_gru.get_type = _patched_get_type  # type: ignore[assignment]
_gru._json_schema_to_python_type = _patched_json_to_py  # type: ignore[assignment]

import gradio as gr  # noqa: E402

from dcm_anon import AnonymizationConfig, anonymize_path  # noqa: E402
from dcm_anon.manifest import build_manifest  # noqa: E402
from dcm_anon.verify_output import scan_outputs  # noqa: E402

DEMO_HEADER = """# dcm-anon: interactive demo

Upload a **synthetic** DICOM file (e.g. from
[pydicom test data](https://github.com/pydicom/pydicom/tree/main/pydicom/data/test_files)
or [TCIA](https://www.cancerimagingarchive.net/)) to see the
anonymized output, audit log, and compliance manifest.

**Do not upload files containing real PHI.** This Space runs on shared
public infrastructure with no DPA and no encryption at rest. Your upload
is visible to the pod that processes it. Max 2 MB.

For real research data, install locally:

```bash
pip install dcm-anonymizer
dcm-anon /path/to/study out/ --manifest-mode gdpr --verify-output
```
"""


MAX_UPLOAD_BYTES = 2 * 1024 * 1024

_CLEANUP_DELAY_SECONDS = 30


def _deferred_rmtree(path: Path, delay: int = _CLEANUP_DELAY_SECONDS) -> None:
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

    _deferred_rmtree(workdir)

    return summary_text, json.dumps(manifest_dict, indent=2), str(zip_path)


with gr.Blocks(title="dcm-anon demo") as demo:
    gr.Markdown(DEMO_HEADER)
    with gr.Row():
        with gr.Column():
            file_in = gr.File(label="Synthetic DICOM (.dcm), max 2 MB", file_types=[".dcm"])
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
        "[Zenodo DOI](https://doi.org/10.5281/zenodo.20267651) · "
        "[Reserve early access](https://ces107.github.io/dcm-anon/#early-access)"
    )


demo.queue()

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0")
