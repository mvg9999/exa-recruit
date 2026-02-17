"""Exa People Search wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
from exa_py import Exa

from .config import get_api_key


@dataclass
class PersonResult:
    """A single person search result."""
    name: str
    linkedin_url: str
    title: str
    highlights: list[str] = field(default_factory=list)
    text: str = ""
    published_date: str = ""
    image: str = ""
    score: float = 0.0


@dataclass
class SearchResponse:
    """Complete search response."""
    query: str
    results: list[PersonResult]
    cost_dollars: float = 0.0


def search_people(
    query: str,
    num_results: int = 10,
    search_type: str = "auto",
    location: str | None = None,
    include_text: bool = False,
) -> SearchResponse:
    """Search for people using Exa API.

    Args:
        query: Natural language search query.
        num_results: Number of results (1-100).
        search_type: Search type (auto, neural, fast, deep, instant).
        location: ISO 2-letter country code for result biasing.
        include_text: Whether to include full profile text.
    """
    api_key = get_api_key()
    exa = Exa(api_key=api_key)

    # Build contents request
    contents: dict = {"highlights": {"numSentences": 3, "highlightsPerUrl": 3}}
    if include_text:
        contents["text"] = {"maxCharacters": 2000}

    # Build search kwargs
    kwargs: dict = {
        "query": query,
        "category": "people",
        "num_results": num_results,
        "type": search_type,
        "contents": contents,
    }
    if location:
        kwargs["userLocation"] = location

    response = exa.search(**kwargs)

    # Parse results
    people = []
    for r in response.results:
        # Title format varies: "Name | Title | LinkedIn" or "Name - Title | LinkedIn"
        raw_title = (r.title or "").replace(" | LinkedIn", "").strip()
        parts = [p.strip() for p in raw_title.split(" | ")]
        name = parts[0] if parts else ""
        title_str = " | ".join(parts[1:]) if len(parts) > 1 else ""

        people.append(PersonResult(
            name=name or (r.author or ""),
            linkedin_url=r.url or "",
            title=title_str,
            highlights=getattr(r, "highlights", []) or [],
            text=getattr(r, "text", "") or "",
            published_date=getattr(r, "publishedDate", "") or "",
            score=getattr(r, "score", 0.0) or 0.0,
        ))

    cost = 0.0
    if hasattr(response, "costDollars") and response.costDollars:
        cost = response.costDollars.get("total", 0.0) if isinstance(response.costDollars, dict) else float(response.costDollars)

    return SearchResponse(query=query, results=people, cost_dollars=cost)
