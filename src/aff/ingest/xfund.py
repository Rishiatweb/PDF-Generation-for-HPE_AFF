"""XFUND (German + French) ingester.

Downloads JSON annotations + image zips directly from the official XFUND
GitHub release. No HuggingFace loading script involved.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import requests
import structlog
from PIL import Image

from aff.schema import DocumentRecord, FieldRecord

log = structlog.get_logger()

_BASE_URL = "https://github.com/doc-analysis/XFUND/releases/download/v1.0"
_SUBSETS = {"de": "xfund_de", "fr": "xfund_fr"}
_LANGUAGES = {"de": "de", "fr": "fr"}


def _download(url: str, dest: Path) -> bool:
    """Download ``url`` to ``dest`` if missing. Returns True on success."""
    if dest.exists():
        return True
    log.info("ingest.xfund.download", url=url)
    try:
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                fh.write(chunk)
        return True
    except Exception as exc:
        log.error("ingest.xfund.download_failed", url=url, error=str(exc))
        return False


def _normalise_bbox(bbox: list, width: int, height: int) -> list[float]:
    if len(bbox) != 4:
        return [0.0, 0.0, 0.0, 0.0]
    x0, y0, x1, y1 = (float(v) for v in bbox)
    return [
        max(0.0, min(1.0, x0 / width)),
        max(0.0, min(1.0, y0 / height)),
        max(0.0, min(1.0, x1 / width)),
        max(0.0, min(1.0, y1 / height)),
    ]


def _ingest_subset(lang_code: str, data_root: Path) -> list[DocumentRecord]:
    source = _SUBSETS[lang_code]
    language = _LANGUAGES[lang_code]
    raw_dir = data_root / "raw" / "xfund" / lang_code
    raw_dir.mkdir(parents=True, exist_ok=True)
    img_dir = raw_dir / "images"
    img_dir.mkdir(exist_ok=True)
    png_dir = raw_dir / "images_png"
    png_dir.mkdir(exist_ok=True)

    log.info("ingest.xfund.start", lang=lang_code)
    records: list[DocumentRecord] = []

    for split_name in ("train", "val"):
        json_dest = raw_dir / f"{lang_code}.{split_name}.json"
        zip_dest = raw_dir / f"{lang_code}.{split_name}.zip"

        if not _download(f"{_BASE_URL}/{lang_code}.{split_name}.json", json_dest):
            log.warning("ingest.xfund.json_skip", lang=lang_code, split=split_name)
            continue
        if not _download(f"{_BASE_URL}/{lang_code}.{split_name}.zip", zip_dest):
            log.warning("ingest.xfund.zip_skip", lang=lang_code, split=split_name)
            continue

        with zipfile.ZipFile(zip_dest) as zf:
            zf.extractall(img_dir)

        with open(json_dest, encoding="utf-8") as fh:
            data = json.load(fh)

        for doc in data.get("documents", []):
            doc_id = str(doc.get("id", f"{source}_{len(records):05d}"))
            img_info = doc.get("img", {})
            fname = img_info.get("fname", "")
            width = int(img_info.get("width", 1))
            height = int(img_info.get("height", 1))

            img_path: Path | None = None
            direct = img_dir / fname
            if direct.exists():
                img_path = direct
            else:
                matches = list(img_dir.rglob(Path(fname).name))
                if matches:
                    img_path = matches[0]

            if img_path is None:
                log.warning("ingest.xfund.no_image", doc_id=doc_id, fname=fname)
                continue

            png_path = png_dir / f"{doc_id}.png"
            if not png_path.exists():
                with Image.open(img_path) as im:
                    im.save(png_path)

            field_records: list[FieldRecord] = []
            for entity in doc.get("document", []):
                label_text = entity.get("text", "")
                role = entity.get("label", "other").lower()
                bbox_norm = _normalise_bbox(
                    list(entity.get("box", [0, 0, 0, 0])),
                    width,
                    height,
                )
                field_records.append(
                    FieldRecord(
                        field_id=str(entity.get("id", "")),
                        label=label_text,
                        value=label_text if role == "answer" else "",
                        role=role,
                        bbox_norm=bbox_norm,
                        page=0,
                        source_fmt="image",
                    )
                )

            records.append(
                DocumentRecord(
                    source=source,
                    doc_id=doc_id,
                    image_path=str(png_path),
                    pdf_path=None,
                    page_count=1,
                    language=language,
                    doc_class="form",
                    fields=field_records,
                    quality_tier="degraded",
                )
            )

    log.info("ingest.xfund.complete", lang=lang_code, records=len(records))
    return records


def ingest(data_root: Path, seed: int) -> list[DocumentRecord]:
    """Download and normalise XFUND German + French subsets."""
    records: list[DocumentRecord] = []
    for lang_code in ("de", "fr"):
        try:
            records.extend(_ingest_subset(lang_code, data_root))
        except Exception as exc:
            log.error("ingest.xfund.failed", lang=lang_code, error=str(exc))
    return records
