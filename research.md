# Research Layer v0.1

This document defines the research layer we will build on top of AKShare for
tracking US stock themes and mapping them to A-share domestic-substitution
opportunities.

## Questions For You

1. Coverage: should the first version cover only A-shares and China ETFs, or also
   include Hong Kong stocks?
2. Holding period: is the default target 3-6 months, 6-12 months, or flexible by
   theme?
3. Risk filter: should we exclude ST stocks, Beijing Stock Exchange stocks,
   ChiNext, STAR Market, loss-making companies, or very small market caps?
4. Position style: do you prefer concentrated stock picks, ETF-first exposure, or
   a mix of stocks plus ETFs?
5. Signal priority: should we rank candidates more by theme relevance, recent
   momentum, valuation, fundamentals, or liquidity?
6. Verification depth: for each candidate, do you want quick evidence only
   through market/sector data, or deeper checks using announcements, financials,
   fund flows, and research reports?
7. US trigger: when you provide a US stock and keywords, should we also fetch US
   price/news/financial data, or treat your prompt as the only US-side trigger?
8. Output format: do you want terminal tables, CSV files, Markdown reports, or a
   small local web dashboard later?
9. Update cadence: should the system be run on demand, daily after A-share close,
   weekly, or around US earnings events?
10. Decision boundary: should the tool only produce research candidates, or also
    produce suggested watchlist weights and buy/sell conditions?

## Goal

Given a US stock and a set of theme keywords, generate a research pack containing:

- US-side trigger summary.
- Theme and supply-chain breakdown.
- A-share stock candidates.
- China ETF candidates.
- Evidence, risks, and follow-up checks.
- A clear tracking hypothesis for each candidate.

The tool is for research and screening. It should not place trades or present
results as financial advice.

## Example Input

```text
US stock: NVDA
Keywords: Blackwell, AI server, liquid cooling, HBM, optical modules, advanced packaging
Holding period: 3-6 months
Risk preference: medium
Market scope: A-shares + China ETFs
Exclude: ST stocks, illiquid micro caps
```

## Research Pipeline

### 1. Normalize Input

Convert user input into a structured request:

- `us_symbol`: US stock ticker, for example `NVDA`.
- `keywords`: explicit theme keywords.
- `holding_period`: intended holding window.
- `risk_profile`: conservative, medium, or aggressive.
- `market_scope`: A-share, ETF, Hong Kong, or mixed.
- `exclusions`: boards, risk flags, liquidity thresholds, valuation limits.

### 2. Expand Theme

Map keywords into an investable theme tree:

- Upstream materials.
- Equipment and tools.
- Core components.
- Manufacturing and assembly.
- Infrastructure and systems.
- Downstream applications.
- Domestic-substitution angle.

Example:

```text
NVDA -> AI accelerator cycle
  -> AI server
  -> high-speed interconnect
  -> optical modules
  -> PCB and copper clad laminate
  -> liquid cooling
  -> power supply
  -> advanced packaging
  -> semiconductor equipment and materials
```

### 3. Fetch Data

Use AKShare as the raw data layer.

Current local wrappers:

- `research/data_sources.py`
  - `fetch_a_stock_spot()`: Eastmoney first, Sina fallback.
  - `fetch_etf_spot()`: Eastmoney first, THS fallback.
- `research/probe_market_data.py`
  - Smoke test for A-share and ETF data providers.

Candidate AKShare interfaces:

- A-share spot and history:
  - `stock_zh_a_spot_em`
  - `stock_zh_a_spot`
  - `stock_zh_a_daily`
  - `stock_zh_a_hist_tx`
- ETF spot and history:
  - `fund_etf_spot_em`
  - `fund_etf_spot_ths`
  - `fund_etf_hist_em`
  - `fund_etf_hist_sina`
- Industry and concept boards:
  - `stock_board_industry_name_em`
  - `stock_board_industry_cons_em`
  - `stock_board_concept_name_em`
  - `stock_board_concept_cons_em`
- Fundamentals and verification:
  - `stock_financial_analysis_indicator`
  - `stock_financial_report_sina`
  - `stock_balance_sheet_by_report_em`
  - `stock_profit_sheet_by_report_em`
  - `stock_cash_flow_sheet_by_report_em`
- Sentiment and activity:
  - `stock_hot_rank_em`
  - `stock_individual_fund_flow_rank`
  - `stock_sector_fund_flow_rank`
  - `stock_news_em`
  - `stock_notice_report`
  - `stock_research_report_em`

### 4. Build Candidate Universe

Sources for candidates:

- Concept board constituents.
- Industry board constituents.
- ETF names and ETF themes.
- Keyword search over stock names, ETF names, concept names, and industry names.
- Optional manually curated mappings for high-value themes.

Each candidate should carry provenance:

- Source provider.
- Matched keyword.
- Matched board or ETF theme.
- Data timestamp.

### 5. Score Candidates

Initial scoring dimensions:

| Dimension | Meaning | Default Weight |
| --- | --- | --- |
| Theme relevance | How directly the company/ETF maps to the US trigger | 35 |
| Domestic substitution | Whether the candidate benefits from local replacement | 20 |
| Market confirmation | Price strength, volume, fund flow, board strength | 15 |
| Fundamentals | Revenue/profit quality, margins, balance sheet | 15 |
| Liquidity | Turnover and tradability | 10 |
| Risk penalty | ST, extreme valuation, poor liquidity, weak disclosure | -20 to 0 |

Default total score:

```text
score = relevance + substitution + market + fundamentals + liquidity - risk_penalty
```

### 6. Classify Results

Each result should be grouped into:

- `core candidate`: strong direct mapping and acceptable data quality.
- `watchlist`: plausible mapping but needs more verification.
- `ETF exposure`: broad theme exposure when stock risk is high.
- `avoid / concept-only`: weak evidence or mostly hype.

### 7. Generate Research Pack

Output should include:

- Short thesis.
- Candidate table.
- ETF table.
- Evidence notes.
- Risks.
- Holding hypothesis.
- Follow-up checks.
- Data-source notes.

Example candidate row:

| Symbol | Name | Match | Score | Evidence | Risk | Hypothesis |
| --- | --- | --- | ---: | --- | --- | --- |
| 000000 | Example Co | liquid cooling | 78 | Concept board + turnover + revenue clue | valuation high | Watch next two quarters for AI server orders |

## Data Quality Rules

- Always mark data provider and timestamp when possible.
- Prefer Eastmoney for richer fields, but keep fallback providers.
- Do not silently mix incompatible units.
- Cache raw pulls before scoring when the pipeline becomes larger.
- Treat failed providers as warnings, not hard failures, unless all providers fail.
- Keep manually curated mappings separate from raw AKShare data.

## Project Structure

Proposed structure:

```text
research/
  data_sources.py        # provider wrappers and fallback logic
  probe_market_data.py   # smoke tests
  mappings.py            # US ticker / keyword -> China theme mappings
  universe.py            # stock and ETF candidate universe builders
  scoring.py             # scoring rules
  report.py              # Markdown/CSV output
  cli.py                 # command-line entry point
```

## Near-Term Milestones

1. Finalize your answers to the questions above.
2. Add a small curated mapping table for the first 5-10 US tickers.
3. Implement keyword-to-board matching.
4. Generate a first Markdown report for one example, likely `NVDA`.
5. Add CSV export for candidate tables.
6. Add cache files for raw data pulls.
7. Add tests for scoring and fallback behavior.

## First Themes To Support

Suggested initial watchlist:

- `NVDA`: AI server, optical module, liquid cooling, PCB, advanced packaging.
- `TSLA`: FSD, robotics, energy storage, power electronics.
- `ASML`: semiconductor equipment, lithography chain, materials.
- `AMD`: AI GPU, server, advanced packaging.
- `PLTR`: AI application, data security, software localization.
- `LLY` / `NVO`: GLP-1, peptide, pharmaceutical CDMO.
- `ISRG`: surgical robot, high-end medical equipment.
