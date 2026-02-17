"""LLM-based post-retrieval filtering using Claude Haiku 4.5 via OpenRouter."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

import openai

from .searcher import PersonResult


@dataclass
class FilterResult:
    """Result of LLM filtering for a single candidate."""
    match: bool
    confidence: float
    reason: str
    current_company: str | None = None
    current_role: str | None = None
    graduation_year: str | None = None


FILTER_PROMPT = """You are a recruiting filter. Given a candidate's LinkedIn profile data and search criteria, determine if this person is a genuine match.

Search criteria:
{criteria}

Candidate profile:
- Name: {name}
- Current title: {title}
- Profile text: {text}
- Highlights: {highlights}

Respond with ONLY this JSON (no markdown, no explanation):
{{"match": true, "confidence": 0.95, "reason": "one sentence", "current_company": "extracted company name or null", "current_role": "extracted role or null", "graduation_year": "extracted year or null"}}"""


def _get_openrouter_key() -> str:
    """Get the OpenRouter API key from environment or .env file."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    # Try loading from .env via dotenv (already loaded by config module)
    from dotenv import load_dotenv
    from pathlib import Path
    for env_path in [Path.cwd() / ".env", Path(__file__).parent.parent.parent / ".env"]:
        if env_path.exists():
            load_dotenv(env_path)
            key = os.environ.get("OPENROUTER_API_KEY", "")
            if key:
                return key
    raise RuntimeError(
        "OPENROUTER_API_KEY not found. Set it in .env or as an environment variable."
    )


def _build_criteria(query: str, filter_config: dict | None = None) -> str:
    """Build filter criteria string from query or config."""
    if filter_config:
        parts = []
        if filter_config.get("company"):
            aliases = filter_config.get("company_aliases", [])
            company_str = filter_config["company"]
            if aliases:
                company_str += f" (also known as: {', '.join(aliases)})"
            parts.append(f"- Target company: {company_str}")
        if filter_config.get("roles"):
            parts.append(f"- Target roles: {', '.join(filter_config['roles'])}")
        if filter_config.get("graduation_years"):
            years = filter_config["graduation_years"]
            parts.append(f"- Graduation years: {', '.join(str(y) for y in years)}")
        if filter_config.get("require_current"):
            parts.append("- Must be CURRENTLY at the target company (not former)")
        extra = filter_config.get("extra", "")
        if extra:
            parts.append(f"- Additional: {extra}")
        return "\n".join(parts) if parts else query
    return query


def _build_prompt(person: PersonResult, query: str, filter_config: dict | None = None) -> str:
    """Build the classification prompt for a single candidate."""
    criteria = _build_criteria(query, filter_config)
    highlights = " | ".join(person.highlights) if person.highlights else "(none)"
    return FILTER_PROMPT.format(
        criteria=criteria,
        name=person.name,
        title=person.title or "(unknown)",
        text=person.text[:2000] if person.text else "(no profile text available)",
        highlights=highlights,
    )


def _parse_response(text: str) -> FilterResult:
    """Parse the LLM JSON response into a FilterResult."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return FilterResult(match=False, confidence=0.0, reason="Failed to parse LLM response")

    return FilterResult(
        match=bool(data.get("match", False)),
        confidence=float(data.get("confidence", 0.0)),
        reason=str(data.get("reason", "")),
        current_company=data.get("current_company"),
        current_role=data.get("current_role"),
        graduation_year=str(data["graduation_year"]) if data.get("graduation_year") else None,
    )


async def _classify_one(
    client: openai.AsyncOpenAI,
    person: PersonResult,
    query: str,
    filter_config: dict | None,
    semaphore: asyncio.Semaphore,
    max_retries: int = 3,
) -> tuple[PersonResult, FilterResult]:
    """Classify a single candidate with retry logic."""
    prompt = _build_prompt(person, query, filter_config)

    async with semaphore:
        for attempt in range(max_retries):
            try:
                response = await client.chat.completions.create(
                    model="anthropic/claude-haiku-4.5",
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.choices[0].message.content
                result = _parse_response(text)
                return person, result
            except openai.RateLimitError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return person, FilterResult(
                        match=False, confidence=0.0, reason="Rate limited after retries"
                    )
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                else:
                    return person, FilterResult(
                        match=False, confidence=0.0, reason=f"API error: {e}"
                    )
    # Unreachable but satisfies type checker
    return person, FilterResult(match=False, confidence=0.0, reason="Unknown error")


async def filter_candidates_async(
    candidates: list[PersonResult],
    query: str,
    filter_config: dict | None = None,
    confidence_threshold: float = 0.6,
    concurrency: int = 20,
) -> tuple[list[tuple[PersonResult, FilterResult]], list[tuple[PersonResult, FilterResult]]]:
    """Filter candidates using Claude Haiku 4.5.

    Returns (matched, rejected) tuples of (PersonResult, FilterResult).
    """
    api_key = _get_openrouter_key()
    client = openai.AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        _classify_one(client, person, query, filter_config, semaphore)
        for person in candidates
    ]
    results = await asyncio.gather(*tasks)

    matched = []
    rejected = []
    for person, fr in results:
        if fr.match and fr.confidence >= confidence_threshold:
            matched.append((person, fr))
        else:
            rejected.append((person, fr))

    return matched, rejected


def filter_candidates(
    candidates: list[PersonResult],
    query: str,
    filter_config: dict | None = None,
    confidence_threshold: float = 0.6,
    concurrency: int = 20,
) -> tuple[list[tuple[PersonResult, FilterResult]], list[tuple[PersonResult, FilterResult]]]:
    """Synchronous wrapper for filter_candidates_async."""
    return asyncio.run(
        filter_candidates_async(
            candidates, query, filter_config, confidence_threshold, concurrency
        )
    )
