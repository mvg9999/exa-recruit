"""CSV export for search results."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

from .searcher import PersonResult, SearchResponse

CSV_COLUMNS = ["timestamp", "name", "linkedin_url", "title", "query", "highlights"]

FILTERED_CSV_COLUMNS = [
    "timestamp", "name", "linkedin_url", "title", "query", "highlights",
    "match", "confidence", "reason", "current_company", "current_role", "graduation_year",
]


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


def export_filtered_csv(
    matched: list[tuple],
    rejected: list[tuple],
    query: str,
    output_dir: str = "./output",
) -> tuple[Path, Path | None]:
    """Export filtered results to CSV files.

    Args:
        matched: List of (PersonResult, FilterResult) tuples that passed filtering.
        rejected: List of (PersonResult, FilterResult) tuples that were rejected.
        query: The original search query.
        output_dir: Directory for output files.

    Returns:
        Tuple of (matched_csv_path, rejected_csv_path or None).
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    slug = slugify(query)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    matched_path = out_path / f"{slug}-filtered-{date_str}.csv"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    # Write matched candidates
    _write_filtered_csv(matched_path, matched, query, timestamp)

    # Write rejected candidates if any
    rejected_path = None
    if rejected:
        rejected_path = out_path / f"{slug}-rejected-{date_str}.csv"
        _write_filtered_csv(rejected_path, rejected, query, timestamp)

    return matched_path, rejected_path


def _write_filtered_csv(
    filepath: Path,
    results: list[tuple],
    query: str,
    timestamp: str,
) -> None:
    """Write filtered results to a CSV file."""
    file_exists = filepath.exists() and filepath.stat().st_size > 0

    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FILTERED_CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()

        for person, fr in results:
            writer.writerow({
                "timestamp": timestamp,
                "name": person.name,
                "linkedin_url": person.linkedin_url,
                "title": person.title,
                "query": query,
                "highlights": " | ".join(person.highlights) if person.highlights else "",
                "match": fr.match,
                "confidence": f"{fr.confidence:.2f}",
                "reason": fr.reason,
                "current_company": fr.current_company or "",
                "current_role": fr.current_role or "",
                "graduation_year": fr.graduation_year or "",
            })
