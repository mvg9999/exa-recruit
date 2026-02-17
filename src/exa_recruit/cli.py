"""CLI entry point for exa-recruit."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .cache import get_history, save_search
from .config import get_api_key
from .export import export_csv
from .searcher import search_people

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
) -> None:
    """Search for people and save results."""
    if num_results < 1 or num_results > 100:
        console.print("[red]Error: --num-results must be between 1 and 100[/red]")
        raise SystemExit(1)

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

    # CSV export
    csv_path = None
    if not no_csv:
        csv_path = export_csv(response, output_dir=output_dir)

    # JSON output mode
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

    # Rich table output
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
    try:
        key = get_api_key()
        redacted = key[:8] + "..." + key[-4:]
        console.print(f"EXA_API_KEY: {redacted}")
    except SystemExit:
        console.print("[red]EXA_API_KEY: not set[/red]")


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
