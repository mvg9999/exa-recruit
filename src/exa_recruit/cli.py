"""CLI entry point for exa-recruit."""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .cache import get_history, save_search
from .config import get_api_key
from .export import export_csv, export_filtered_csv
from .searcher import PersonResult, search_people

app = typer.Typer(
    name="exa-recruit",
    help="Search for candidate profiles using Exa AI People Search.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Natural language search query")],
    num_results: Annotated[int, typer.Option("--num-results", "-n", help="Number of results (1-100)")] = 10,
    output_dir: Annotated[str, typer.Option("--output-dir", "-o", help="Directory for CSV files")] = "./output",
    search_type: Annotated[str, typer.Option("--search-type", "-t", help="Search type: auto, neural, fast, deep, instant")] = "auto",
    location: Annotated[Optional[str], typer.Option("--location", "-l", help="ISO country code for result biasing")] = None,
    no_csv: Annotated[bool, typer.Option("--no-csv", help="Skip CSV export")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON (for agent consumption)")] = False,
    include_text: Annotated[bool, typer.Option("--include-text", help="Include full profile text")] = False,
    no_filter: Annotated[bool, typer.Option("--no-filter", help="Disable LLM filtering")] = False,
    strict: Annotated[bool, typer.Option("--strict", help="Strict filtering (0.8 confidence threshold)")] = False,
    filter_config: Annotated[Optional[str], typer.Option("--filter-config", help="Path to JSON filter config file")] = None,
) -> None:
    """Search for people and save results."""
    if num_results < 1 or num_results > 100:
        console.print("[red]Error: --num-results must be between 1 and 100[/red]")
        raise SystemExit(1)

    filtering_enabled = not no_filter

    # Auto-enable include_text when filtering is on (LLM needs profile text)
    if filtering_enabled and not include_text:
        include_text = True

    if not json_output:
        console.print(f"[dim]Searching for:[/dim] {query}")

    try:
        response = search_people(
            query=query,
            num_results=num_results,
            search_type=search_type,
            location=location,
            include_text=include_text,
        )
    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]API error: {e}[/red]")
        raise SystemExit(1)

    if not response.results:
        if json_output:
            print(json.dumps({"query": query, "num_results": 0, "results": []}))
        else:
            console.print("[yellow]No results found.[/yellow]")
        raise SystemExit(3)

    # Save to cache
    save_search(response)

    # Apply LLM filtering
    if filtering_enabled:
        from .filter import filter_candidates

        config_data = None
        if filter_config:
            config_data = json.loads(Path(filter_config).read_text())

        threshold = 0.8 if strict else 0.6

        if not json_output:
            console.print(f"[dim]Filtering {len(response.results)} candidates with LLM...[/dim]")

        try:
            matched, rejected = filter_candidates(
                response.results, query, filter_config=config_data,
                confidence_threshold=threshold,
            )
        except RuntimeError as e:
            console.print(f"[red]Filter error: {e}[/red]")
            raise SystemExit(1)

        if not json_output:
            mode = "strict" if strict else "normal"
            console.print(
                f"[dim]Filtered: {len(response.results)} → {len(matched)} candidates "
                f"({len(rejected)} rejected, {mode} mode)[/dim]"
            )

        # CSV export (filtered)
        csv_path = None
        rejected_path = None
        if not no_csv:
            csv_path, rejected_path = export_filtered_csv(
                matched, rejected, query, output_dir=output_dir,
            )

        # JSON output mode
        if json_output:
            output = {
                "query": response.query,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_results": len(response.results),
                "filtered_results": len(matched),
                "rejected": len(rejected),
                "confidence_threshold": threshold,
                "cost_dollars": response.cost_dollars,
                "results": [
                    {
                        "name": p.name,
                        "linkedin_url": p.linkedin_url,
                        "title": p.title,
                        "highlights": p.highlights,
                        "match": fr.match,
                        "confidence": fr.confidence,
                        "reason": fr.reason,
                        "current_company": fr.current_company,
                        "current_role": fr.current_role,
                        "graduation_year": fr.graduation_year,
                    }
                    for p, fr in matched
                ],
            }
            if csv_path:
                output["csv_path"] = str(csv_path)
            if rejected_path:
                output["rejected_csv_path"] = str(rejected_path)
            print(json.dumps(output, indent=2))
            return

        # Rich table output
        table = Table(title=f"Filtered results for: {query}")
        table.add_column("Name", style="bold cyan", max_width=25)
        table.add_column("Title", max_width=30)
        table.add_column("Confidence", justify="right", max_width=10)
        table.add_column("Reason", max_width=45)

        for person, fr in matched:
            conf_style = "green" if fr.confidence >= 0.8 else "yellow"
            table.add_row(
                person.name,
                person.title[:30] if person.title else "",
                f"[{conf_style}]{fr.confidence:.0%}[/{conf_style}]",
                fr.reason[:45] if fr.reason else "",
            )

        console.print(table)

        if csv_path:
            console.print(f"\n[green]✓[/green] {len(matched)} matched saved to {csv_path}")
        if rejected_path:
            console.print(f"[dim]{len(rejected)} rejected saved to {rejected_path}[/dim]")
        if response.cost_dollars:
            console.print(f"[dim]Exa cost: ${response.cost_dollars:.4f}[/dim]")

    else:
        # No filtering — original behavior
        csv_path = None
        if not no_csv:
            csv_path = export_csv(response, output_dir=output_dir)

        if json_output:
            output = {
                "query": response.query,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "num_results": len(response.results),
                "cost_dollars": response.cost_dollars,
                "results": [
                    {
                        "name": r.name,
                        "linkedin_url": r.linkedin_url,
                        "title": r.title,
                        "highlights": r.highlights,
                    }
                    for r in response.results
                ],
            }
            if csv_path:
                output["csv_path"] = str(csv_path)
            print(json.dumps(output, indent=2))
            return

        table = Table(title=f"Results for: {query}")
        table.add_column("Name", style="bold cyan", max_width=25)
        table.add_column("LinkedIn URL", style="blue", max_width=40)
        table.add_column("Title", max_width=35)
        table.add_column("Highlights", max_width=40)

        for person in response.results:
            highlight_text = person.highlights[0][:80] + "..." if person.highlights else ""
            table.add_row(
                person.name,
                person.linkedin_url,
                person.title[:35] if person.title else "",
                highlight_text,
            )

        console.print(table)

        if csv_path:
            console.print(f"\n[green]✓[/green] {len(response.results)} results saved to {csv_path}")
        if response.cost_dollars:
            console.print(f"[dim]Cost: ${response.cost_dollars:.4f}[/dim]")


@app.command("filter")
def filter_cmd(
    csv_file: Annotated[str, typer.Argument(help="Path to CSV file to filter")],
    query: Annotated[str, typer.Option("--query", "-q", help="Search criteria for filtering")] = "",
    output_dir: Annotated[Optional[str], typer.Option("--output-dir", "-o", help="Output directory (default: same as input)")] = None,
    strict: Annotated[bool, typer.Option("--strict", help="Strict filtering (0.8 confidence threshold)")] = False,
    filter_config: Annotated[Optional[str], typer.Option("--filter-config", help="Path to JSON filter config file")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Re-filter an existing CSV file using LLM classification."""
    from .filter import filter_candidates

    csv_path = Path(csv_file)
    if not csv_path.exists():
        console.print(f"[red]Error: File not found: {csv_file}[/red]")
        raise SystemExit(1)

    # Read candidates from CSV (handle both lowercase and Title Case column names)
    candidates = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize column names to lowercase for lookup
            lrow = {k.lower().replace(" ", "_"): v for k, v in row.items()}
            highlights_raw = lrow.get("highlights", "")
            text_raw = lrow.get("text", "") or lrow.get("text_snippet", "")
            candidates.append(PersonResult(
                name=lrow.get("name", ""),
                linkedin_url=lrow.get("linkedin_url", ""),
                title=lrow.get("title", ""),
                highlights=highlights_raw.split(" | ") if highlights_raw else [],
                text=text_raw,
            ))

    if not candidates:
        console.print("[yellow]No candidates found in CSV.[/yellow]")
        raise SystemExit(3)

    # Use query from CSV if not provided
    if not query:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            first_row = next(reader, None)
            if first_row:
                lrow = {k.lower(): v for k, v in first_row.items()}
                if lrow.get("query"):
                    query = lrow["query"]
        if not query:
            console.print("[red]Error: No --query provided and no query column in CSV.[/red]")
            raise SystemExit(1)

    config_data = None
    if filter_config:
        config_data = json.loads(Path(filter_config).read_text())

    threshold = 0.8 if strict else 0.6
    out_dir = output_dir or str(csv_path.parent)

    if not json_output:
        console.print(f"[dim]Filtering {len(candidates)} candidates from {csv_path.name}...[/dim]")

    try:
        matched, rejected = filter_candidates(
            candidates, query, filter_config=config_data,
            confidence_threshold=threshold,
        )
    except RuntimeError as e:
        console.print(f"[red]Filter error: {e}[/red]")
        raise SystemExit(1)

    matched_path, rejected_path = export_filtered_csv(
        matched, rejected, query, output_dir=out_dir,
    )

    if json_output:
        output = {
            "input_file": str(csv_path),
            "query": query,
            "total_candidates": len(candidates),
            "matched": len(matched),
            "rejected": len(rejected),
            "confidence_threshold": threshold,
            "matched_csv": str(matched_path),
            "rejected_csv": str(rejected_path) if rejected_path else None,
        }
        print(json.dumps(output, indent=2))
        return

    mode = "strict" if strict else "normal"
    console.print(
        f"\n[green]✓[/green] Filtered: {len(candidates)} → {len(matched)} candidates "
        f"({len(rejected)} rejected, {mode} mode)"
    )
    console.print(f"  Matched: {matched_path}")
    if rejected_path:
        console.print(f"  Rejected: {rejected_path}")


@app.command()
def history(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of entries to show")] = 10,
    query: Annotated[Optional[str], typer.Option("--query", "-q", help="Filter by query text")] = None,
) -> None:
    """View past searches from local cache."""
    entries = get_history(limit=limit, query_filter=query)

    if not entries:
        console.print("[yellow]No search history found.[/yellow]")
        return

    table = Table(title="Search History")
    table.add_column("ID", style="dim")
    table.add_column("Time", style="cyan")
    table.add_column("Query", style="bold")
    table.add_column("Results", justify="right")
    table.add_column("Cost", justify="right", style="green")

    for entry in entries:
        ts = entry["timestamp"][:16].replace("T", " ")
        cost = f"${entry['cost_dollars']:.4f}" if entry["cost_dollars"] else "-"
        table.add_row(
            str(entry["id"]),
            ts,
            entry["query"],
            str(entry["num_results"]),
            cost,
        )

    console.print(table)


config_app = typer.Typer(help="Manage configuration.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """Show current configuration (API keys redacted)."""
    from .config import get_openrouter_key

    try:
        key = get_api_key()
        redacted = key[:8] + "..." + key[-4:]
        console.print(f"EXA_API_KEY: {redacted}")
    except SystemExit:
        console.print("[red]EXA_API_KEY: not set[/red]")

    try:
        key = get_openrouter_key()
        redacted = key[:8] + "..." + key[-4:]
        console.print(f"OPENROUTER_API_KEY: {redacted}")
    except SystemExit:
        console.print("[red]OPENROUTER_API_KEY: not set (required for filtering)[/red]")


@config_app.command("test")
def config_test() -> None:
    """Test Exa API connectivity."""
    console.print("[dim]Testing Exa API connection...[/dim]")
    try:
        response = search_people("software engineer", num_results=1, search_type="instant")
        console.print(f"[green]✓[/green] Exa API connected — got {len(response.results)} result(s)")
        if response.cost_dollars:
            console.print(f"[dim]Test cost: ${response.cost_dollars:.4f}[/dim]")
    except Exception as e:
        console.print(f"[red]✗ Exa API error: {e}[/red]")
        raise SystemExit(1)


@app.command()
def version() -> None:
    """Show version."""
    console.print(f"exa-recruit v{__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
