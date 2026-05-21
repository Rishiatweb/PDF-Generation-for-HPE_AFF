"""Smoke tests for ingest module shape.

These do not download anything — they verify each ingester exposes the
expected ``ingest(data_root, seed)`` contract so a wiring bug shows up
without paying the network cost.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

import pytest

from aff.ingest import funsd, rvlcdip, vrdu, xfund

INGESTERS: list[tuple[str, Callable]] = [
    ("funsd", funsd.ingest),
    ("xfund", xfund.ingest),
    ("vrdu", vrdu.ingest),
    ("rvlcdip", rvlcdip.ingest),
]


@pytest.mark.parametrize(("name", "fn"), INGESTERS, ids=[n for n, _ in INGESTERS])
def test_ingest_signature(name: str, fn: Callable):
    sig = inspect.signature(fn)
    params = list(sig.parameters)
    assert params == ["data_root", "seed"], (
        f"{name}.ingest expected (data_root, seed); got {params}"
    )


@pytest.mark.parametrize(("name", "fn"), INGESTERS, ids=[n for n, _ in INGESTERS])
def test_ingest_has_docstring(name: str, fn: Callable):
    assert fn.__doc__, f"{name}.ingest is missing its docstring"
