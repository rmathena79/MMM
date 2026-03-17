You’re getting a **project plan for later execution** (by Codex). I am **not executing the project** and I will **not** generate any bracket predictions in this message.

# Project Plan: Predict the Full 2026 Men’s NCAA Tournament Main Bracket (63 Games)

## Objective and acceptance criteria

### Objective
Generate **one complete, deterministic prediction** of the **main 64-team bracket** (i.e., **63 games** from Round of 64 through National Championship) for the **2026 Men’s NCAA Division I tournament**, using web-sourced data and a statistically grounded model/ensemble.

### “Done” means
- A single final artifact containing **exactly 63 predicted game winners** in an **unambiguous** format (CSV + JSON recommended).
- The bracket is **structurally valid** (each team appears once in its first-round slot, winners advance correctly, regions are consistent, etc.).
- The project runs **start-to-finish without human questions** (human only approves tool usage / commands).
- All work products are preserved: raw downloads, transformed datasets, model artifacts, logs, and final outputs.

### Explicit scope choice: “63 games”
Selection Sunday yields **68 teams** and 4 “First Four” play-in games. This project will:
- **Predict the 4 play-in winners** (needed to construct the 64-team field), but
- Output the required **63 main-bracket game predictions** as the primary deliverable.
- Save play-in predictions as an additional artifact, clearly separated.

## Execution design for “no human input”

### Key design constraints
- Codex must not ask the user for clarifications (the user will not help).
- Scripts must have:
  - Robust fallbacks for data acquisition
  - Deterministic randomness (seeded)
  - Strong validation checks and readable error messages
  - Caching to avoid repeated re-scrapes

### One-command orchestration
Create a single orchestrator script that performs the full pipeline:
- `python scripts/run_pipeline.py --year 2026`

Codex will still execute intermediate steps internally, but the plan should ensure this one command can reproduce everything.

## Repository layout and work product preservation

Create this structure in the workspace repo:

- `README.md` (how to run; what outputs mean)
- `requirements.txt` (pinned reasonable versions)
- `scripts/`
  - `run_pipeline.py` (orchestrator)
  - `fetch_bracket.py`
  - `fetch_team_ratings.py`
  - `fetch_historical_data.py`
  - `train_models.py`
  - `predict_matchups.py`
  - `build_bracket.py`
  - `validate_outputs.py`
  - `utils/` (http, caching, logging, name matching)
- `data/`
  - `raw/` (timestamped downloads; never edited)
  - `interim/` (cleaned tables; standardized IDs)
  - `processed/` (final feature tables for modeling)
- `models/` (serialized model objects, calibration params)
- `outputs/` (final predictions + summaries)
- `logs/` (timestamped run logs; include metadata)

Preservation rule: never overwrite raw data; store by timestamped filename.

## Data acquisition strategy

This phase must prioritize *official bracket correctness* first, then predictive power.

### Bracket and seeds (must be correct)
Primary target: scrape the official bracket from NCAA’s bracket page for 2026 (commonly a Next.js page with embedded JSON).
- Implement `scripts/fetch_bracket.py` to:
  1. Try to locate the 2026 bracket page on NCAA bracket listings.
  2. Download HTML and parse embedded `__NEXT_DATA__` JSON (or equivalent) into a normalized bracket structure.
  3. Extract:
     - Regions
     - Seeds
     - Team names
     - First Four pairings and which seed line they feed into
     - Game slot ordering (so each Round of 64 game is uniquely labeled)

Fallbacks (in order):
- A reputable secondary bracket source (e.g., entity["organization","ESPN","sports media company"] bracket pages)
- The 2026 tournament Wikipedia bracket page (only as fallback; must validate consistency)
- If the bracket exists as a PDF only, download and parse with `pdfplumber` + heuristics (last resort; more brittle)

Bracket validation checks (mandatory):
- Exactly 4 regions
- Each region has 16 seed lines (with First Four placeholders allowed)
- Total teams: 68 including play-in participants
- After selecting play-in winners, exactly 64 teams populate the main bracket

### Team strength signals (predictive features)
Use multiple non-paywalled sources to reduce single-source risk. Sources should be scraped politely and cached.

Minimum viable ratings source (strongly recommended):
- entity["organization","BartTorvik","college basketball analytics site"]: scrape current season team efficiency/power values (e.g., Adjusted Efficiency Margin, AdjO, AdjD, tempo).

Secondary sources (for redundancy / ensemble features):
- entity["organization","Sports-Reference","sports statistics website"] (college basketball): scrape season-level team metrics (e.g., SRS, SOS, pace proxies, win-loss, etc.).
- entity["organization","Massey Ratings","sports ratings publisher"]: scrape a rating value if accessible without friction (optional but valuable).
- If available without paywalls: public “net rating”/ranking signals and/or polling.

Market signals (optional but high value if accessible)
If Round of 64 point spreads or moneylines are available from a legally accessible odds aggregator:
- Fetch and store them with timestamps
- Convert to implied probabilities (vig-adjusted if possible)
- Use as an ensemble component for Round of 64 only (later rounds won’t have posted lines)

Injury/news signals (optional, only if robust)
Injury scraping is fragile; only include if it can be done reliably and automatically. If attempted:
- Use a single consistent injury feed
- Keep as a **small adjustment** so bad data doesn’t dominate

## Historical dataset for calibration and model selection

Purpose: calibrate win probabilities and choose ensemble weights using past tournaments.

### Historical tournament outcomes
Implement `scripts/fetch_historical_data.py` to build a dataset of NCAA tournament games for a training window such as 2008–2025:
- For each year:
  - Collect teams, seeds, and game results for the 64-team main bracket (and optionally include First Four separately)

Possible sources:
- Sports-Reference tournament pages are often scrape-friendly for game outcomes.
- If that fails, use a reputable open dataset from a maintained GitHub repo (must store the exact commit hash or downloaded file checksum in logs).

### Historical ratings aligned to tournament year
For each historical year:
- Collect the same rating fields used for 2026 from the same rating sources (especially BartTorvik-style efficiency margins, if available historically).
- Store “as-of” date if the source provides it; otherwise accept “season final” but note the limitation in logs.

### Name matching and team identity
This is a common failure mode. Implement a robust mapping layer:
- Canonical team ID table with:
  - `team_name_raw`
  - `team_name_canonical`
  - source-specific identifiers if discoverable
- Use fuzzy matching with guardrails:
  - Strict thresholds + manual override file
  - Log all uncertain matches and fail hard if too many unresolved matches occur for 2026 teams

Create `data/interim/team_name_map_overrides.csv`:
- Initially auto-generated with “low confidence” rows
- But since the human won’t help, the pipeline should instead:
  - Attempt multiple match approaches
  - If still unresolved for 2026 teams, switch to a backup rating source or fallback to seed-only probabilities for those teams (while logging the degradation)

## Modeling and prediction methodology

This plan prioritizes accuracy by using a calibrated probability model + bracket-consistent optimization.

### Core probability model (recommended baseline)
Train a logistic regression (or gradient-boosted trees if stable) on historical tournament games with features such as:
- `rating_diff` (Team A rating − Team B rating)
- `seed_diff` (Seed A − Seed B)
- Optional: tempo interaction, offense/defense components, SOS proxy

Model outputs:
- `P(A beats B)` for arbitrary neutral-site matchups

Calibration:
- Evaluate calibration (reliability curve, Brier score)
- Optionally apply isotonic regression or Platt scaling if needed

Cross-validation design (important)
Use “leave-one-year-out” or rolling-year validation (train on past years, validate on a held-out year). Select model based on:
- Log loss (primary)
- Brier score (secondary)
- Stability (avoid models that overfit a particular year)

### Ensemble approach (recommended)
If multiple rating sources are gathered:
- Train a meta-model or weighted average on probabilities, weights learned on historical years
- Safeguard: if a source is missing for 2026, automatically renormalize weights

### Play-in integration (First Four)
Predict play-in winners using the same probability model, then insert winners into their bracket slots to form the 64-team main bracket. Store play-in predictions separately.

## Building a full deterministic 63-game bracket from probabilities

You must output a single bracket, not just probabilities.

### Pairwise probability matrix
Compute `P(i beats j)` for every pair of teams in the 64-team field.

### Generate candidate brackets
Implement two bracket construction strategies:

1. **Maximum joint-likelihood bracket (Viterbi-style dynamic programming)**
   - Treat the bracket as a tree.
   - At each node, compute (for each possible team) the maximum probability of the subtree culminating in that team.
   - Backtrack to produce a single full bracket that maximizes the product of chosen game probabilities.

2. **Monte Carlo “most frequent outcome” bracket (sanity check / alternative)**
   - Run N simulations (e.g., 50,000–200,000 depending on speed) using the pairwise probabilities.
   - Derive:
     - Most common champion
     - Most common Final Four
     - Optionally most common full bracket (usually too sparse)
   - Use this to sanity-check the DP bracket; if they disagree wildly, log and prioritize the DP bracket unless simulation strongly suggests a modeling bug.

### Select the single final bracket
By default:
- Choose the **DP maximum joint-likelihood bracket** as the deliverable bracket.
- Also compute its expected number of correct picks under simulation and log it.
- If a clearly better bracket emerges under a defined metric (e.g., higher simulated expected correct picks by a meaningful margin), allow the pipeline to choose that bracket, but it must be deterministic and explain the selection in `outputs/summary.md`.

## Output formats and required deliverables

### Primary required deliverable (63 games)
Write `outputs/main_bracket_predictions_2026.csv` with exactly 63 rows:

Required columns:
- `game_id` (stable identifier, e.g., `R64_East_1`, `R32_West_4`, `FF_1`, `NCG`)
- `round` (R64, R32, S16, E8, F4, NCG)
- `region` (East/West/South/Midwest or blank for F4/NCG)
- `slot` (a human-readable slot label)
- `team1`, `seed1`
- `team2`, `seed2`
- `predicted_winner`, `predicted_winner_seed`
- `win_prob` (probability that predicted_winner wins that matchup)
- `model_version` (hash of config + git commit if available)
- `generated_at_utc`

Also write the same data as `outputs/main_bracket_predictions_2026.json` with structured objects.

### Additional preserved artifacts
- `outputs/play_in_predictions_2026.csv` (4 rows)
- `outputs/summary.md`:
  - Predicted champion
  - Predicted Final Four
  - Brief notes on data sources used, and whether any fallbacks/degradations happened
- `data/raw/...` all raw fetches
- `data/processed/features_2026.parquet` (or CSV)
- `models/...` serialized fitted model(s)
- `logs/run_*.log` plus a machine-readable `run_metadata.json` containing:
  - Source URLs used
  - Fetch timestamps
  - Record counts
  - Any fallback paths taken

## Validation and QA gates

Implement `scripts/validate_outputs.py` and fail the pipeline if any check fails:

Bracket structure checks:
- Exactly 63 main-bracket games produced
- Exactly 64 distinct teams appear in Round of 64 games
- Winners advance correctly (a team predicted to win in R64 must appear in its R32 slot, etc.)
- No impossible matchups (teams from different regions can’t meet before Final Four)

Data sanity checks:
- No missing seeds
- No missing team names
- Probabilities in [0, 1]
- Reasonable rating ranges (detect scraping failure returning empty/duplicated pages)

Reproducibility checks:
- Fixed random seed captured in metadata
- Cached data present so reruns don’t change unless explicitly requested

## Implementation details and runbook

### Environment setup (Windows-friendly)
Codex should:
1. Create a virtual environment:
   - `python -m venv .venv`
2. Install deps:
   - `.venv\Scripts\pip install -r requirements.txt`

Recommended dependencies:
- `requests`, `httpx` (one is enough)
- `beautifulsoup4`, `lxml`
- `pandas`, `numpy`
- `scikit-learn`
- `rapidfuzz` (team-name matching)
- `pyarrow` (optional for parquet)
- `tqdm`
- `pdfplumber` (only if PDF fallback used)

### Orchestrator flow
`run_pipeline.py` should run these steps in order, stopping on validation failure:
1. Fetch bracket + seeds (and First Four structure)
2. Fetch 2026 team ratings/features
3. Fetch historical outcomes and historical ratings/features
4. Train and validate model(s)
5. Predict play-in winners; expand to 64-team bracket
6. Compute pairwise probabilities
7. Construct bracket (DP + simulation checks)
8. Write outputs
9. Validate outputs + write run metadata

### Logging
Use structured logging:
- One human-readable log file
- One JSON metadata file
Include HTTP status codes, source URLs, and cache hits/misses.

## Safety, compliance, and robustness notes

- Respect website rate limits (sleep/backoff, user-agent).
- Cache every fetched page (avoid hammering sources).
- Avoid paywalled sources or any attempt to bypass access controls.
- If a key source blocks scraping:
  - Use fallback sources
  - Log the degradation
  - Continue with a reduced-feature model rather than failing (unless bracket itself cannot be obtained)

## Final deliverable checklist for human assessment

Human should be able to open:
- `outputs/main_bracket_predictions_2026.csv` → confirm 63 rows and clear winners
- `outputs/summary.md` → quick champion/Final Four view
- `logs/run_metadata.json` → confirm sources and timestamps
- `data/raw/` → confirm preservation of original material