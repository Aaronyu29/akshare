# Research Layer Todo List

This checklist turns `research.md` and `research/ARCHITECTURE.md` into an
implementation plan. Work through it in order unless a later task explicitly
unblocks an earlier one.

## Rules

- Keep changes on branch `feature/us-a-share-research`.
- Commit after each stable milestone.
- Do not commit generated cache or report files.
- Keep `openai-agents` optional in v1.
- Keep the deterministic Python pipeline runnable without `OPENAI_API_KEY`.
- Do not add trading or broker integration.
- Do not run `codex logout`, `chatgpt logout`, or clear auth credentials.

## Implementation Status

- [x] Research layer package added under `research/`.
- [x] Deterministic CLI pipeline implemented without requiring `OPENAI_API_KEY`.
- [x] A-share, ETF, board, history, and ETF profile data-source wrappers added.
- [x] Eastmoney-first provider fallback added where practical.
- [x] Cache, config, schemas, mappings, universe, enrichment, filters, scoring, report, and agent/tool adapter modules implemented.
- [x] Markdown report output writes to ignored `research/reports/`.
- [x] Cache output writes to ignored `research/cache/`.
- [x] Local compile passed for `research/` and research tests.
- [x] `pytest` installed in local `.venv`.
- [x] Unit tests passed: `8 passed`.
- [x] Live data probe passed for A-share spot/history and ETF spot/history.

## Milestone 0: Repo Hygiene

- [ ] Confirm branch is `feature/us-a-share-research`.
- [ ] Confirm worktree is clean before implementation.
- [ ] Confirm `.gitignore` includes:
  - [ ] `/research/cache/`
  - [ ] `/research/reports/`
- [ ] Confirm local virtual environment works:
  - [ ] `.venv\Scripts\python.exe -c "import akshare as ak; print(ak.__version__)"`
- [ ] Confirm market-data smoke test still works with network approval:
  - [ ] `.venv\Scripts\python.exe research\probe_market_data.py`

Acceptance:

- [ ] No uncommitted unrelated changes.
- [ ] Smoke test can fetch A-share or fallback data and ETF data.

Suggested commit:

```text
chore: verify research layer baseline
```

## Milestone 1: Core Package Skeleton

- [ ] Add `research/__init__.py`.
- [ ] Add `research/config.py`.
- [ ] Add `research/schemas.py`.
- [ ] Add `research/cache.py`.
- [ ] Add placeholder modules:
  - [ ] `research/mappings.py`
  - [ ] `research/universe.py`
  - [ ] `research/enrichment.py`
  - [ ] `research/filters.py`
  - [ ] `research/scoring.py`
  - [ ] `research/report.py`
  - [ ] `research/cli.py`
- [ ] Add package folders:
  - [ ] `research/agents/__init__.py`
  - [ ] `research/tools/__init__.py`

Acceptance:

- [ ] All new modules import without side effects.
- [ ] `python -m py_compile` passes for all `research/*.py`.
- [ ] No live network calls happen at import time.

Suggested commit:

```text
feat: add research package skeleton
```

## Milestone 2: Config Defaults

- [ ] Define `ScoreWeights`.
- [ ] Define `CacheSettings`.
- [ ] Define `ResearchSettings`.
- [ ] Include defaults:
  - [ ] A-share + China ETF only.
  - [ ] hard exclusions: BSE and ST.
  - [ ] core candidate target: 3.
  - [ ] max core candidates: 8.
  - [ ] default RSI threshold placeholder, configurable.
  - [ ] report directory: `research/reports`.
  - [ ] cache directory: `research/cache`.
- [ ] Add helper `get_default_settings()`.

Acceptance:

- [ ] Config objects are dataclasses.
- [ ] Config can be imported and printed from Python.
- [ ] Defaults match `research.md`.

Suggested commit:

```text
feat: add research configuration defaults
```

## Milestone 3: Data Schemas

- [ ] Implement dataclasses in `research/schemas.py`:
  - [ ] `ResearchRequest`
  - [ ] `TriggerPacket`
  - [ ] `ThemeNode`
  - [ ] `Candidate`
  - [ ] `CandidateEvidence`
  - [ ] `CandidateMetrics`
  - [ ] `ScoreComponent`
  - [ ] `CandidateScore`
  - [ ] `EtfCandidate`
  - [ ] `TradingPlan`
  - [ ] `ResearchReport`
  - [ ] `DataWarning`
- [ ] Add enum-like string constants or `Enum` classes for:
  - [ ] evidence tiers: `hard`, `medium`, `soft`, `unknown`
  - [ ] candidate classes: `core`, `watchlist`, `avoid_overheated`, `avoid_black_history`, `concept_only`
  - [ ] market types: `a_share`, `etf`
- [ ] Add simple serialization helpers:
  - [ ] `to_dict()`
  - [ ] `from_dict()` only where needed.

Acceptance:

- [ ] Schemas can be instantiated in a tiny smoke script.
- [ ] No pandas objects are required inside schemas.
- [ ] Schemas avoid API-key or network dependencies.

Suggested commit:

```text
feat: define research data schemas
```

## Milestone 4: Cache Layer

- [ ] Implement `research/cache.py`.
- [ ] Add deterministic cache key helper:
  - [ ] namespace
  - [ ] provider
  - [ ] dataset
  - [ ] params hash
  - [ ] extension
- [ ] Add metadata structure:
  - [ ] provider
  - [ ] dataset
  - [ ] params
  - [ ] fetched_at
  - [ ] ttl_seconds
  - [ ] row_count
  - [ ] schema_version
- [ ] Add helpers:
  - [ ] `save_json()`
  - [ ] `load_json()`
  - [ ] `save_dataframe_csv()`
  - [ ] `load_dataframe_csv()`
  - [ ] `is_fresh()`
  - [ ] `ensure_cache_dirs()`
- [ ] Do not require parquet in v1.

Acceptance:

- [ ] Cache functions work in a temp directory.
- [ ] Metadata is saved next to cached data.
- [ ] `research/cache/` remains ignored by git.

Suggested commit:

```text
feat: add filesystem cache helpers
```

## Milestone 5: Mapping Layer

- [ ] Implement `research/mappings.py`.
- [ ] Add curated first ticker mappings:
  - [ ] `NVDA`
  - [ ] `TSLA`
  - [ ] `ASML`
  - [ ] `AMD`
  - [ ] `PLTR`
  - [ ] `LLY`
  - [ ] `NVO`
  - [ ] `ISRG`
- [ ] For `NVDA`, include:
  - [ ] AI server
  - [ ] optical module
  - [ ] liquid cooling
  - [ ] PCB
  - [ ] copper clad laminate
  - [ ] advanced packaging
  - [ ] semiconductor equipment
  - [ ] HBM
  - [ ] power supply
- [ ] Include bilingual aliases where useful:
  - [ ] English keyword
  - [ ] Chinese keyword
  - [ ] common abbreviation
- [ ] Add lookup helpers:
  - [ ] `get_ticker_mapping(symbol)`
  - [ ] `expand_keywords(symbol, keywords)`
  - [ ] `theme_slug(text)`

Acceptance:

- [ ] `NVDA` mapping returns a non-empty theme tree.
- [ ] Custom user keywords are preserved and merged with curated mappings.
- [ ] No network calls.

Suggested commit:

```text
feat: add curated theme mappings
```

## Milestone 6: Data Source Enhancements

- [ ] Review existing `research/data_sources.py`.
- [ ] Add optional cache usage without changing existing public behavior.
- [ ] Add wrapper return metadata:
  - [ ] provider
  - [ ] fetched_at
  - [ ] row_count
  - [ ] warnings
- [ ] Add ETF fee/profile fetching helpers if available through AKShare.
- [ ] Add board-name fetching helpers:
  - [ ] Eastmoney concept boards.
  - [ ] Eastmoney industry boards.
  - [ ] THS boards as fallback where useful.
- [ ] Keep provider failures visible.

Acceptance:

- [ ] Existing `probe_market_data.py` still runs.
- [ ] A-share spot fallback remains functional.
- [ ] ETF spot fallback remains functional.

Suggested commit:

```text
feat: extend research data source wrappers
```

## Milestone 7: Candidate Universe Builder

- [ ] Implement `research/universe.py`.
- [ ] Inputs:
  - [ ] `ResearchRequest`
  - [ ] `TriggerPacket`
  - [ ] mapping output
  - [ ] provider data
- [ ] Candidate sources:
  - [ ] curated mappings
  - [ ] concept board constituents
  - [ ] industry board constituents
  - [ ] stock-name keyword search
  - [ ] ETF-name keyword search
- [ ] Each candidate must include provenance:
  - [ ] matched keyword
  - [ ] matched theme
  - [ ] source board or provider
  - [ ] timestamp
- [ ] Implement deduplication by normalized stock code.
- [ ] Implement ETF candidate collection separately from stocks.

Acceptance:

- [ ] A dry-run `NVDA` request produces stock and ETF candidate lists.
- [ ] Candidate provenance is visible.
- [ ] No candidate is silently duplicated.

Suggested commit:

```text
feat: build research candidate universe
```

## Milestone 8: Enrichment Layer

- [ ] Implement `research/enrichment.py`.
- [ ] Add quote enrichment from spot data.
- [ ] Add recent historical bars where available.
- [ ] Add technical metrics:
  - [ ] RSI
  - [ ] 5-day return
  - [ ] 20-day return
  - [ ] turnover amount
  - [ ] volume expansion placeholder
  - [ ] moving-average distance placeholder
- [ ] Add ETF enrichment:
  - [ ] management fee
  - [ ] custody fee
  - [ ] fund size
  - [ ] turnover/liquidity
  - [ ] tracking index when available
- [ ] Missing metrics should become warnings.

Acceptance:

- [ ] Enrichment works with partial data.
- [ ] No crash when one AKShare endpoint fails.
- [ ] Metrics are attached to candidates as `CandidateMetrics`.

Suggested commit:

```text
feat: enrich candidates with market metrics
```

## Milestone 9: Filters

- [ ] Implement `research/filters.py`.
- [ ] Hard filters:
  - [ ] BSE codes.
  - [ ] ST names.
  - [ ] confirmed black-history flags from evidence notes.
- [ ] Soft flags:
  - [ ] RSI high.
  - [ ] recent return too high.
  - [ ] turnover/crowding high.
  - [ ] weak liquidity.
  - [ ] weak evidence.
- [ ] Keep soft-flagged candidates in output sections.
- [ ] Add cooling-condition text for overheated candidates.

Acceptance:

- [ ] ST and BSE candidates are excluded or classified as hard filtered.
- [ ] Overheated candidates are not core candidates.
- [ ] Avoid/watchlist rationale is visible.

Suggested commit:

```text
feat: add research filters and risk flags
```

## Milestone 10: Scoring

- [ ] Implement `research/scoring.py`.
- [ ] Score components:
  - [ ] theme relevance: 0-30
  - [ ] revenue/order evidence: 0-25
  - [ ] chip structure: 0-15
  - [ ] tradability: 0-15
  - [ ] speculative potential: 0-15
  - [ ] risk penalty: -30-0
- [ ] Add rationale text for each component.
- [ ] Add 30% customer/order exposure as strong bonus, not hard gate.
- [ ] Add large-order catalyst bonus.
- [ ] Cap core candidates around 3 by default.
- [ ] Place excess good names into watchlist.

Acceptance:

- [ ] Total score equals component sum.
- [ ] Score rationale is available for report rendering.
- [ ] Core list is selective.

Suggested commit:

```text
feat: score research candidates
```

## Milestone 11: Report Rendering

- [ ] Implement `research/report.py`.
- [ ] Render Markdown sections:
  - [ ] title and run metadata
  - [ ] user input
  - [ ] US trigger summary
  - [ ] theme tree
  - [ ] core candidates
  - [ ] watchlist
  - [ ] avoid / overheated
  - [ ] avoid / black-history
  - [ ] ETF implementation table
  - [ ] evidence notes
  - [ ] entry conditions
  - [ ] take-profit conditions
  - [ ] stop-loss / invalidation conditions
  - [ ] data warnings
  - [ ] follow-up checks
- [ ] Add filename helper:
  - [ ] `{US_SYMBOL}_{theme_slug}_{YYYYMMDD_HHMMSS}.md`
- [ ] Save under `research/reports/`.

Acceptance:

- [ ] A report can be generated from hand-built schema objects.
- [ ] Markdown is readable and compact.
- [ ] Report files are ignored by git.

Suggested commit:

```text
feat: render research markdown reports
```

## Milestone 12: CLI

- [ ] Implement `research/cli.py`.
- [ ] Commands:
  - [ ] `run`
  - [ ] `probe`
  - [ ] `show-config`
- [ ] `run` accepts:
  - [ ] `--us`
  - [ ] `--keywords`
  - [ ] `--input`
  - [ ] `--output-dir`
  - [ ] `--no-agent`
- [ ] `probe` calls existing market-data probes or shared probe functions.
- [ ] `show-config` prints settings.
- [ ] CLI must use the same internal pipeline as agent mode.

Acceptance:

- [ ] `python -m research.cli show-config` works.
- [ ] `python -m research.cli run --us NVDA --keywords "Blackwell,liquid cooling"` creates a Markdown report.
- [ ] CLI does not require `OPENAI_API_KEY`.

Suggested commit:

```text
feat: add research command line interface
```

## Milestone 13: Agent SDK Adapter

- [ ] Add `research/agents/prompts.py`.
- [ ] Add `research/agents/schemas.py`.
- [ ] Add `research/agents/sdk_adapter.py`.
- [ ] Keep `openai-agents` optional.
- [ ] Add import guard:
  - [ ] If SDK missing, show clear message and fall back to manual mode.
- [ ] Define agent roles:
  - [ ] `TriggerResearchAgent`
  - [ ] `EvidenceAgent`
  - [ ] `RiskAgent`
  - [ ] `ReportAgent`
- [ ] Add tool wrappers:
  - [ ] `research/tools/market_tools.py`
  - [ ] `research/tools/scoring_tools.py`
  - [ ] `research/tools/report_tools.py`
- [ ] Do not expose shell tools in v1.
- [ ] Do not require agent mode for deterministic tests.

Acceptance:

- [ ] Importing `research.agents.sdk_adapter` without SDK installed does not crash the whole project.
- [ ] Manual mode remains the default.
- [ ] Agent adapter design matches `research/ARCHITECTURE.md`.

Suggested commit:

```text
feat: add optional agents sdk adapter
```

## Milestone 14: Tests

- [ ] Add focused tests if the repo test setup supports them.
- [ ] Test cache key generation.
- [ ] Test config defaults.
- [ ] Test score component sum.
- [ ] Test hard filters for ST and BSE.
- [ ] Test report rendering from fake data.
- [ ] Test provider fallback with mocked failures.
- [ ] Avoid tests that require live OpenAI API calls.

Acceptance:

- [ ] Tests pass locally.
- [ ] Tests do not require credentials.
- [ ] Tests do not require live market data unless explicitly marked smoke.

Suggested commit:

```text
test: add research layer unit tests
```

## Milestone 15: First End-to-End Dry Run

- [ ] Create a hand-written trigger packet for `NVDA`.
- [ ] Run the pipeline without agent mode.
- [ ] Generate a Markdown report.
- [ ] Confirm report includes:
  - [ ] 3 core stock candidates if enough evidence exists.
  - [ ] ETF candidates.
  - [ ] entry conditions.
  - [ ] take-profit conditions.
  - [ ] stop-loss / invalidation conditions.
  - [ ] data warnings.
- [ ] Inspect whether generated report should remain ignored or be saved as a sample.
- [ ] If saving a sample, put it under a committed examples path, not `research/reports/`.

Acceptance:

- [ ] One complete report is generated.
- [ ] No generated cache/report files are accidentally staged.
- [ ] Known data-source failures are recorded as warnings, not silent failures.

Suggested commit:

```text
feat: complete nvda research dry run
```

## Milestone 16: Git And Push

- [ ] Confirm branch:
  - [ ] `git branch --show-current`
- [ ] Confirm clean worktree:
  - [ ] `git status --short`
- [ ] Review latest commits:
  - [ ] `git log --oneline -10`
- [ ] Push branch:
  - [ ] `git push -u origin feature/us-a-share-research`
- [ ] If push fails due to auth, do not reset or discard commits.

Acceptance:

- [ ] Branch exists on GitHub.
- [ ] Local commits match remote branch.

## Deferred Items

- [ ] Web dashboard.
- [ ] CSV sidecar exports.
- [ ] Rich chip-distribution data source.
- [ ] Automated scheduled runs.
- [ ] Broker/trading integration.
- [ ] Full OpenAI Agents SDK production workflow.
- [ ] Codex CLI workspace automation from inside the pipeline.
- [ ] Multi-theme portfolio dashboard.

## One-Shot Implementation Prompt

Use this prompt later when asking Codex to implement the list:

```text
Implement todoList.md through Milestone 12 first. Keep OpenAI Agents SDK optional.
Do not implement broker/trading integration. Do not commit generated cache or
reports. Use focused commits after stable milestones. Preserve existing user
changes and do not run any logout commands.
```
