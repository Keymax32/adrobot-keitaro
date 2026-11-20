import pytest
from fastapi import HTTPException

from app.editor import edit, merge, remote_offers


def bindings(weights):
    return merge([], [dict(offer_id=i, share=w) for i, w in enumerate(weights, 1)], {})


def test_pin_rounding_archive_restore():
    rows = edit(bindings([25] * 4), 1, "pin")
    rows = edit(rows, 2, "remove")
    assert [r["share"] for r in rows] == [25, 0, 38, 37]
    assert [o["offer_id"] for o in remote_offers(rows)] == [1, 3, 4]
    rows = edit(rows, 2, "restore")
    assert [r["share"] for r in rows] == [25] * 4


def test_impossible_pin_set_does_not_mutate_draft():
    rows = edit(bindings([60, 40]), 1, "pin")
    with pytest.raises(HTTPException):
        edit(rows, 2, "remove")
    assert [r["share"] for r in rows] == [60, 40]


def test_fetch_archives_missing_and_recognizes_return():
    rows = bindings([50, 50])
    rows = merge(rows, [dict(offer_id=2, share=100)], {})
    assert rows[-1]["removed"] and rows[-1]["share"] == 0
    rows = merge(rows, [dict(offer_id=1, share=100)], {})
    assert len(rows) == 2 and not rows[0]["removed"]


def test_last_offer_and_disabled_binding():
    rows = bindings([100, 0])
    rows[1]["state"] = "disabled"
    result = remote_offers(edit(rows, 1, "remove"))
    assert result == [dict(offer_id=2, share=0, state="disabled")]

