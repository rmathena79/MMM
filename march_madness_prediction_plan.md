# 2026 NCAA Men's March Madness Bracket Prediction Plan

## Objective

Predict all 63 game outcomes of the 2026 Men's NCAA Division I Tournament main
bracket (the 64-team bracket after First Four results are resolved). Maximize
accuracy using publicly available analytical ratings, betting market data, and
historical seed-performance baselines.

---

## Overview of Approach

The prediction engine is a **multi-source composite model**. It works as follows:

1. Scrape/collect team power ratings from multiple independent analytical systems
2. Scrape/collect betting market odds and point spreads (market consensus)
3. Compute a blended composite strength rating for every tournament team
4. Simulate the bracket round by round, picking the higher-composite-rated team
   in each matchup, with targeted upset adjustments based on historical patterns
5. Emit the full 63-game bracket as a human-readable text file

This is not a machine learning project. It is a data aggregation and
decision-rule project. The "model" is a weighted average of expert systems.

---

## Phase 1: Establish the Bracket Structure

### Step 1.1 — Retrieve the official bracket

Fetch the full 68-team bracket from the NCAA or ESPN. The critical output is a
structured data file mapping each region (East, West, Midwest, South) to its
eight seed-line matchups.

**Primary source:** `https://www.ncaa.com/news/basketball-men/mml-official-bracket/2026-03-15/2026-ncaa-tournament-printable-bracket-schedule-march-madness`

**Backup source:** `https://www.espn.com/espn/betting/story/_/id/48217692/espn-2026-ncaa-tournament-men-bracket-game-odds`

**Action:** Fetch the page, parse the bracket, and write a JSON file:

```
data/bracket.json
```

Schema (example):
```json
{
  "East": {
    "1v16": ["Duke", "Siena"],
    "8v9":  ["Ohio State", "TCU"],
    "5v12": ["St. John's", "Northern Iowa"],
    "4v13": ["Kansas", "Cal Baptist"],
    "6v11": ["Louisville", "South Florida"],
    "3v14": ["Michigan State", "North Dakota State"],
    "7v10": ["UCLA", "UCF"],
    "2v15": ["UConn", "Furman"]
  },
  ...
}
```

### Step 1.2 — Resolve First Four games

Four play-in games produce four teams that fill specific bracket slots. The First
Four matchups for 2026 are:

| Slot     | Game                             | Region   |
|----------|----------------------------------|----------|
| 16-seed  | UMBC vs. Howard                  | Midwest  |
| 16-seed  | Prairie View A&M vs. Lehigh      | South    |
| 11-seed  | Texas vs. NC State               | West     |
| 11-seed  | Miami (Ohio) vs. SMU             | Midwest  |

**Action:** Predict these four games using the same composite method described
below (or using the BPI projections and spreads already published, since these
games are essentially toss-ups or lopsided). Hard-code the winners into the
bracket before proceeding to Round of 64 predictions.

**Published BPI projections for First Four (from ESPN):**
- UMBC by 1.5 → pick UMBC
- NC State by 0.1 → near toss-up; lean NC State (or adjust after data pull)
- Lehigh by 0.9 → lean Lehigh
- SMU by 6.7 → pick SMU

---

## Phase 2: Collect Team Strength Data

Gather numerical power ratings for all 68 tournament teams from multiple sources.
The goal is 3-5 independent rating systems plus market odds.

### Source A — ESPN BPI (Basketball Power Index)

**URL:** `https://www.espn.com/mens-college-basketball/bpi`
Also: `https://www.espn.com/mens-college-basketball/bpi/_/view/tournament`

**What to collect:** BPI rating (points above/below average), offensive rating,
defensive rating, strength of record.

**Scraping notes:** ESPN pages are JavaScript-rendered. Try fetching the HTML
first; if the data table is not in the static HTML, try the underlying ESPN API.
The tournament-view page may list only the 68 tournament teams, which is
convenient.

**Fallback:** If BPI numbers cannot be programmatically extracted, use the
per-game BPI projections from the ESPN betting article (URL in Step 1.1 backup
source), which gives BPI point-spread projections for every first-round game.
These implicitly encode relative team strength and can be reverse-engineered into
ratings.

### Source B — KenPom Ratings

**URL:** `https://kenpom.com/`

**What to collect:** Adjusted Efficiency Margin (AdjEM), Adjusted Offensive
Efficiency (AdjO), Adjusted Defensive Efficiency (AdjD), rank.

**Scraping notes:** KenPom shows a partial table to non-subscribers. The top ~40
teams and their ratings are often visible. If a paywall blocks full access,
deprioritize this source and rely on Sources A, C, D.

### Source C — BartTorvik T-Rank

**URL:** `https://barttorvik.com/`

**What to collect:** T-Rank composite rating, ADJOE, ADJDE, WAB (Wins Above
Bubble).

**Scraping notes:** BartTorvik uses Cloudflare browser verification. If direct
fetch fails, try fetching the `trank.php` endpoint or the CSV export if one
exists. If blocked, skip and weight other sources more.

### Source D — Sports-Reference / CBB

**URL:** `https://www.sports-reference.com/cbb/seasons/men/2026-ratings.html`

**What to collect:** SRS (Simple Rating System) — margin of victory adjusted for
strength of schedule. Also available: ORtg, DRtg, SOS.

**Scraping notes:** Sports-Reference pages are static HTML with well-structured
tables. This should be the most reliable programmatic source.

### Source E — Betting Market Consensus

**Primary URL:** The ESPN betting article with DraftKings spreads for every first-
round game:
`https://www.espn.com/espn/betting/story/_/id/48217692/espn-2026-ncaa-tournament-men-bracket-game-odds`

**Supplementary:** Championship futures odds from CBS/DraftKings:
`https://www.cbssports.com/college-basketball/news/ncaa-tournament-odds-march-madness-2026-national-championship/`

**What to collect:**
- Point spreads and BPI projections for every first-round matchup
- Championship futures odds (implied win probabilities for the entire tournament)

**Why this matters:** Betting markets are the single strongest predictor of game
outcomes. They aggregate the opinions of millions of bettors and sophisticated
models. Point spreads directly encode expected margin of victory.

### Source F — Neil Paine Composite Forecast (bonus)

**URL:** `https://neilpaine.substack.com/p/2026-ncaa-tournament-forecast`

**What to collect:** Pre-computed composite probabilities to advance through each
round for every team. This source already does the multi-source blending we aim
to do. If accessible, it becomes the single most valuable data source.

**Scraping notes:** Substack pages are generally fetchable. The data may be in
tables or embedded charts.

### Data Collection Strategy

```
for each source in [A, B, C, D, E, F]:
    try:
        fetch and parse
        save to data/{source_name}.json
    except:
        log warning, continue to next source
```

**Minimum viable data:** If only ONE source is successfully scraped, proceed with
that single source. The project must be resilient to scraping failures. If NO
sources yield team ratings, fall back to Phase 3 using only seed-based historical
probabilities and published betting odds.

---

## Phase 3: Build Composite Ratings

### Step 3.1 — Normalize ratings to a common scale

Each rating system uses a different scale. Normalize all to **points above
average per 100 possessions** (or a z-score if raw scales differ too much).

For each source that was successfully collected:
1. Compute mean and standard deviation across all tournament teams
2. Convert each team's rating to a z-score: `(rating - mean) / stdev`

### Step 3.2 — Compute weighted composite

For each team, compute:

```
composite = w_A * z_BPI + w_B * z_KenPom + w_C * z_Torvik + w_D * z_SRS + ...
```

Default weights (adjust based on which sources are available):
- ESPN BPI: 0.25
- KenPom: 0.25
- BartTorvik: 0.20
- Sports-Reference SRS: 0.15
- Betting market implied: 0.15

If fewer sources are available, redistribute weights proportionally among those
that are. If betting odds are the only source, use them alone — they are the
strongest single predictor.

### Step 3.3 — Incorporate championship futures odds

Championship futures odds encode the market's holistic view of which teams can
win six consecutive games, not just one. Use these as a sanity check:
- Convert futures odds to implied probabilities
- If a team's composite rating significantly disagrees with its market
  probability, investigate and potentially adjust

Save output to:
```
data/composite_ratings.json
```

---

## Phase 4: Generate Predictions

### Step 4.1 — Predict each game using the composite

Process the bracket round by round. For each matchup:

1. Look up both teams' composite ratings
2. Compute the **rating gap** = higher_rated - lower_rated
3. **Default rule:** Pick the higher-rated team
4. Apply upset adjustments (see Step 4.2)

### Step 4.2 — Upset heuristics

Historical data shows certain seed matchups produce upsets at known rates. Apply
these adjustments:

| Matchup    | Historical upset rate | Adjustment rule                         |
|------------|----------------------|------------------------------------------|
| 1 vs 16    | ~1.5%                | Never pick the 16-seed                  |
| 2 vs 15    | ~6%                  | Pick 2-seed unless composite gap < 0.3σ |
| 3 vs 14    | ~15%                 | Pick 3-seed unless composite gap < 0.5σ |
| 4 vs 13    | ~21%                 | Pick 4-seed unless composite gap < 0.6σ |
| 5 vs 12    | ~35%                 | Pick 5-seed unless composite gap < 0.4σ |
| 6 vs 11    | ~37%                 | Pick higher composite, ignoring seed    |
| 7 vs 10    | ~39%                 | Pick higher composite, ignoring seed    |
| 8 vs 9     | ~49%                 | Pick higher composite, ignoring seed    |

For rounds 2+, seed-based heuristics matter less; rely primarily on composite
ratings.

**Target number of first-round upsets:** Historically, ~6-8 upsets occur per
tournament in the Round of 64 (where "upset" = lower seed wins). Ensure the
model picks roughly this many, concentrated in the 5v12 through 9v8 matchups.

### Step 4.3 — Round-by-round bracket traversal

```python
def predict_bracket(bracket, ratings):
    results = {}
    current_round = bracket  # list of 32 first-round matchups
    round_num = 1
    while len(current_round) > 0:
        winners = []
        for matchup in current_round:
            team_a, team_b = matchup
            winner = pick_winner(team_a, team_b, ratings, round_num)
            winners.append(winner)
            results[f"R{round_num}: {team_a} vs {team_b}"] = winner
        # Pair winners for next round
        current_round = [(winners[i], winners[i+1]) for i in range(0, len(winners), 2)]
        round_num += 1
    return results
```

### Step 4.4 — Sanity checks

Before finalizing:
- Verify exactly 63 games are predicted (4 First Four + 32 + 16 + 8 + 4 + 2 + 1
  = 67 total; but we need 63 for the main bracket: 32+16+8+4+2+1)
- Verify all four regional champions are determined
- Verify the Final Four, championship game, and champion are determined
- Cross-reference the champion and Final Four with betting market favorites —
  if the model picks a very long-shot champion, reconsider

---

## Phase 5: Output

### Step 5.1 — Generate the prediction file

Create a clean, human-readable output file:

```
output/bracket_predictions.txt
```

Format:
```
========================================
2026 NCAA MEN'S TOURNAMENT PREDICTIONS
========================================

FIRST FOUR
----------
UMBC vs Howard → UMBC
NC State vs Texas → NC State
Lehigh vs Prairie View A&M → Lehigh
SMU vs Miami (Ohio) → SMU

EAST REGION
-----------
Round of 64:
  (1) Duke vs (16) Siena → Duke
  (8) Ohio State vs (9) TCU → Ohio State
  ...
Round of 32:
  Duke vs Ohio State → Duke
  ...
Sweet 16:
  Duke vs ... → Duke
  ...
Elite 8:
  ... → [East Champion]

[Repeat for West, Midwest, South]

FINAL FOUR
----------
East Champion vs West Champion → ...
Midwest Champion vs South Champion → ...

NATIONAL CHAMPIONSHIP
---------------------
... vs ... → [2026 CHAMPION]
```

### Step 5.2 — Save supplementary artifacts

Also save:
- `data/composite_ratings.json` — all team ratings
- `data/bracket.json` — the structured bracket
- `output/prediction_rationale.txt` — for each game, the composite gap and any
  upset adjustment applied (optional but encouraged)

---

## Execution Summary

| Step | Action                                  | Estimated effort |
|------|-----------------------------------------|-----------------|
| 1.1  | Fetch and parse bracket                 | Simple fetch     |
| 1.2  | Resolve First Four                      | Trivial          |
| 2    | Scrape team ratings (3-5 sources)       | Medium; expect some failures |
| 3    | Normalize and blend into composite      | Straightforward math |
| 4    | Traverse bracket, pick winners          | Core logic       |
| 5    | Format and save output                  | Simple I/O       |

**Total expected tool calls:** 5-15 web fetches, 1 Python script execution.

**Failure modes and mitigations:**
- *All scraping fails:* Use Claude's own knowledge of the bracket, team records,
  seeds, and betting odds gathered during planning (see Appendix A) to make
  predictions via structured reasoning. This is the absolute fallback.
- *Some sources blocked:* Proceed with whatever sources succeeded. Even one good
  rating system (especially market odds) is sufficient.
- *A team name doesn't match across sources:* Use fuzzy matching or a manually
  constructed alias map (e.g., "UConn" = "Connecticut", "Miami" = "Miami FL"
  vs "Miami OH").

---

## Appendix A: Pre-Gathered Intelligence

This appendix preserves key data gathered during plan composition for use as
fallback or cross-reference.

### The Full 2026 Bracket

**EAST REGION (Final site: Newark, NJ)**
- (1) Duke vs (16) Siena
- (8) Ohio State vs (9) TCU
- (5) St. John's vs (12) Northern Iowa
- (4) Kansas vs (13) Cal Baptist
- (6) Louisville vs (11) South Florida
- (3) Michigan State vs (14) North Dakota State
- (7) UCLA vs (10) UCF
- (2) UConn vs (15) Furman

**WEST REGION (Final site: San Francisco, CA)**
- (1) Arizona vs (16) LIU
- (8) Villanova vs (9) Utah State
- (5) Wisconsin vs (12) High Point
- (4) Arkansas vs (13) Hawaii
- (6) BYU vs (11) Texas/NC State (First Four winner)
- (3) Gonzaga vs (14) Kennesaw State
- (7) Miami (FL) vs (10) Missouri
- (2) Purdue vs (15) Queens

**MIDWEST REGION (Final site: Detroit, MI)**
- (1) Michigan vs (16) UMBC/Howard (First Four winner)
- (8) Georgia vs (9) Saint Louis
- (5) Texas Tech vs (12) Akron
- (4) Alabama vs (13) Hofstra
- (6) Tennessee vs (11) SMU/Miami OH (First Four winner)
- (3) Virginia vs (14) Wright State
- (7) Kentucky vs (10) Santa Clara
- (2) Iowa State vs (15) Tennessee State

**SOUTH REGION (Final site: Atlanta, GA)**
- (1) Florida vs (16) Prairie View A&M/Lehigh (First Four winner)
- (8) Clemson vs (9) Iowa
- (5) Vanderbilt vs (12) McNeese
- (4) Nebraska vs (13) Troy
- (6) North Carolina vs (11) VCU
- (3) Illinois vs (14) Penn
- (7) Saint Mary's vs (10) Texas A&M
- (2) Houston vs (15) Idaho

### Championship Odds (DraftKings, as of 3/15/2026)

| Team          | Seed | Odds   | Implied Prob |
|---------------|------|--------|-------------|
| Duke          | 1    | +325   | ~23%        |
| Michigan      | 1    | +340   | ~22%        |
| Arizona       | 1    | +400   | ~20%        |
| Florida       | 1    | +700   | ~12%        |
| Houston       | 2    | +1000  | ~9%         |
| Iowa State    | 2    | +1500  | ~6%         |
| Illinois      | 3    | +1900  | ~5%         |
| Michigan St   | 3    | +2000  | ~5%         |
| UConn         | 2    | +1700  | ~5%         |
| Purdue        | 2    | +3500  | ~3%         |

### BPI First-Round Projections (from ESPN)

| Matchup                              | BPI Projection         | BPI Win%  |
|--------------------------------------|------------------------|-----------|
| (1) Duke vs (16) Siena               | Duke by 29.5           | ~99%      |
| (8) Ohio State vs (9) TCU            | Ohio State by 4.0      | 65.4%     |
| (4) Nebraska vs (13) Troy            | Nebraska by 15.9       | 92.7%     |
| (6) Louisville vs (11) S. Florida    | Louisville by 9.1      | 81.0%     |
| (5) Wisconsin vs (12) High Point     | Wisconsin by 7.3       | 76.3%     |
| UMBC vs Howard (First Four)          | UMBC by 1.5            | 55.9%     |
| NC State vs Texas (First Four)       | NC State by 0.1        | 50.2%     |
| Lehigh vs Pra. View A&M (First Four) | Lehigh by 0.9          | 53.7%     |
| SMU vs Miami OH (First Four)         | SMU by 6.7             | 74.5%     |

### Notable Expert Insights

- Duke is the KenPom #1 team with top-4 offensive and defensive ratings
- Michigan lost key player L.J. Cason for the season; has covered only one game
  since that injury (market may be overrating them)
- VCU (11-seed) is a popular upset pick over North Carolina (6-seed)
- Texas A&M (10-seed) favored by some models over Saint Mary's (7-seed)
- High Point (12-seed) flagged by BPI as most likely big upset vs Wisconsin (5)
- Florida is defending champion but lost badly in SEC tournament semifinal
- Iowa State lost to Arizona twice in Big 12 play but dominated otherwise

---

## Appendix B: Team Name Alias Map

Use this to reconcile names across data sources:

```json
{
  "UConn": ["Connecticut", "UCONN"],
  "Miami (FL)": ["Miami", "Miami Florida", "Miami-FL"],
  "Miami (OH)": ["Miami Ohio", "Miami-OH", "Miami (Ohio)", "Miami RedHawks"],
  "UCF": ["Central Florida"],
  "VCU": ["Virginia Commonwealth"],
  "SMU": ["Southern Methodist"],
  "BYU": ["Brigham Young"],
  "LIU": ["Long Island", "Long Island University"],
  "UNC": ["North Carolina", "N. Carolina"],
  "NC State": ["N.C. State", "North Carolina State"],
  "Texas A&M": ["Texas A&M", "TAMU"],
  "Cal Baptist": ["California Baptist", "CBU"],
  "UMBC": ["Maryland-Baltimore County"],
  "Prairie View A&M": ["Prairie View", "PVAMU"],
  "NDSU": ["North Dakota State", "N. Dakota St."]
}
```

---

## Appendix C: Implementation Notes for Claude Code

1. **Language:** Python 3. Use `requests` for HTTP, `beautifulsoup4` for HTML
   parsing, standard library `json` for data. Install any missing packages
   via `pip install`.

2. **Directory structure:**
   ```
   project_root/
   ├── march_madness_prediction_plan.md   (this file)
   ├── data/                              (intermediate data files)
   │   ├── bracket.json
   │   ├── bpi_ratings.json
   │   ├── srs_ratings.json
   │   ├── betting_odds.json
   │   ├── composite_ratings.json
   │   └── ...
   ├── src/                               (scripts)
   │   ├── 01_fetch_bracket.py
   │   ├── 02_fetch_ratings.py
   │   ├── 03_build_composite.py
   │   └── 04_predict_bracket.py
   └── output/
       ├── bracket_predictions.txt        (FINAL OUTPUT)
       └── prediction_rationale.txt       (optional)
   ```

3. **Execution order:** Run scripts 01 through 04 in sequence, or combine into
   a single orchestration script. Each script should be independently re-runnable.

4. **Error tolerance:** Every web fetch must be wrapped in try/except. Log
   failures. Never let a single scraping failure abort the entire pipeline.

5. **Critical success criterion:** The file `output/bracket_predictions.txt`
   must exist at completion and must contain exactly 63 game predictions for
   the main bracket (plus 4 First Four predictions = 67 total).
