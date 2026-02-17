"""CSV export for search results."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

from .searcher import SearchResponse

CSV_COLUMNS = ["timestamp", "name", "linkedin_url", "title", "query", "highlights"]


def slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_len]


def auto_filename(query: str) -> str:
    """Generate a CSV filename from query and date."""
    slug = slugify(query)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{slug}-{date_str}.csv"


def export_csv(response: SearchResponse, output_dir: str = "./output") -> Path:
    """Export search results to a CSV file.

    Creates the output directory if needed. Appends to existing file if
    the filename matches (same query + same day).

    Returns the path to the CSV file.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    filename = auto_filename(response.query)
    filepath = out_path / filename

    file_exists = filepath.exists() and filepath.stat().st_size > 0
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()

        for person in response.results:
            writer.writerow({
                "timestamp": timestamp,
                "name": person.name,
                "linkedin_url": person.linkedin_url,
                "title": person.title,
                "query": response.query,
                "highlights": " | ".join(person.highlights) if person.highlights else "",
            })

    return filepath
