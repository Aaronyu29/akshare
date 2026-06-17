# Research Layer Architecture v0.1

This document defines the first implementation architecture for the A-share and
ETF research layer.

The strategy contract lives in `../research.md`. This file is the engineering
contract: module boundaries, data flow, schemas, cache layout, report shape, and
agent integration.

## Design Goals

- Keep AKShare as the raw market-data adapter, not the strategy engine.
- Keep the deterministic Python pipeline usable without an OpenAI API key.
- Keep agent review optional but first-class for unstructured evidence.
- Generate one Markdown report per research run.
- Cache raw and normalized data from day one.
- Make every output auditable: data source, timestamp, evidence tier, and
  scoring components must be visible.

## Non-Goals For v1

- No live trading.
- No broker integration.
- No automatic order execution.
- No web dashboard.
- No database server.
- No mandatory OpenAI Agents SDK dependency.
- No attempt to fully solve chip-distribution analysis in v1; implement a simple
  metric interface and leave room for richer data later.

## High-Level Flow

```text
User raw context
  -> trigger packet
  -> theme expansion
  -> candidate universe
  -> data enrichment
  -> filters
  -> scoring
  -> agent evidence review, if available
  -> report model
  -> Markdown report
```

There are two supported execution modes:

```text
Manual-agent mode:
  Codex/user prepares trigger and evidence notes
  Python pipeline runs deterministic data/scoring/report steps

SDK-agent mode:
  OpenAI Agents SDK verifies trigger and evidence
  Python tools are exposed as function tools
  The same deterministic pipeline writes the report
```

## Proposed File Structure

```text
research/
  ARCHITECTURE.md
  __init__.py
  cli.py
  config.py
  schemas.py
  cache.py
  data_sources.py
  mappings.py
  universe.py
  enrichment.py
  filters.py
  scoring.py
  report.py
  probe_market_data.py

  agents/
    __init__.py
    sdk_adapter.py
    prompts.py
    schemas.py

  tools/
    __init__.py
    market_tools.py
    scoring_tools.py
    report_tools.py

  cache/
    raw/
    normalized/
    evidence/

  reports/
```

`cache/` and `reports/` should be git-ignored after implementation starts.

## Module Responsibilities

### `config.py`

Owns defaults that should be easy to change:

- Market scope: A-share and China ETFs.
- Hard exclusions: BSE and ST.
- Core candidate target: 3 names.
- Maximum core candidates: 8 names.
- Default RSI overheating threshold: configurable.
- Cache TTLs.
- Report output directory.
- Score weights.

### `schemas.py`

Defines typed data contracts used by the deterministic pipeline.

Use dataclasses in v1 to avoid adding a dependency. If the Agents SDK layer needs
Pydantic models later, add them under `research/agents/schemas.py`.

Core schemas:

- `ResearchRequest`
- `TriggerPacket`
- `ThemeNode`
- `Candidate`
- `CandidateEvidence`
- `CandidateMetrics`
- `CandidateScore`
- `EtfCandidate`
- `TradingPlan`
- `ResearchReport`

### `cache.py`

Provides filesystem cache helpers:

- Save raw provider responses.
- Save normalized DataFrames.
- Save evidence snippets.
- Load cache by key.
- Expire by TTL.
- Record provider, fetch time, params hash, and row count.

Cache keys should be deterministic:

```text
{namespace}/{provider}/{dataset}/{params_hash}.{ext}
```

Examples:

```text
cache/raw/eastmoney/a_stock_spot/20260617.json
cache/normalized/sina/a_stock_spot/20260617.parquet
cache/evidence/NVDA/liquid_cooling/20260617.json
```

If parquet support is inconvenient, start with CSV or JSON. Do not block v1 on
storage format.

### `data_sources.py`

Already exists. Keep it focused on provider fallback and raw data access.

Rules:

- Prefer Eastmoney when stable and richer.
- Fall back to Sina, THS, or Tencent.
- Return provider name with data.
- Never silently swallow all provider failures.

### `mappings.py`

Curated mapping layer from US tickers and keywords to China themes.

Responsibilities:

- Map `NVDA` to AI server, optical modules, liquid cooling, PCB, advanced
  packaging, semiconductor equipment.
- Map aliases and bilingual terms.
- Keep human-curated mappings separate from AKShare raw data.

Example shape:

```python
THEME_MAPPINGS = {
    "NVDA": {
        "themes": ["ai_server", "optical_module", "liquid_cooling"],
        "keywords": ["Blackwell", "HBM", "CPO", "PCB"],
    }
}
```

### `universe.py`

Builds the candidate universe.

Inputs:

- `ResearchRequest`
- `TriggerPacket`
- mappings
- AKShare industry boards
- AKShare concept boards
- ETF names and themes

Outputs:

- Stock candidates with provenance.
- ETF candidates with provenance.

Candidate provenance must include:

- Matched keyword.
- Matched board or source.
- Provider.
- Timestamp.
- Whether the candidate came from curated mapping or raw keyword search.

### `enrichment.py`

Adds metrics and evidence to candidates.

Possible data:

- Latest quote.
- Recent price history.
- RSI and recent return.
- Turnover and amount.
- Financial indicators.
- Fund flow.
- Shareholder count if available.
- ETF fee, size, turnover, and tracking index.

The module should be allowed to return partial data. Missing metrics should
become warnings, not fatal errors.

### `filters.py`

Applies hard exclusions and soft risk flags.

Hard exclusions:

- BSE.
- ST.
- Serious black-history issues when confirmed.

Soft flags:

- RSI overheating.
- Recent return overheating.
- Excessive turnover/crowding.
- Weak liquidity.
- Weak or soft-only evidence.
- Governance or disclosure concerns that are not hard exclusions.

Do not delete soft-flagged candidates too early. Keep them for watchlist or avoid
sections so the report explains why they are not actionable.

### `scoring.py`

Computes transparent component scores.

Default components:

```text
theme_relevance: 0-30
revenue_order_evidence: 0-25
chip_structure: 0-15
tradability: 0-15
speculative_potential: 0-15
risk_penalty: -30-0
```

Total:

```text
total = theme_relevance
      + revenue_order_evidence
      + chip_structure
      + tradability
      + speculative_potential
      + risk_penalty
```

Every score must expose a short rationale.

### `report.py`

Turns the report model into Markdown.

Required sections:

- Header and run metadata.
- User input / trigger packet.
- US-side trigger summary.
- Theme tree.
- Core stock candidates, usually 3 names.
- Watchlist.
- Avoid / overheated.
- Avoid / black-history.
- ETF implementation table.
- Evidence notes.
- Entry, take-profit, and stop-loss conditions.
- Data-source warnings.
- Follow-up checks.

Filename:

```text
research/reports/{US_SYMBOL}_{theme_slug}_{YYYYMMDD_HHMMSS}.md
```

### `cli.py`

First interface. Keep it simple.

Suggested commands:

```text
python -m research.cli run --us NVDA --keywords "Blackwell,liquid cooling,HBM"
python -m research.cli probe
python -m research.cli show-config
```

Input can also be a text file:

```text
python -m research.cli run --input research/inputs/nvda.txt
```

The CLI should call the same internal pipeline that an agent would call.

## Agent SDK Boundary

The OpenAI Agents SDK integration should live behind `research/agents/sdk_adapter.py`.

The deterministic pipeline must not import the Agents SDK directly.

### Agent Inputs

The agent receives:

- Raw user context.
- Optional US ticker.
- Optional keywords.
- Optional source links or pasted snippets.

### Agent Outputs

The agent should produce a structured `TriggerPacket`:

```text
us_symbol
trigger_date
trigger_type
trigger_summary
price_move
earnings_points
news_points
social_points
affected_supply_chain_links
confidence
sources
```

The agent can also produce `CandidateEvidence`:

```text
symbol
evidence_tier
customer_or_order_summary
estimated_exposure
source_quality
risks
sources
```

### Python Tools Exposed To Agents

Initial tool list:

- `fetch_a_stock_spot`
- `fetch_etf_spot`
- `build_candidate_universe`
- `enrich_candidates`
- `score_candidates`
- `write_markdown_report`

Do not expose broad shell access as an agent tool in v1.

## Report Schema

Minimal report model:

```text
ResearchReport
  request
  trigger_packet
  theme_tree
  core_candidates[]
  watchlist[]
  avoid_overheated[]
  avoid_black_history[]
  etf_candidates[]
  data_warnings[]
  follow_up_checks[]
```

Candidate row:

```text
symbol
name
market
matched_theme
score_total
score_components
evidence_tier
evidence_summary
risk_flags
entry_conditions
take_profit_conditions
stop_loss_conditions
data_sources
```

ETF row:

```text
code
name
theme
tracking_index
management_fee
custody_fee
fund_size
turnover
premium_discount
top_holdings
use_case
data_sources
```

## Cache Policy

Suggested TTLs:

- Spot quotes: same trading day.
- Historical daily bars: 1 day.
- ETF fees and fund profiles: 7 days.
- Board constituents: 1 day.
- Financial indicators: 7 days.
- Evidence snippets: 30 days, but refresh when the user asks for latest.

Every cached object should include metadata:

```text
provider
dataset
params
fetched_at
ttl_seconds
row_count
schema_version
```

## Technical Filters

Initial mechanical filters:

- RSI.
- Recent 5-day and 20-day return.
- Turnover amount.
- Volume expansion.
- Price distance from moving averages.
- ETF liquidity and fund size.

Overheating should be a combined flag, not just RSI:

```text
overheated = RSI high
          or recent return extreme
          or volume/turnover crowding extreme
          or theme board heat too high
```

Exact thresholds should stay configurable.

## Testing Plan

Unit tests:

- Cache key generation.
- Score calculation.
- Hard exclusions.
- Soft flag classification.
- Report rendering.
- Provider fallback behavior with mocked failures.

Smoke tests:

- Existing `probe_market_data.py`.
- One dry-run report with a small hand-written trigger packet.

No tests should require live OpenAI API calls in v1.

## Implementation Order

1. Add `.gitignore` entries for `research/cache/` and `research/reports/`.
2. Add schemas and config.
3. Add cache helpers.
4. Add mapping table for `NVDA`.
5. Add universe builder.
6. Add technical filters and scoring.
7. Add Markdown report renderer.
8. Add CLI.
9. Add smoke test for one dry run.
10. Add optional Agents SDK adapter.

## Open Design Decisions

- Exact RSI and overheating thresholds.
- Which AKShare endpoint best supports chip profit/loss distribution.
- Whether ETF fee data is reliable from AKShare alone or needs a second source.
- Whether black-history checks start as manual agent notes or structured data.
- Whether reports should include CSV sidecars later.
