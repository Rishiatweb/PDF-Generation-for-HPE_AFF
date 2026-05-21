# Legacy

Frozen pre-rewrite code, kept for reference only. **Do not extend or import
from anything in this directory.** Active code lives in `src/aff/`.

| Archived | Replacement |
| --- | --- |
| `legacy/data_pipeline/` (full package: ingest, consolidate, order, loader, storage, generate, cli, tests) | `src/aff/` (rebuilt incrementally) |
| `legacy/blank_form_generator.py` (white-rectangle redaction) | `src/aff/blank_forms/` (PDF-native: AcroForm clearing + content-stream redaction; planned) |
| `legacy/analyze_forms.py` (audit script for the old generator) | TBD — rebuild against the new output |
| `legacy/form_harness.py` (synthetic AcroForm PDF generator) | TBD — port or rewrite as needed |

The dataset downloaders under `legacy/data_pipeline/ingest/` are the only
modules being ported forward; everything else is being redesigned.
