# Research Layer v0.2

This document defines the research layer we will build on top of AKShare for
tracking US stock themes and mapping them to A-share domestic-substitution
opportunities.

## Confirmed Preferences

- Coverage: A-shares and China ETFs only.
- Holding period: several weeks to several months.
- Exclusions: Beijing Stock Exchange stocks and ST stocks.
- Allowed boards: main board, ChiNext, STAR Market, and other non-BSE A-share
  boards unless they are ST.
- Position style: concentrated stock picks, with ETFs as supporting references or
  backup exposure.
- Signal priority: theme relevance first, then revenue/order evidence, ownership
  and chip structure, tradability, and speculative potential.
- Revenue/order evidence: for a supply-chain company, orders or revenue from the
  relevant foreign-listed customer should ideally be 30% or more of related
  revenue, total revenue, or disclosed major-customer exposure. This is a strong
  positive signal, not a hard requirement for core candidacy.
- Large-order catalyst: if a company wins a very large order that can materially
  lift revenue or profit growth, this should receive a high evidence score even
  when historical customer exposure is below 30%.
- Core candidate count: keep it highly selective, usually around 3 core names.
- ETF requirement: every report must include actionable ETF choices. If
  individual-stock conviction is weak, ETFs become the fallback implementation.
  ETF reports must include fees and other practical trading details.
- US trigger: the user can provide US-side context directly, including price
  moves, earnings, company news, social-media discussion, and other catalyst
  notes. The agent should then search externally, verify, summarize, and feed the
  structured trigger into the program.
- A-share overheating filter: avoid candidates with excessively high RSI,
  overheated speculation, or obvious short-term crowding.
- Black-history filter: avoid companies with serious past issues, including
  fraud, regulatory penalties, repeated disclosure problems, major governance
  concerns, or other red flags.
- Report trading plan: every report must include entry conditions, take-profit
  conditions, and stop-loss / invalidation conditions.
- Output format: Markdown reports first.
- Implementation timing: finish research design discussion before writing more
  code.

## Open Questions

1. Which evidence sources should count as valid customer/order proof:
   annual-report top customers, interim reports, announcements, research reports,
   investor relations Q&A, supply-chain teardown, or media reports?
2. For tradability, what minimum liquidity do you want: daily turnover amount,
   market cap, average volume, or no hard threshold in v1?
3. For speculative potential, should we score catalysts such as earnings,
   product launches, policy events, US stock earnings, or A-share theme heat?
4. Should the report include an explicit "do not buy / avoid" section for concept
   names that look noisy or overhyped?
5. For RSI and overheating, what default threshold should we use later: RSI > 70,
   RSI > 75, or a combined rule using RSI, recent涨幅, turnover, and board heat?

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
Holding period: several weeks to several months
Risk preference: medium
Market scope: A-shares + China ETFs
Exclude: ST stocks, Beijing Stock Exchange stocks
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

### 2.5. Verify US Trigger

The user may provide raw US-side trigger material directly:

- US stock price move and magnitude.
- Earnings growth, guidance, and margin changes.
- Company press releases.
- Product launches.
- News and industry reports.
- Social-media discussion and market narratives.

Agent responsibility:

- Search externally when needed.
- Verify dates, source quality, and whether the trigger is new or already priced
  in.
- Extract the affected supply-chain links.
- Convert unstructured context into structured fields for the Python pipeline.

The local program should not be expected to independently understand all
unstructured US-side context. It should receive a cleaned trigger packet from the
agent.

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
| Theme relevance | How directly the company/ETF maps to the US trigger | 30 |
| Revenue/order evidence | Whether the theme is visible in revenue, orders, customers, or capacity; 30%+ relevant customer/order exposure or a large revenue-moving order is a major positive signal | 25 |
| Chip structure | Profit/loss holder distribution, its change speed, and whether profitable chips are becoming more concentrated | 15 |
| Tradability | Liquidity, volatility, entry/exit practicality, and market depth | 15 |
| Speculative potential | Catalyst density, narrative clarity, and theme heat | 15 |
| Risk penalty | ST, BSE, RSI overheating, excessive speculation, weak disclosure, black-history issues, extreme valuation, or poor liquidity | -30 to 0 |

Default total score:

```text
score = relevance + revenue_orders + chip_structure + tradability + speculation - risk_penalty
```

### 6. Classify Results

Each result should be grouped into:

- `core candidate`: strong direct mapping and acceptable data quality.
- `watchlist`: plausible mapping but needs more verification.
- `ETF implementation`: actionable ETF exposure and benchmark when stock
  conviction is weak or when a basket is more practical.
- `avoid / concept-only`: weak evidence or mostly hype.
- `avoid / overheated`: strong theme but RSI,涨幅, turnover, or crowding suggests
  poor entry timing.
- `avoid / black-history`: serious historical governance, fraud, disclosure,
  penalty, or credibility issues.

### 7. Generate Research Pack

Output should include:

- Short thesis.
- Concentrated stock candidate table.
- ETF implementation table.
- Evidence notes.
- Risks.
- Holding hypothesis.
- Entry conditions.
- Take-profit conditions.
- Stop-loss and invalidation conditions.
- Follow-up checks.
- Data-source notes.

Example candidate row:

| Symbol | Name | Match | Score | Evidence | Risk | Hypothesis |
| --- | --- | --- | ---: | --- | --- | --- |
| 000000 | Example Co | liquid cooling | 78 | Concept board + turnover + revenue clue | valuation high | Watch next two quarters for AI server orders |

Example trading-plan row:

| Symbol | Entry Conditions | Take Profit | Stop Loss / Invalidation |
| --- | --- | --- | --- |
| 000000 | RSI cools down, price holds key support, volume contracts after theme pullback | Theme reaches crowded phase, valuation rerates sharply, or catalyst is priced in | Order evidence is disproved, price breaks support, or sector heat collapses |

Example ETF row:

| Code | Name | Theme | Fee Notes | Size/Liquidity | Tracking | Use Case |
| --- | --- | --- | --- | --- | --- | --- |
| 000000 | Example ETF | semiconductor equipment | management fee + custody fee required | turnover and fund size required | index and tracking quality required | fallback when single-stock evidence is weak |

## Evidence Standards

Revenue and order evidence should be separated into tiers:

- `hard evidence`: annual reports, interim reports, announcements, disclosed top
  customers, signed contracts, order books, capacity dedicated to a named
  customer, or audited segment revenue.
- `medium evidence`: investor relations Q&A, research reports, channel checks,
  supply-chain clues, product certification, customer qualification, or public
  bidding/procurement information.
- `soft evidence`: concept-board membership, market rumors, media narratives,
  vague "serves leading overseas customers" language, or thematic association
  without numeric support.

For supply-chain companies, the ideal evidence is a named or strongly verifiable
foreign-listed customer where the related order or revenue exposure is 30% or
more. This is a strong positive signal rather than a hard cutoff. If exact
exposure is unavailable, the report must say so and downgrade the evidence tier.

Large-order exceptions should be allowed. If a single new order or customer win
can drive a clear step-change in revenue, margin, capacity utilization, or profit
growth, the report should highlight it even before it becomes a 30% historical
customer exposure.

## Agent And Python Boundary

The local Python layer can handle:

- Data fetching from AKShare and other structured sources.
- Normalizing stock, ETF, board, financial, and quote data.
- Caching raw data.
- Keyword matching and candidate universe construction.
- Mechanical scoring for liquidity, price behavior, fund flow, and simple
  financial metrics.
- Generating Markdown reports from structured inputs.
- Computing mechanical technical filters such as RSI, recent涨幅, turnover, and
  volume-price behavior.

A research agent is useful for:

- Reading announcements, annual reports, investor Q&A, news, and research report
  snippets.
- Judging whether a claimed customer/order relationship is real, material, and
  current.
- Extracting order size, customer exposure, capacity impact, and timing from
  unstructured text.
- Explaining why a candidate is a true supply-chain beneficiary instead of a
  concept-board passenger.
- Flagging weak, circular, or rumor-like evidence.
- Checking black-history issues such as penalties, fraud allegations, repeated
  disclosure problems, governance problems, and prior market credibility damage.
- Turning user-provided US trigger material into a structured trigger packet.

Recommended design:

- Python builds the candidate universe and collects structured evidence.
- The research agent reviews unstructured evidence and writes evidence notes.
- The final score combines mechanical data and agent-reviewed evidence tiers.

## Chip Structure

Chip structure is a large topic and should initially be treated as a scored
research module rather than a single hard rule.

Primary signals:

- Profit holder distribution.
- Loss holder distribution.
- Change speed of the profit/loss distribution.
- Whether profitable chips are becoming more concentrated or more dispersed.
- Whether loss-making holders are being reduced through turnover.

Supporting signals:

- Shareholder count changes.
- Top-10 tradable shareholder concentration.
- Institutional and fund holdings.
- Northbound holdings where available.
- Turnover, volume-price behavior, and float absorption.
- Margin financing and securities lending balance.
- Lock-up releases and major shareholder selling pressure.

The report should avoid making unsupported claims such as "dealer accumulation"
unless the evidence is clearly described. Prefer phrasing like "profit chips are
expanding quickly", "loss chips are being cleared", "float appears to be
tightening", or "chip structure is improving" with the underlying indicators.

## ETF Requirements

Every report must include ETF candidates even when stock candidates look strong.

ETF fields to include:

- Code and name.
- Theme and tracked index.
- Management fee.
- Custody fee.
- Fund size.
- Recent turnover or liquidity.
- Premium/discount when available.
- Top holdings or index exposure when available.
- Use case: fallback, benchmark, or diversified implementation.

## Default Filters

Hard exclusions:

- Beijing Stock Exchange stocks.
- ST stocks.
- Serious black-history issues.

Allowed unless later excluded by scoring:

- Main board.
- ChiNext.
- STAR Market.
- Loss-making companies.
- High-valuation companies.
- Small and mid-cap companies.

The first version should avoid over-filtering. We prefer to keep possible theme
winners in the universe, then downgrade them through risk and tradability scores
instead of removing them too early.

Soft exclusions and downgrades:

- RSI is too high.
- Short-term speculation is too aggressive.
- Recent涨幅 is too large relative to evidence.
- Turnover and board heat suggest crowded trading.
- The company has unresolved credibility issues that are not severe enough for a
  hard exclusion.

When a stock is fundamentally relevant but overheated, the report should keep it
as a watchlist or avoid/overheated candidate and specify what cooling condition
would make it actionable again.

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
