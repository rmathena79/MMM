"""
predict.py - 2026 NCAA Men's Basketball Tournament Bracket Predictor
Reads raw_team_stats.json, normalizes signals, and predicts all 67 games.
"""

import json
import os
import sys
from pathlib import Path

# ── Directory setup ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
OUT_DIR  = BASE_DIR / "output"
for d in (DATA_DIR, LOGS_DIR, OUT_DIR):
    d.mkdir(exist_ok=True)

# ── Load raw stats ────────────────────────────────────────────────────────────
with open(DATA_DIR / "raw_team_stats.json") as f:
    raw = json.load(f)

teams_raw = raw["teams"]

# ── Normalization helpers ─────────────────────────────────────────────────────
def normalize_kenpom_rank(rank, n_teams=370):
    """Higher rank number = worse. Invert so score is 0-100."""
    return max(0.0, (n_teams - rank) / (n_teams - 1) * 100)

def normalize_net_rank(rank, n_teams=370):
    return max(0.0, (n_teams - rank) / (n_teams - 1) * 100)

def normalize_adjEM(em):
    """AdjEM roughly spans -30 to +40. Normalize to 0-100."""
    lo, hi = -30.0, 40.0
    return max(0.0, min(100.0, (em - lo) / (hi - lo) * 100))

def normalize_spread(adjOE, adjDE):
    """OE-DE spread: higher is better. Roughly -15 to +45."""
    spread = adjOE - adjDE
    lo, hi = -15.0, 45.0
    return max(0.0, min(100.0, (spread - lo) / (hi - lo) * 100))

def normalize_recent_form(w10):
    """Wins in last 10 games: 0-10."""
    return (w10 / 10.0) * 100.0

def normalize_sos(sos_rank, n_teams=370):
    """Lower SOS rank number = harder schedule = better. Invert."""
    return max(0.0, (n_teams - sos_rank) / (n_teams - 1) * 100)

# ── Composite score weights ───────────────────────────────────────────────────
WEIGHTS = {
    "kenpom_adjEM":   0.35,
    "net_rank":       0.20,
    "oe_de_spread":   0.15,
    "recent_form":    0.15,
    "sos":            0.10,
    "contextual":     0.05,   # injury/upside factor
}

# ── Build composite scores ────────────────────────────────────────────────────
team_scores = {}

for name, t in teams_raw.items():
    s_adjEM      = normalize_adjEM(t["kenpom_adjEM"])
    s_net        = normalize_net_rank(t["net_rank"])
    s_spread     = normalize_spread(t["kenpom_adjOE"], t["kenpom_adjDE"])
    s_form       = normalize_recent_form(t["recent_form_w10"])
    s_sos        = normalize_sos(t["sos_rank"])
    # Contextual: start at 50 (neutral), adjust for injury
    s_contextual = max(0.0, 50.0 + t.get("injury_penalty", 0) * 5)

    composite = (
        WEIGHTS["kenpom_adjEM"]  * s_adjEM +
        WEIGHTS["net_rank"]      * s_net   +
        WEIGHTS["oe_de_spread"]  * s_spread +
        WEIGHTS["recent_form"]   * s_form  +
        WEIGHTS["sos"]           * s_sos   +
        WEIGHTS["contextual"]    * s_contextual
    )

    team_scores[name] = {
        "seed":          t["seed"],
        "region":        t["region"],
        "record":        t["record"],
        "composite":     round(composite, 2),
        "s_adjEM":       round(s_adjEM, 2),
        "s_net":         round(s_net, 2),
        "s_spread":      round(s_spread, 2),
        "s_form":        round(s_form, 2),
        "s_sos":         round(s_sos, 2),
        "s_contextual":  round(s_contextual, 2),
        "injury_note":   t.get("injury_note", ""),
    }

# Save team_scores.json
with open(DATA_DIR / "team_scores.json", "w") as f:
    json.dump(team_scores, f, indent=2)
print("Saved data/team_scores.json")

# ── Historical seed upset rates (base probability for FAVORITE to win) ────────
# Key: (higher_seed, lower_seed) – probability the HIGHER seed (favorite) wins
SEED_WIN_PROB = {
    (1, 16): 0.99,
    (2, 15): 0.94,
    (3, 14): 0.85,
    (4, 13): 0.79,
    (5, 12): 0.65,
    (6, 11): 0.62,
    (7, 10): 0.61,
    (8,  9): 0.51,
    # Same seed (First Four)
    (11,11): 0.50,
    (16,16): 0.50,
}

UPSET_SCORE_THRESHOLD = 5.0   # if lower-seed outscores higher-seed by this much → upset

def get_seed_win_prob(s1, s2):
    """Return probability that team with seed s1 beats team with seed s2."""
    hi = min(s1, s2)
    lo = max(s1, s2)
    if s1 == s2:
        return 0.50
    prob_hi_wins = SEED_WIN_PROB.get((hi, lo), 0.50)
    if s1 == hi:
        return prob_hi_wins
    else:
        return 1.0 - prob_hi_wins

def predict_game(team_a, team_b):
    """
    Predict winner between team_a and team_b.
    Returns (winner_name, loser_name, upset_flag, score_delta).
    """
    sa = team_scores[team_a]
    sb = team_scores[team_b]
    seed_a = sa["seed"]
    seed_b = sb["seed"]
    score_a = sa["composite"]
    score_b = sb["composite"]
    delta = score_a - score_b   # positive → team_a better by composite

    # Determine favorite by seed
    if seed_a <= seed_b:
        fav, dog = team_a, team_b
        dog_better_by = score_b - score_a
    else:
        fav, dog = team_b, team_a
        dog_better_by = score_a - score_b

    # Upset trigger: if underdog's composite exceeds favorite's by > threshold
    if dog_better_by > UPSET_SCORE_THRESHOLD:
        winner = dog
        upset = (fav != dog)
    else:
        winner = fav
        upset = False

    loser = team_b if winner == team_a else team_a
    return winner, loser, upset, round(abs(delta), 2)

# ── Bracket definition ────────────────────────────────────────────────────────
# First Four placeholders resolved below
FF_WINNERS = {}   # e.g. "F1" -> winning team name

FIRST_FOUR = [
    {"id": "F1", "team_a": "UMBC",            "team_b": "Howard",
     "region": "Midwest", "seed": 16,
     "desc": "(16) UMBC vs. (16) Howard → winner feeds Midwest as 16-seed vs Michigan"},
    {"id": "F2", "team_a": "Texas",           "team_b": "NC State",
     "region": "West",    "seed": 11,
     "desc": "(11) Texas vs. (11) NC State → winner feeds West as 11-seed vs BYU"},
    {"id": "F3", "team_a": "Prairie View A&M","team_b": "Lehigh",
     "region": "South",   "seed": 16,
     "desc": "(16) Prairie View A&M vs. (16) Lehigh → winner feeds South as 16-seed vs Florida"},
    {"id": "F4", "team_a": "SMU",             "team_b": "Miami (OH)",
     "region": "Midwest", "seed": 11,
     "desc": "(11) SMU vs. (11) Miami (OH) → winner feeds Midwest as 11-seed vs Tennessee"},
]

# Round of 64 matchups (1v16, 8v9, 5v12, 4v13, 6v11, 3v14, 7v10, 2v15)
# First Four slots are labeled "FF:F1" etc. and resolved at runtime.
ROUND64 = {
    "East": [
        ("Duke",          "Siena",           1, 16),
        ("Ohio State",    "TCU",             8,  9),
        ("St. John's",    "Northern Iowa",   5, 12),
        ("Kansas",        "Cal Baptist",     4, 13),
        ("Louisville",    "South Florida",   6, 11),
        ("Michigan State","North Dakota State",3,14),
        ("UCLA",          "UCF",             7, 10),
        ("UConn",         "Furman",          2, 15),
    ],
    "West": [
        ("Arizona",       "LIU",             1, 16),
        ("Villanova",     "Utah State",      8,  9),
        ("Wisconsin",     "High Point",      5, 12),
        ("Arkansas",      "Hawaii",          4, 13),
        ("BYU",           "FF:F2",           6, 11),   # F2 winner
        ("Gonzaga",       "Kennesaw State",  3, 14),
        ("Miami (FL)",    "Missouri",        7, 10),
        ("Purdue",        "Queens (NC)",     2, 15),
    ],
    "Midwest": [
        ("Michigan",      "FF:F1",           1, 16),   # F1 winner
        ("Georgia",       "Saint Louis",     8,  9),
        ("Texas Tech",    "Akron",           5, 12),
        ("Alabama",       "Hofstra",         4, 13),
        ("Tennessee",     "FF:F4",           6, 11),   # F4 winner
        ("Virginia",      "Wright State",    3, 14),
        ("Kentucky",      "Santa Clara",     7, 10),
        ("Iowa State",    "Tennessee State", 2, 15),
    ],
    "South": [
        ("Florida",       "FF:F3",           1, 16),   # F3 winner
        ("Clemson",       "Iowa",            8,  9),
        ("Vanderbilt",    "McNeese",         5, 12),
        ("Nebraska",      "Troy",            4, 13),
        ("North Carolina","VCU",             6, 11),
        ("Illinois",      "Penn",            3, 14),
        ("Saint Mary's",  "Texas A&M",       7, 10),
        ("Houston",       "Idaho",           2, 15),
    ],
}

# ── Game-by-game simulation ───────────────────────────────────────────────────
results = []   # list of dicts: {round, region, game_num, team_a, team_b, winner, upset, delta, note}

def record_game(rnd, region, team_a, team_b, seed_a, seed_b, note=""):
    winner, loser, upset, delta = predict_game(team_a, team_b)
    results.append({
        "round":   rnd,
        "region":  region,
        "team_a":  team_a,
        "seed_a":  seed_a,
        "team_b":  team_b,
        "seed_b":  seed_b,
        "winner":  winner,
        "loser":   loser,
        "upset":   upset,
        "delta":   delta,
        "note":    note,
    })
    return winner

# Step 1: First Four
print("\n=== FIRST FOUR ===")
for ff in FIRST_FOUR:
    w = record_game("First Four", ff["region"], ff["team_a"], ff["team_b"],
                    ff["seed"], ff["seed"], ff["desc"])
    FF_WINNERS[ff["id"]] = w
    print(f"  [{ff['id']}] {ff['team_a']} vs {ff['team_b']} → {w}")

# Resolve FF placeholders
def resolve(name):
    if name.startswith("FF:"):
        fid = name.split(":")[1]
        return FF_WINNERS[fid]
    return name

def get_seed(name):
    return team_scores[name]["seed"]

# Step 2: Round of 64
print("\n=== ROUND OF 64 ===")
r32_by_region = {reg: [] for reg in ["East","West","Midwest","South"]}

for region, matchups in ROUND64.items():
    for ta, tb, sa, sb in matchups:
        ta = resolve(ta)
        tb = resolve(tb)
        # Use actual seed from team_scores for FF winners
        sa = get_seed(ta)
        sb = get_seed(tb)
        w = record_game("R64", region, ta, tb, sa, sb)
        r32_by_region[region].append(w)
        game = results[-1]
        upset_tag = " **UPSET**" if game["upset"] else ""
        print(f"  {region}: ({sa}) {ta} vs ({sb}) {tb} → {w}{upset_tag}")

# Step 3: Round of 32
print("\n=== ROUND OF 32 ===")
s16_by_region = {reg: [] for reg in ["East","West","Midwest","South"]}

for region, winners in r32_by_region.items():
    # Pair: [0]v[1], [2]v[3], [4]v[5], [6]v[7]  (bracket order)
    for i in range(0, 8, 2):
        ta = winners[i]
        tb = winners[i+1]
        sa = get_seed(ta)
        sb = get_seed(tb)
        w = record_game("R32", region, ta, tb, sa, sb)
        s16_by_region[region].append(w)
        game = results[-1]
        upset_tag = " **UPSET**" if game["upset"] else ""
        print(f"  {region}: ({sa}) {ta} vs ({sb}) {tb} → {w}{upset_tag}")

# Step 4: Sweet 16
print("\n=== SWEET 16 ===")
e8_by_region = {reg: [] for reg in ["East","West","Midwest","South"]}

for region, winners in s16_by_region.items():
    for i in range(0, 4, 2):
        ta = winners[i]
        tb = winners[i+1]
        sa = get_seed(ta)
        sb = get_seed(tb)
        w = record_game("Sweet16", region, ta, tb, sa, sb)
        e8_by_region[region].append(w)
        game = results[-1]
        upset_tag = " **UPSET**" if game["upset"] else ""
        print(f"  {region}: ({sa}) {ta} vs ({sb}) {tb} → {w}{upset_tag}")

# Step 5: Elite Eight
print("\n=== ELITE EIGHT ===")
ff_teams = []

for region, winners in e8_by_region.items():
    ta = winners[0]
    tb = winners[1]
    sa = get_seed(ta)
    sb = get_seed(tb)
    w = record_game("Elite8", region, ta, tb, sa, sb)
    ff_teams.append((w, region))
    game = results[-1]
    upset_tag = " **UPSET**" if game["upset"] else ""
    print(f"  {region}: ({sa}) {ta} vs ({sb}) {tb} → {w}{upset_tag}")

# Step 6: Final Four
# Traditional bracket pairings: East vs West, Midwest vs South
print("\n=== FINAL FOUR ===")
ff_results = []
# Find each region's winner
def ff_team(region):
    for t, r in ff_teams:
        if r == region:
            return t
    return None

east_w    = ff_team("East")
west_w    = ff_team("West")
midwest_w = ff_team("Midwest")
south_w   = ff_team("South")

# Matchup 1: East vs West
ta, tb = east_w, west_w
sa, sb = get_seed(ta), get_seed(tb)
sf1 = record_game("FinalFour", "National", ta, tb, sa, sb,
                  note="East champion vs West champion")
game = results[-1]
upset_tag = " **UPSET**" if game["upset"] else ""
print(f"  East ({sa}) {ta} vs West ({sb}) {tb} → {sf1}{upset_tag}")
ff_results.append(sf1)

# Matchup 2: Midwest vs South
ta, tb = midwest_w, south_w
sa, sb = get_seed(ta), get_seed(tb)
sf2 = record_game("FinalFour", "National", ta, tb, sa, sb,
                  note="Midwest champion vs South champion")
game = results[-1]
upset_tag = " **UPSET**" if game["upset"] else ""
print(f"  Midwest ({sa}) {ta} vs South ({sb}) {tb} → {sf2}{upset_tag}")
ff_results.append(sf2)

# Step 7: Championship
print("\n=== CHAMPIONSHIP ===")
ta, tb = ff_results[0], ff_results[1]
sa, sb = get_seed(ta), get_seed(tb)
champion = record_game("Championship", "National", ta, tb, sa, sb)
game = results[-1]
upset_tag = " **UPSET**" if game["upset"] else ""
print(f"  ({sa}) {ta} vs ({sb}) {tb} → {champion}{upset_tag}")

# ── Validation ────────────────────────────────────────────────────────────────
round_counts = {}
for g in results:
    round_counts[g["round"]] = round_counts.get(g["round"], 0) + 1

EXPECTED = {
    "First Four":   4,
    "R64":         32,
    "R32":         16,
    "Sweet16":      8,
    "Elite8":       4,
    "FinalFour":    2,
    "Championship": 1,
}

print("\n=== VALIDATION ===")
all_ok = True
for rnd, exp in EXPECTED.items():
    got = round_counts.get(rnd, 0)
    status = "OK" if got == exp else f"ERROR (got {got})"
    if got != exp:
        all_ok = False
    print(f"  {rnd}: expected {exp}, got {got} → {status}")

total_expected = sum(EXPECTED.values())
total_got      = sum(round_counts.values())
print(f"  TOTAL: expected {total_expected}, got {total_got} → {'OK' if total_got == total_expected else 'ERROR'}")
if not all_ok:
    print("VALIDATION FAILED", file=sys.stderr)

# ── Write output files ────────────────────────────────────────────────────────
def seed_str(s):
    return f"({s})"

lines_txt = []
lines_md  = []

def section(title):
    lines_txt.append("")
    lines_txt.append(f"=== {title} ===")
    lines_md.append(f"\n## {title}\n")

def game_line(g):
    sa, ta = g["seed_a"], g["team_a"]
    sb, tb = g["seed_b"], g["team_b"]
    w = g["winner"]
    upset = " *** UPSET ***" if g["upset"] else ""
    delta_info = f"(Δ score: {g['delta']:.1f})"
    txt = f"{seed_str(sa)} {ta} vs. {seed_str(sb)} {tb}  →  WINNER: {w}{upset}  {delta_info}"
    md  = f"| {seed_str(sa)} {ta} | {seed_str(sb)} {tb} | **{w}**{' 🔥' if g['upset'] else ''} | {g['delta']:.1f} |"
    lines_txt.append(txt)
    lines_md.append(md)

md_table_header = "| Team A | Team B | Winner | Score Δ |"
md_table_sep    = "|--------|--------|--------|---------|"

section("FIRST FOUR")
lines_md.append(md_table_header)
lines_md.append(md_table_sep)
for g in results:
    if g["round"] == "First Four":
        game_line(g)

for region in ["East", "West", "Midwest", "South"]:
    section(f"ROUND OF 64 — {region.upper()}")
    lines_md.append(md_table_header)
    lines_md.append(md_table_sep)
    for g in results:
        if g["round"] == "R64" and g["region"] == region:
            game_line(g)

for region in ["East", "West", "Midwest", "South"]:
    section(f"ROUND OF 32 — {region.upper()}")
    lines_md.append(md_table_header)
    lines_md.append(md_table_sep)
    for g in results:
        if g["round"] == "R32" and g["region"] == region:
            game_line(g)

for region in ["East", "West", "Midwest", "South"]:
    section(f"SWEET 16 — {region.upper()}")
    lines_md.append(md_table_header)
    lines_md.append(md_table_sep)
    for g in results:
        if g["round"] == "Sweet16" and g["region"] == region:
            game_line(g)

for region in ["East", "West", "Midwest", "South"]:
    section(f"ELITE EIGHT — {region.upper()}")
    lines_md.append(md_table_header)
    lines_md.append(md_table_sep)
    for g in results:
        if g["round"] == "Elite8" and g["region"] == region:
            game_line(g)

section("FINAL FOUR")
lines_md.append(md_table_header)
lines_md.append(md_table_sep)
for g in results:
    if g["round"] == "FinalFour":
        game_line(g)

section("CHAMPIONSHIP")
lines_md.append(md_table_header)
lines_md.append(md_table_sep)
for g in results:
    if g["round"] == "Championship":
        game_line(g)

lines_txt.append("")
lines_txt.append(f"=== CHAMPION: {champion} ===")
lines_md.append(f"\n## CHAMPION\n\n### 🏆 {champion}")

# Write predictions_full.txt
with open(OUT_DIR / "predictions_full.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines_txt))
print("\nSaved output/predictions_full.txt")

# Write predictions_bracket.md
md_header = [
    "# 2026 NCAA Men's Basketball Tournament -- Full Bracket Predictions",
    "",
    f"**Generated:** 2026-03-16  ",
    f"**Model:** Composite score (KenPom AdjEM 35% + NET 20% + OE-DE Spread 15% + Recent Form 15% + SOS 10% + Contextual 5%)",
    "",
]
with open(OUT_DIR / "predictions_bracket.md", "w", encoding="utf-8") as f:
    f.write("\n".join(md_header + lines_md))
print("Saved output/predictions_bracket.md")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  2026 NCAA TOURNAMENT PREDICTION COMPLETE")
print(f"{'='*60}")
print(f"\n  CHAMPION: {champion}")
print(f"\n  First Four Winners:")
for fid, w in FF_WINNERS.items():
    print(f"    [{fid}] {w}")

print(f"\n  Regional Champions:")
for region in ["East","West","Midwest","South"]:
    champ = ff_team(region)
    seed  = get_seed(champ)
    print(f"    {region}: ({seed}) {champ}")

print(f"\n  Final Four:")
for g in results:
    if g["round"] == "FinalFour":
        print(f"    {g['team_a']} vs {g['team_b']} → {g['winner']}")

print(f"\n  Championship:")
for g in results:
    if g["round"] == "Championship":
        print(f"    {g['team_a']} vs {g['team_b']} → {g['winner']}")

upsets = [g for g in results if g["upset"]]
print(f"\n  Total upsets predicted: {len(upsets)}")
for u in upsets:
    print(f"    {u['round']} {u['region']}: ({u['seed_b']}) {u['team_b']} over ({u['seed_a']}) {u['team_a']}"
          if u['winner'] == u['team_b'] else
          f"    {u['round']} {u['region']}: ({u['seed_a']}) {u['team_a']} over ({u['seed_b']}) {u['team_b']}")

print(f"\n{'='*60}\n")
