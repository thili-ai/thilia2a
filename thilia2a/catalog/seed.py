"""Seed the Catalog Agent's own return-policy database — the Catalog team's system, deliberately
separate from the Order Agent's (`thilimcp`'s `shop.db`), even down to the storage layer.
"""
import sqlite3

WINDOWS = {"electronics": 15, "clothing": 30, "perishables": 0}


def seed_catalog(db_path: str = "catalog.db") -> sqlite3.Connection:
    """Create and seed the Catalog Agent's return-policy table at db_path."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("DROP TABLE IF EXISTS return_policy")
    conn.execute("CREATE TABLE return_policy (category TEXT PRIMARY KEY, window_days INTEGER NOT NULL)")
    for category, days in WINDOWS.items():
        conn.execute("INSERT INTO return_policy VALUES (?, ?)", (category, days))
    conn.commit()
    return conn
