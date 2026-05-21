"""Pipeline data schemas.

Two dataclasses define every record that flows between stages:

* :class:`FieldRecord` — one annotated field on a form page.
* :class:`DocumentRecord` — one source document plus its fields.

Both are plain dataclasses (no pydantic), with derived views (``has_response``,
``gt_payload``) exposed as properties so there is exactly one source of truth.
Use :meth:`DocumentRecord.to_dict` / :meth:`DocumentRecord.from_dict` for JSON
serialisation — these include the derived views on write and strip them on read.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

type Bbox = list[float]
"""``[x0, y0, x1, y1]`` normalised to the page in [0, 1]."""

type Role = Literal["question", "answer", "header", "other"]
type SourceFmt = Literal["image", "pdf"]
type QualityTier = Literal["clean", "degraded", "clean_synthetic", "degraded_synthetic"]
type Split = Literal["train", "val", "test"]


@dataclass(slots=True)
class FieldRecord:
    """A single annotated field (question, answer, header, …) on one page."""

    field_id: str
    label: str
    value: str
    role: Role
    bbox_norm: Bbox
    page: int
    source_fmt: SourceFmt
    match_type: str | None = None

    @property
    def has_response(self) -> bool:
        return self.role == "answer" and bool(self.value)


@dataclass(slots=True)
class DocumentRecord:
    """One source document, its metadata, and all annotated fields on it."""

    source: str
    doc_id: str
    image_path: str | None
    pdf_path: str | None
    page_count: int
    language: str
    doc_class: str
    fields: list[FieldRecord] = field(default_factory=list)
    quality_tier: QualityTier = "degraded"
    quality_score: float = 0.0
    split: Split | None = None

    @property
    def gt_payload(self) -> dict[str, str]:
        return {f.field_id: f.value for f in self.fields if f.has_response}

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready dict, including derived views."""
        data = asdict(self)
        data["gt_payload"] = self.gt_payload
        for fld, raw in zip(self.fields, data["fields"], strict=True):
            raw["has_response"] = fld.has_response
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentRecord:
        """Reconstruct from a dict produced by :meth:`to_dict` (or equivalent)."""
        raw_fields = data.get("fields", [])
        fields_ = [
            FieldRecord(**{k: v for k, v in rf.items() if k != "has_response"}) for rf in raw_fields
        ]
        scalars = {k: v for k, v in data.items() if k not in {"fields", "gt_payload"}}
        return cls(fields=fields_, **scalars)
