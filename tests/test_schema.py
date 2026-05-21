"""Schema dataclass behaviour and JSON round-trip."""

from __future__ import annotations

from aff.schema import DocumentRecord, FieldRecord


def _make_doc() -> DocumentRecord:
    return DocumentRecord(
        source="funsd",
        doc_id="doc-1",
        image_path="data/raw/funsd/doc-1.png",
        pdf_path=None,
        page_count=1,
        language="en",
        doc_class="form",
        fields=[
            FieldRecord(
                field_id="0",
                label="Name",
                value="",
                role="question",
                bbox_norm=[0.10, 0.20, 0.30, 0.25],
                page=0,
                source_fmt="image",
            ),
            FieldRecord(
                field_id="1",
                label="Acme Corp",
                value="Acme Corp",
                role="answer",
                bbox_norm=[0.35, 0.20, 0.60, 0.25],
                page=0,
                source_fmt="image",
            ),
        ],
        quality_tier="degraded",
    )


def test_has_response_is_derived():
    question, answer = _make_doc().fields
    assert question.has_response is False
    assert answer.has_response is True


def test_gt_payload_is_derived():
    doc = _make_doc()
    assert doc.gt_payload == {"1": "Acme Corp"}


def test_round_trip_preserves_fields():
    original = _make_doc()
    restored = DocumentRecord.from_dict(original.to_dict())
    assert restored == original


def test_to_dict_emits_derived_views():
    payload = _make_doc().to_dict()
    assert payload["gt_payload"] == {"1": "Acme Corp"}
    assert [f["has_response"] for f in payload["fields"]] == [False, True]


def test_from_dict_ignores_extra_derived_keys():
    """from_dict must tolerate documents that already carry derived keys."""
    raw = _make_doc().to_dict()
    raw["fields"][0]["has_response"] = True  # corrupt — should be ignored
    restored = DocumentRecord.from_dict(raw)
    # Derived view recomputes from role+value, not the persisted flag
    assert restored.fields[0].has_response is False
