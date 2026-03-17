# Project Plan: 2026 NCAA Men's Tournament Bracket Prediction
**Prepared for execution by Claude Code**
**Date composed:** March 16, 2026

---

## Overview

Predict the winner of all 63 games in the 2026 NCAA Division I Men's Basketball Tournament main bracket (seeds 1–16 in each of four regions, after First Four play-in games are resolved). Output must be a human-readable file listing every predicted game result.

---

## The Bracket

The bracket was announced on Selection Sunday, March 15, 2026. It is embedded here in full so no re-discovery is needed. All First Four outcomes must be predicted first, as those winners enter the main bracket.

### First Four (Dayton, OH — UD Arena)

These four games produce teams that fill open slots in the main bracket before Round 1 begins.

| Game | Teams | Winner feeds |
|------|-------|-------------|
| F1 | (16) UMBC vs. (16) Howard | Midwest (1) Michigan's side |
| F2 | (11) Texas vs. (11) NC State | West (6) BYU's side |
| F3 | (16) Prairie View A&M vs. (16) Lehigh | South (1) Florida's side |
| F4 | (11) SMU vs. (11) Miami (OH) | Midwest (6) Tennessee's side |

### East Region

| Seed | Team |
|------|------|
| 1 | Duke |
| 2 | UConn |
| 3 | Michigan State |
| 4 | Kansas |
| 5 | St. John's |
| 6 | Louisville |
| 7 | UCLA |
| 8 | Ohio State |
| 9 | TCU |
| 10 | UCF |
| 11 | South Florida |
| 12 | Northern Iowa |
| 13 | Cal Baptist |
| 14 | North Dakota State |
| 15 | Furman |
| 16 | Siena |

Round 1 matchups: 1v16, 8v9, 5v12, 4v13, 6v11, 3v14, 7v10, 2v15

### West Region

| Seed | Team |
|------|------|
| 1 | Arizona |
| 2 | Purdue |
| 3 | Gonzaga |
| 4 | Arkansas |
| 5 | Wisconsin |
| 6 | BYU |
| 7 | Miami (FL) |
| 8 | Villanova |
| 9 | Utah State |
| 10 | Missouri |
| 11 | Texas/NC State winner (First Four F2) |
| 12 | High Point |
| 13 | Hawaii |
| 14 | Kennesaw State |
| 15 | Queens (NC) |
| 16 | LIU |

Round 1 matchups: 1v16, 8v9, 5v12, 4v13, 6v11, 3v14, 7v10, 2v15

### Midwest Region

| Seed | Team |
|------|------|
| 1 | Michigan |
| 2 | Iowa State |
| 3 | Virginia |
| 4 | Alabama |
| 5 | Texas Tech |
| 6 | Tennessee |
| 7 | Kentucky |
| 8 | Georgia |
| 9 | Saint Louis |
| 10 | Santa Clara |
| 11 | SMU/Miami (OH) winner (First Four F4) |
| 12 | Akron |
| 13 | Hofstra |
| 14 | Wright State |
| 15 | Tennessee State |
| 16 | UMBC/Howard winner (First Four F1) |

Round 1 matchups: 1v16, 8v9, 5v12, 4v13, 6v11, 3v14, 7v10, 2v15

### South Region

| Seed | Team |
|------|------|
| 1 | Florida |
| 2 | Houston |
| 3 | Illinois |
| 4 | Nebraska |
| 5 | Vanderbilt |
| 6 | North Carolina |
| 7 | Saint Mary's |
| 8 | Clemson |
| 9 | Iowa |
| 10 | Texas A&M |
| 11 | VCU |
| 12 | McNeese |
| 13 | Troy |
| 14 | Penn |
| 15 | Idaho |
| 16 | Prairie View A&M/Lehigh winner (First Four F3) |

Round 1 matchups: 1v16, 8v9, 5v12, 4v13, 6v11, 3v14, 7v10, 2v15

---

## Prediction Methodology

The goal is accuracy. Use the following multi-signal approach, assembling a **composite score** for each team that can be used to predict head-to-head matchups.

### Step 1 — Data Collection

For each of the 64 main-bracket teams (plus the 8 First Four teams), gather the following via web search. Store raw data in `data/raw_team_stats.json`.

**Primary signals (highest weight):**
- KenPom adjusted efficiency margin (AdjEM) — the single best predictor of NCAA Tournament outcomes historically
- NET ranking (NCAA's official metric)
- Strength of schedule (both KenPom SOS and NET SOS)
- Recent form: record in last 10 games

**Secondary signals:**
- Adjusted offensive efficiency (AdjOE) and adjusted defensive efficiency (AdjDE) from KenPom
- Tempo (possessions per game — relevant for upset potential)
- Season record and conference record
- Conference tournament result (champion, runner-up, early exit, etc.)

**Tertiary / contextual signals:**
- Head coach tournament experience and historical tournament win rate
- Key injuries or roster news as of March 16, 2026 (search for each team)
- Travel/geography disadvantage (compare team's home region to game site)
- Historical seed matchup win rates (e.g., 12-seeds beat 5-seeds ~35% of the time)

**Data sources to query (in order of preference):**
1. `https://kenpom.com` — AdjEM, AdjOE, AdjDE, tempo, SOS (scrape or search for each team)
2. `https://www.ncaa.com/rankings/basketball-men/d1/ncaa-mens-basketball-net-rankings` — NET rankings
3. ESPN, CBS Sports, or Sports Reference for recent game logs and injury reports
4. Web search queries like `"[Team] KenPom 2026"` and `"[Team] NCAA tournament 2026 injury"` as fallback

Save all gathered data to `data/raw_team_stats.json` keyed by team name.

### Step 2 — Score Normalization

Using `predict.py`, normalize all signals to a common 0–100 scale:
- Invert rankings (rank 1 = highest score)
- Z-score or min-max normalize efficiency margins
- Convert win percentages to 0–100

Compute a **composite strength score** for each team as a weighted sum:

| Signal | Weight |
|--------|--------|
| KenPom AdjEM | 35% |
| NET ranking | 20% |
| AdjOE − AdjDE spread | 15% |
| Recent form (last 10 games) | 15% |
| SOS | 10% |
| Contextual/injury adjustments | 5% |

Store normalized scores in `data/team_scores.json`.

### Step 3 — Game Prediction Logic

For each matchup, predict the winner using the following rules, implemented in `predict.py`:

1. **Compute score delta:** `delta = winner_score - loser_score` between the two teams.
2. **Apply seed-line upset probability overlay:** Historical NCAA data shows that certain seed matchups have predictable upset rates. Hard-code these historical baseline upset rates and use them to modulate the composite score prediction when the delta is within a threshold:
   - 1 vs 16: ~99% favor the 1-seed (but not 100%)
   - 2 vs 15: ~94%
   - 3 vs 14: ~85%
   - 4 vs 13: ~79%
   - 5 vs 12: ~65%
   - 6 vs 11: ~62%
   - 7 vs 10: ~61%
   - 8 vs 9: ~51%
   - In later rounds: rely primarily on composite scores
3. **Upset trigger:** If a lower-seeded team's composite score exceeds the higher-seeded team's score by more than 5 points (on the normalized 0–100 scale), predict the upset regardless of seed line.
4. **Predict each round in sequence**, feeding winners forward into the next round's matchup table.

### Step 4 — Bracket Simulation

Simulate all 67 games (4 First Four + 63 main bracket) in round order:
- First Four (4 games)
- Round of 64 (32 games)
- Round of 32 (16 games)
- Sweet 16 (8 games)
- Elite Eight (4 games)
- Final Four (2 games)
- Championship (1 game)

For each game, record: Round, Region (or "Final Four"/"Championship"), Seed + Team A vs. Seed + Team B, Predicted Winner, Composite Score A, Composite Score B.

---

## File and Directory Structure

All work products must be preserved. Use the following layout inside the workspace directory:

```
/
├── march_madness_2026_plan.md       ← this file (input)
├── data/
│   ├── raw_team_stats.json          ← all gathered stats, keyed by team name
│   └── team_scores.json             ← normalized composite scores per team
├── predict.py                       ← main prediction script
├── logs/
│   └── data_collection.log          ← log of all web queries and results
└── output/
    ├── predictions_full.txt         ← PRIMARY OUTPUT: all 67 game predictions, human-readable
    └── predictions_bracket.md      ← SECONDARY OUTPUT: bracket formatted by round and region
```

---

## Execution Steps for Claude Code

Execute in order. Each step must complete before the next begins.

### Step A — Verify and resolve First Four teams
Search for the four First Four matchups to confirm the teams and find any relevant pre-game information (injury news, recent form). Record the predicted winners of all four First Four games. These winners will fill the open 11- and 16-seed slots in the West, Midwest, and South regions.

### Step B — Collect team data
For each of the 68 teams, query the data sources listed in Step 1 of the methodology. Prioritize KenPom and NET. Accept partial data if a source is unavailable — do not block on any single source. Log all queries and results to `logs/data_collection.log`. Save results to `data/raw_team_stats.json`.

### Step C — Normalize and score
Run the normalization logic (Step 2 of methodology) on `raw_team_stats.json`. Output `data/team_scores.json`. Print a sanity-check summary: top 10 teams by composite score and bottom 10.

### Step D — Predict all games
Run the game prediction logic (Steps 3–4 of methodology) over all 67 games in round order. Feed winners forward after each round. Save full game-by-game results to `output/predictions_full.txt` and `output/predictions_bracket.md`.

### Step E — Validate output
Confirm that:
- Exactly 4 First Four games are predicted
- Exactly 32 Round of 64 games are predicted
- Exactly 16 Round of 32 games are predicted
- Exactly 8 Sweet 16 games are predicted
- Exactly 4 Elite Eight games are predicted
- Exactly 2 Final Four games are predicted
- Exactly 1 Championship game is predicted
- Every team appears in the bracket exactly once per round they are predicted to win
- No team plays itself

Print validation results to console. If any check fails, diagnose and re-run.

---

## Output Format Specification

### `output/predictions_full.txt`
Plain text, human-readable. One game per line, all 67 games grouped by round. Format:

```
=== FIRST FOUR ===
[F1] (16) UMBC vs. (16) Howard  →  WINNER: Howard
[F2] (11) Texas vs. (11) NC State  →  WINNER: Texas
[F3] (16) Prairie View A&M vs. (16) Lehigh  →  WINNER: Lehigh
[F4] (11) SMU vs. (11) Miami (OH)  →  WINNER: SMU

=== ROUND OF 64 — EAST ===
(1) Duke vs. (16) Siena  →  WINNER: Duke
...

=== ROUND OF 32 — EAST ===
...

=== SWEET 16 — EAST ===
...

=== ELITE EIGHT — EAST ===
...

=== FINAL FOUR ===
(East winner) Duke vs. (West winner) Arizona  →  WINNER: Duke
(Midwest winner) Michigan vs. (South winner) Florida  →  WINNER: Florida

=== CHAMPIONSHIP ===
Duke vs. Florida  →  WINNER: Florida

=== CHAMPION: Florida ===
```

### `output/predictions_bracket.md`
Markdown table or bracket-style ASCII art organized by region, showing all rounds in columnar layout. Intended for human review.

---

## Constraints and Error Handling

- **No human input during execution.** If a data source is unavailable, fall back to the next source, then to seed-line historical averages alone for that team.
- **Web access is available** and should be used aggressively in Step B.
- **Python is the primary scripting language.** Use only standard library plus `requests`, `beautifulsoup4`, and `json` — install via pip if needed.
- **All intermediate files must be saved**, not just the final output.
- **Do not re-do research that is already done.** If `raw_team_stats.json` is partially populated, resume from where it left off.
- If the prediction script encounters a missing score for a team, fall back to using seed rank as a proxy (lower seed number = higher score), and log a warning.

---

## Success Criteria

The project is complete when:
1. `output/predictions_full.txt` exists and contains exactly 67 predicted game outcomes in the specified format.
2. `output/predictions_bracket.md` exists and is legible.
3. All data files and the prediction script are preserved in the workspace.
4. Validation in Step E passes all checks.