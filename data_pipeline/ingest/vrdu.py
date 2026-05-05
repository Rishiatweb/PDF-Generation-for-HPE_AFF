"""Stage 1.3 — VRDU (registration_forms + ad_buy_forms) ingester."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import structlog

from data_pipeline import DocumentRecord, FieldRecord

log = structlog.get_logger()

_VRDU_REPO = "https://github.com/google-research-datasets/vrdu"

_SUBSETS = {
    "registration_forms": "vrdu_registration",
    "ad_buy_forms": "vrdu_ad_buy",
}


def _clone_vrdu(vrdu_dir: Path) -> bool:
    """Clone VRDU repo if not already present. Returns True on success."""
    if (vrdu_dir / "registration_forms").exists():
        log.info("ingest.vrdu.already_cloned", path=str(vrdu_dir))
        return True
    vrdu_dir.parent.mkdir(parents=True, exist_ok=True)
    log.info("ingest.vrdu.cloning", url=_VRDU_REPO)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", _VRDU_REPO, str(vrdu_dir)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        log.error("ingest.vrdu.clone_failed", stderr=result.stderr)
        return False
    return True


def _pdf_sha256(pdf_path: Path) -> str:
    h = hashlib.sha256()
    with open(pdf_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _render_pdf_pages(pdf_path: Path, img_dir: Path, doc_id: str) -> list[str]:
    """Render each page of a PDF to PNG. Returns list of image paths."""
    try:
        import fitz  # pymupdf
    except ImportError:
        log.warning("ingest.vrdu.pymupdf_missing")
        return []

    img_paths: list[str] = []
    doc = fitz.open(str(pdf_path))
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=150)
        out_path = img_dir / f"{doc_id}_p{page_num:03d}.png"
        pix.save(str(out_path))
        img_paths.append(str(out_path))
    doc.close()
    return img_paths


def _parse_subset(
    subset_name: str,
    source: str,
    vrdu_dir: Path,
    img_dir: Path,
    seen_sha256: set[str],
) -> list[DocumentRecord]:
    subset_dir = vrdu_dir / subset_name
    jsonl_gz = subset_dir / "dataset.jsonl.gz"
    meta_json = subset_dir / "meta.json"
    pdfs_dir = subset_dir / "pdfs"

    if not jsonl_gz.exists():
        log.warning("ingest.vrdu.missing_dataset", subset=subset_name, path=str(jsonl_gz))
        return []

    # Load field type metadata
    match_types: dict[str, str] = {}
    if meta_json.exists():
        with open(meta_json, encoding="utf-8") as fh:
            meta = json.load(fh)
        # meta.json maps field_name → match_type string
        for field_name, field_meta in meta.items():
            if isinstance(field_meta, dict):
                match_types[field_name] = field_meta.get("match_type", "StringMatch")
            elif isinstance(field_meta, str):
                match_types[field_name] = field_meta

    records: list[DocumentRecord] = []

    with gzip.open(jsonl_gz, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                item: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("ingest.vrdu.json_error", error=str(exc))
                continue

            doc_id = str(item.get("doc_id", item.get("id", f"{source}_{len(records):05d}")))
            pdf_filename = item.get("pdf_file", f"{doc_id}.pdf")
            pdf_path = pdfs_dir / pdf_filename

            if not pdf_path.exists():
                # Try finding by doc_id
                alt = pdfs_dir / f"{doc_id}.pdf"
                if alt.exists():
                    pdf_path = alt
                else:
                    log.warning("ingest.vrdu.missing_pdf", doc_id=doc_id)
                    continue

            # Dedup by sha256
            sha = _pdf_sha256(pdf_path)
            if sha in seen_sha256:
                log.debug("ingest.vrdu.dedup_sha256", doc_id=doc_id)
                continue
            seen_sha256.add(sha)

            # Render pages to PNG
            doc_img_dir = img_dir / source
            doc_img_dir.mkdir(parents=True, exist_ok=True)
            img_paths = _render_pdf_pages(pdf_path, doc_img_dir, doc_id)
            primary_image = img_paths[0] if img_paths else ""

            # Parse field annotations
            annotations = item.get("annotations", {})
            field_records: list[FieldRecord] = []
            gt_payload: dict[str, str] = {}

            # Annotations can be dict {field_name: {value, bbox}} or list
            if isinstance(annotations, dict):
                for field_name, ann in annotations.items():
                    value = str(ann.get("value", ann.get("text", "")))
                    box = ann.get("bbox", ann.get("box", [0, 0, 0, 0]))
                    if len(box) == 4:
                        x0, y0, x1, y1 = [float(v) for v in box]
                        # VRDU bboxes are normalised 0-1
                        bbox_norm = [
                            max(0.0, min(1.0, x0)),
                            max(0.0, min(1.0, y0)),
                            max(0.0, min(1.0, x1)),
                            max(0.0, min(1.0, y1)),
                        ]
                    else:
                        bbox_norm = [0.0, 0.0, 0.0, 0.0]

                    page_num = int(ann.get("page", 0))
                    mt = match_types.get(field_name, "StringMatch")

                    field_records.append(FieldRecord(
                        field_id=field_name,
                        label=field_name.replace("_", " ").title(),
                        value=value,
                        role="answer",
                        bbox_norm=bbox_norm,
                        page=page_num,
                        source_fmt="pdf",
                        has_response=bool(value.strip()),
                        match_type=mt,
                    ))

                    if value.strip():
                        gt_payload[field_name] = value

            elif isinstance(annotations, list):
                for ann in annotations:
                    field_name = str(ann.get("field_name", ann.get("name", "")))
                    value = str(ann.get("value", ann.get("text", "")))
                    box = ann.get("bbox", ann.get("box", [0, 0, 0, 0]))
                    if len(box) == 4:
                        x0, y0, x1, y1 = [float(v) for v in box]
                        bbox_norm = [
                            max(0.0, min(1.0, x0)),
                            max(0.0, min(1.0, y0)),
                            max(0.0, min(1.0, x1)),
                            max(0.0, min(1.0, y1)),
                        ]
                    else:
                        bbox_norm = [0.0, 0.0, 0.0, 0.0]

                    page_num = int(ann.get("page", 0))
                    mt = match_types.get(field_name, "StringMatch")

                    field_records.append(FieldRecord(
                        field_id=field_name,
                        label=field_name.replace("_", " ").title(),
                        value=value,
                        role="answer",
                        bbox_norm=bbox_norm,
                        page=page_num,
                        source_fmt="pdf",
                        has_response=bool(value.strip()),
                        match_type=mt,
                    ))

                    if value.strip():
                        gt_payload[field_name] = value

            page_count = int(item.get("page_count", len(img_paths) or 1))

            records.append(DocumentRecord(
                source=source,
                doc_id=doc_id,
                image_path=primary_image,
                pdf_path=str(pdf_path),
                page_count=page_count,
                language="en",
                doc_class="form",
                fields=field_records,
                gt_payload=gt_payload,
                quality_tier="clean",
                quality_score=0.0,
                split=None,
            ))

    log.info("ingest.vrdu.subset_complete", subset=subset_name, records=len(records))
    return records


def ingest(data_root: Path, seed: int) -> list[DocumentRecord]:  # noqa: ARG001
    """Download and normalise VRDU registration_forms + ad_buy_forms."""
    vrdu_dir = data_root / "raw" / "vrdu"
    img_dir = data_root / "raw" / "vrdu_images"

    if not _clone_vrdu(vrdu_dir):
        log.error("ingest.vrdu.clone_failed_abort")
        return []

    seen_sha256: set[str] = set()
    records: list[DocumentRecord] = []

    for subset_name, source in _SUBSETS.items():
        try:
            records.extend(_parse_subset(subset_name, source, vrdu_dir, img_dir, seen_sha256))
        except Exception as exc:
            log.error("ingest.vrdu.subset_failed", subset=subset_name, error=str(exc))

    log.info("ingest.vrdu.complete", total=len(records))
    return records
