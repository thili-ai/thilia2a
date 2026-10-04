"""Stand up both agents for real and score the assistant against every single-item order in the
seeded shop, not a hand-picked list.

Run with: `pytest tests/conformance.py -q`
"""
import sqlite3
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

import pytest
import uvicorn
from thilimcp import seed_shop

from thilia2a import WINDOWS, ask, build_catalog_app, build_order_app, parse_returnable

TODAY = date(2026, 9, 30)


def _run(app, port):
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@pytest.fixture(scope="session", autouse=True)
def agents():
    tmp = Path(tempfile.mkdtemp())
    catalog_app = build_catalog_app(db_path=str(tmp / "catalog.db"))
    order_app = build_order_app(shop_db_path=str(tmp / "shop.db"))

    threading.Thread(target=_run, args=(catalog_app, 8102), daemon=True).start()
    threading.Thread(target=_run, args=(order_app, 8101), daemon=True).start()
    time.sleep(2)
    yield


@pytest.fixture(scope="session")
def grading_set():
    """Every single-item order's independently-computed expected eligibility verdict."""
    conn = seed_shop(str(Path(tempfile.mkdtemp()) / "ground_truth.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT o.id, o.created_at, p.category, count(oi.id) AS n_items
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        GROUP BY o.id HAVING n_items = 1
    """).fetchall()

    cases = []
    for r in rows:
        delivered = date.fromisoformat(r["created_at"])
        days_elapsed = (TODAY - delivered).days
        window = WINDOWS[r["category"]]
        cases.append((r["id"], days_elapsed <= window))
    return cases


async def test_known_order_completes_with_correct_verdict(grading_set):
    order_id, expected = next(c for c in grading_set if c[1])  # a returnable one
    state, text = await ask(str(order_id))
    assert state == "TASK_STATE_COMPLETED"
    assert parse_returnable(text) == expected


async def test_grading_set_scores_at_least_twenty_cases_correctly(grading_set):
    sample = grading_set[:20] if len(grading_set) >= 20 else grading_set
    correct = 0
    for order_id, expected in sample:
        state, text = await ask(str(order_id))
        assert state == "TASK_STATE_COMPLETED"
        if parse_returnable(text) == expected:
            correct += 1
    assert correct == len(sample)


async def test_malformed_input_fails_honestly_not_a_crash():
    state, text = await ask("not-a-number")
    assert state == "TASK_STATE_FAILED"
    assert "whole number" in text


async def test_missing_order_fails_honestly_not_a_crash():
    state, text = await ask("999999")
    assert state == "TASK_STATE_FAILED"
