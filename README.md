# exa-recruit

CLI tool for searching candidate profiles using [Exa AI People Search](https://exa.ai/docs/changelog/people-search-launch).

Search with natural language queries like "cybersecurity engineers at Google with 5+ years experience" and get results with LinkedIn profiles, titles, and highlights — automatically saved to CSV.

## Setup

```bash
# Clone and install
cd ~/repos
git clone https://github.com/mvg9999/exa-recruit.git
cd exa-recruit
pip install -e .

# Configure API key
cp .env.example .env
# Edit .env and add your Exa API key (get one at https://dashboard.exa.ai/api-keys)
```

## Usage

### Search for candidates

```bash
# Basic search
exa-recruit search "cybersecurity engineers at Google"

# More results with location bias
exa-recruit search "ML engineers in San Francisco" -n 25 -l US

# Terminal only (no CSV)
exa-recruit search "VP of Sales at SaaS startups" --no-csv

# JSON output (for agent/script consumption)
exa-recruit search "product managers at Stripe" --json

# Deep search with full profile text
exa-recruit search "founding engineers at YC startups" -t deep --include-text
```

### View search history

```bash
exa-recruit history              # Last 10 searches
exa-recruit history -n 50        # Last 50
exa-recruit history -q "Google"  # Filter by query
```

### Configuration

```bash
exa-recruit config show   # Show config (API key redacted)
exa-recruit config test   # Test Exa API connectivity
```

## Output

Results are saved as CSV files in `./output/` (auto-created). Filenames are generated from the query and date:

```
output/cybersecurity-engineers-google-2026-02-17.csv
```

CSV columns: timestamp, name, linkedin_url, title, query, highlights

## Costs

~$0.025 per search (10 results with highlights). Exa gives $10 free credits to start.

## Agent Integration

Use `--json` for structured output that can be parsed by scripts or AI agents:

```bash
exa-recruit search "senior engineers" --json | jq '.results[].name'
```
