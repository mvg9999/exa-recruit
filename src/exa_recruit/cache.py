"""SQLite search history cache."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .searcher import SearchResponse

DEFAULT_DB_PATH = Path.home() / ".config" / "exa-recruit" / "history.db"


def _get_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Get or create the SQLite database."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            query TEXT NOT NULL,
            num_results INTEGER NOT NULL,
            cost_dollars REAL,
            results_json TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def save_search(response: SearchResponse, db_path: Path | None = None) -> int:
    """Save a search to the history database. Returns the row ID."""
    conn = _get_db(db_path)
    results_data = [
        {
            "name": r.name,
            "linkedin_url": r.linkedin_url,
            "title": r.title,
            "highlights": r.highlights,
        }
        for r in response.results
    ]
    cursor = conn.execute(
        "INSERT INTO searches (timestamp, query, num_results, cost_dollars, results_json) VALUES (?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            response.query,
            len(response.results),
            response.cost_dollars,
            json.dumps(results_data),
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_history(
    limit: int = 10,
    query_filter: str | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    """Get search history entries."""
    conn = _get_db(db_path)
    if query_filter:
        rows = conn.execute(
            "SELECT id, timestamp, query, num_results, cost_dollars FROM searches WHERE query LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{query_filter}%", limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, timestamp, query, num_results, cost_dollars FROM searches ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "timestamp": r[1],
            "query": r[2],
            "num_results": r[3],
            "cost_dollars": r[4],
        }
        for r in rows
    ]
