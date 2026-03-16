#!/usr/bin/env python3
"""
2026 NCAA Men's March Madness Bracket Prediction Engine

Multi-source composite model that blends:
- Sports-Reference SRS ratings
- ESPN BPI projections & point spreads
- DraftKings championship futures odds
- Historical seed-performance baselines
"""

import json
import os
import math

# ============================================================================
# PHASE 1: BRACKET STRUCTURE
# ============================================================================

# First Four predictions (from BPI projections)
FIRST_FOUR = {
    "UMBC vs Howard": {"winner": "UMBC", "bpi_spread": 1.5},
    "NC State vs Texas": {"winner": "NC State", "bpi_spread": 0.1},
    "Lehigh vs Prairie View A&M": {"winner": "Lehigh", "bpi_spread": 0.9},
    "SMU vs Miami (OH)": {"winner": "SMU", "bpi_spread": 6.7},
}

# Full bracket after First Four resolution
BRACKET = {
    "East": [
        {"seed_high": 1, "seed_low": 16, "teams": ["Duke", "Siena"]},
        {"seed_high": 8, "seed_low": 9,  "teams": ["Ohio State", "TCU"]},
        {"seed_high": 5, "seed_low": 12, "teams": ["St. John's", "Northern Iowa"]},
        {"seed_high": 4, "seed_low": 13, "teams": ["Kansas", "Cal Baptist"]},
        {"seed_high": 6, "seed_low": 11, "teams": ["Louisville", "South Florida"]},
        {"seed_high": 3, "seed_low": 14, "teams": ["Michigan State", "North Dakota State"]},
        {"seed_high": 7, "seed_low": 10, "teams": ["UCLA", "UCF"]},
        {"seed_high": 2, "seed_low": 15, "teams": ["UConn", "Furman"]},
    ],
    "West": [
        {"seed_high": 1, "seed_low": 16, "teams": ["Arizona", "LIU"]},
        {"seed_high": 8, "seed_low": 9,  "teams": ["Villanova", "Utah State"]},
        {"seed_high": 5, "seed_low": 12, "teams": ["Wisconsin", "High Point"]},
        {"seed_high": 4, "seed_low": 13, "teams": ["Arkansas", "Hawaii"]},
        {"seed_high": 6, "seed_low": 11, "teams": ["BYU", "NC State"]},  # First Four winner
        {"seed_high": 3, "seed_low": 14, "teams": ["Gonzaga", "Kennesaw State"]},
        {"seed_high": 7, "seed_low": 10, "teams": ["Miami (FL)", "Missouri"]},
        {"seed_high": 2, "seed_low": 15, "teams": ["Purdue", "Queens"]},
    ],
    "Midwest": [
        {"seed_high": 1, "seed_low": 16, "teams": ["Michigan", "UMBC"]},  # First Four winner
        {"seed_high": 8, "seed_low": 9,  "teams": ["Georgia", "Saint Louis"]},
        {"seed_high": 5, "seed_low": 12, "teams": ["Texas Tech", "Akron"]},
        {"seed_high": 4, "seed_low": 13, "teams": ["Alabama", "Hofstra"]},
        {"seed_high": 6, "seed_low": 11, "teams": ["Tennessee", "SMU"]},  # First Four winner
        {"seed_high": 3, "seed_low": 14, "teams": ["Virginia", "Wright State"]},
        {"seed_high": 7, "seed_low": 10, "teams": ["Kentucky", "Santa Clara"]},
        {"seed_high": 2, "seed_low": 15, "teams": ["Iowa State", "Tennessee State"]},
    ],
    "South": [
        {"seed_high": 1, "seed_low": 16, "teams": ["Florida", "Lehigh"]},  # First Four winner
        {"seed_high": 8, "seed_low": 9,  "teams": ["Clemson", "Iowa"]},
        {"seed_high": 5, "seed_low": 12, "teams": ["Vanderbilt", "McNeese"]},
        {"seed_high": 4, "seed_low": 13, "teams": ["Nebraska", "Troy"]},
        {"seed_high": 6, "seed_low": 11, "teams": ["North Carolina", "VCU"]},
        {"seed_high": 3, "seed_low": 14, "teams": ["Illinois", "Penn"]},
        {"seed_high": 7, "seed_low": 10, "teams": ["Saint Mary's", "Texas A&M"]},
        {"seed_high": 2, "seed_low": 15, "teams": ["Houston", "Idaho"]},
    ],
}

# Team seed lookup
TEAM_SEEDS = {}
for region, matchups in BRACKET.items():
    for m in matchups:
        TEAM_SEEDS[m["teams"][0]] = m["seed_high"]
        TEAM_SEEDS[m["teams"][1]] = m["seed_low"]

# ============================================================================
# PHASE 2: TEAM STRENGTH DATA
# ============================================================================

# Source D: Sports-Reference SRS ratings (scraped)
SRS_RATINGS = {
    "Michigan": 32.48, "Duke": 31.55, "Arizona": 29.92, "Florida": 27.90,
    "Iowa State": 27.15, "Illinois": 26.45, "Houston": 26.23, "Purdue": 25.64,
    "Gonzaga": 25.11, "Michigan State": 23.44, "Louisville": 23.41,
    "UConn": 22.92, "Vanderbilt": 22.83, "Alabama": 22.70, "Arkansas": 22.43,
    "St. John's": 22.42, "Tennessee": 22.08, "Texas Tech": 21.95,
    "Virginia": 21.60, "Nebraska": 21.54, "Kansas": 21.10, "BYU": 21.04,
    "Kentucky": 19.80, "Georgia": 19.57, "Wisconsin": 19.52,
    "North Carolina": 19.39, "Ohio State": 19.06, "Iowa": 19.00,
    "UCLA": 18.28, "Miami (FL)": 18.04, "NC State": 18.02,
    "Saint Mary's": 17.87, "Utah State": 17.36, "Saint Louis": 17.27,
    "SMU": 17.27, "Clemson": 16.99, "Texas A&M": 16.76,
    "Villanova": 16.30, "Texas": 16.17, "Santa Clara": 15.88,
    "TCU": 15.75, "UCF": 13.30, "South Florida": 13.29, "VCU": 13.19,
    "Missouri": 13.08, "Akron": 9.04, "Northern Iowa": 8.49,
    # Teams not in SRS top 90 - estimated from seed/context
    "Siena": 0.0, "Cal Baptist": 1.0, "North Dakota State": 2.0,
    "Furman": 3.0, "LIU": -3.0, "High Point": 4.0, "Hawaii": 2.0,
    "Kennesaw State": 1.0, "Queens": -2.0, "UMBC": 2.0,
    "Howard": 0.5, "Hofstra": 5.0, "Wright State": 2.0,
    "Tennessee State": -1.0, "Miami (OH)": 3.0, "Lehigh": 3.5,
    "Prairie View A&M": 2.5, "McNeese": 6.0, "Troy": 4.0,
    "Penn": 3.0, "Idaho": -2.0,
}

# Source E: ESPN BPI point spread projections (scraped) - converted to implied ratings
# BPI spread tells us relative strength; we convert to an estimated rating
BPI_SPREADS = {
    # First Four
    ("UMBC", "Howard"): ("UMBC", 1.5),
    ("NC State", "Texas"): ("NC State", 0.1),
    ("Lehigh", "Prairie View A&M"): ("Lehigh", 0.9),
    ("SMU", "Miami (OH)"): ("SMU", 6.7),
    # Round of 64
    ("Duke", "Siena"): ("Duke", 28.9),
    ("Ohio State", "TCU"): ("Ohio State", 4.0),
    ("St. John's", "Northern Iowa"): ("St. John's", 10.8),
    ("Kansas", "Cal Baptist"): ("Kansas", 15.8),
    ("Louisville", "South Florida"): ("Louisville", 9.1),
    ("Michigan State", "North Dakota State"): ("Michigan State", 17.4),
    ("UCLA", "UCF"): ("UCLA", 6.0),
    ("UConn", "Furman"): ("UConn", 20.6),
    ("Arizona", "LIU"): ("Arizona", 28.5),
    ("Villanova", "Utah State"): ("Utah State", 0.4),  # Utah State slight fav
    ("Wisconsin", "High Point"): ("Wisconsin", 7.3),
    ("Arkansas", "Hawaii"): ("Arkansas", 15.0),
    ("Gonzaga", "Kennesaw State"): ("Gonzaga", 19.2),
    ("Miami (FL)", "Missouri"): ("Miami (FL)", 1.3),
    ("Purdue", "Queens"): ("Purdue", 23.8),
    ("Michigan", "UMBC"): ("Michigan", 27.0),  # estimated for First Four winner
    ("Georgia", "Saint Louis"): ("Georgia", 0.2),
    ("Texas Tech", "Akron"): ("Texas Tech", 9.5),
    ("Alabama", "Hofstra"): ("Alabama", 13.8),
    ("Tennessee", "SMU"): ("Tennessee", 5.0),  # estimated for First Four winner
    ("Virginia", "Wright State"): ("Virginia", 16.2),
    ("Kentucky", "Santa Clara"): ("Kentucky", 6.0),
    ("Iowa State", "Tennessee State"): ("Iowa State", 25.6),
    ("Florida", "Lehigh"): ("Florida", 26.0),  # estimated for First Four winner
    ("Clemson", "Iowa"): ("Clemson", 0.1),  # BPI: Clemson by 0.1
    ("Vanderbilt", "McNeese"): ("Vanderbilt", 9.2),
    ("Nebraska", "Troy"): ("Nebraska", 15.9),
    ("North Carolina", "VCU"): ("North Carolina", 2.9),
    ("Illinois", "Penn"): ("Illinois", 22.4),
    ("Saint Mary's", "Texas A&M"): ("Saint Mary's", 0.8),
    ("Houston", "Idaho"): ("Houston", 25.1),
    ("BYU", "NC State"): ("BYU", 3.0),  # estimated
}

# Championship futures odds (from plan Appendix A) - higher implied prob = stronger
FUTURES_IMPLIED_PROB = {
    "Duke": 0.23, "Michigan": 0.22, "Arizona": 0.20, "Florida": 0.12,
    "Houston": 0.09, "Iowa State": 0.06, "Illinois": 0.05,
    "Michigan State": 0.05, "UConn": 0.05, "Purdue": 0.03,
}

# ============================================================================
# PHASE 3: BUILD COMPOSITE RATINGS
# ============================================================================

def normalize_to_zscores(ratings_dict):
    """Convert raw ratings to z-scores."""
    values = list(ratings_dict.values())
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    stdev = math.sqrt(variance) if variance > 0 else 1.0
    return {team: (rating - mean) / stdev for team, rating in ratings_dict.items()}


def build_bpi_implied_ratings():
    """
    Convert BPI point spreads into implied team ratings.
    Use a network/anchor approach: anchor Duke at SRS-equivalent, then derive others.
    Simpler approach: use spreads as pairwise constraints and solve approximately.

    For simplicity, we use the BPI spread as a direct strength indicator relative
    to each opponent, then average each team's implied ratings across all its matchups.
    """
    # For each team, collect all spread-based implied ratings
    team_implied = {}

    for (team_a, team_b), (favored, spread) in BPI_SPREADS.items():
        # If team_a is favored, team_a is `spread` points better
        if favored == team_a:
            diff = spread
        else:
            diff = -spread

        # Use SRS of the opponent as anchor if available
        if team_b in SRS_RATINGS and team_a not in [
            "UMBC", "Howard", "Lehigh", "Prairie View A&M", "SMU", "Miami (OH)",
            "NC State", "Texas"
        ]:
            implied_a = SRS_RATINGS[team_b] + diff
            if team_a not in team_implied:
                team_implied[team_a] = []
            team_implied[team_a].append(implied_a)

        if team_a in SRS_RATINGS and team_b not in [
            "UMBC", "Howard", "Lehigh", "Prairie View A&M", "SMU", "Miami (OH)",
            "NC State", "Texas"
        ]:
            implied_b = SRS_RATINGS[team_a] - diff
            if team_b not in team_implied:
                team_implied[team_b] = []
            team_implied[team_b].append(implied_b)

    # Average implied ratings
    return {team: sum(vals) / len(vals) for team, vals in team_implied.items()}


def build_futures_ratings():
    """Convert futures implied probabilities to a rating-like score."""
    # Log-odds transform: higher prob -> higher score
    ratings = {}
    for team, prob in FUTURES_IMPLIED_PROB.items():
        if prob > 0 and prob < 1:
            ratings[team] = math.log(prob / (1 - prob))
    return ratings


def build_composite_ratings():
    """Build the final composite rating for every tournament team."""
    # Get all tournament teams
    all_teams = set()
    for region, matchups in BRACKET.items():
        for m in matchups:
            all_teams.update(m["teams"])

    # Source 1: SRS z-scores (weight: 0.40)
    srs_tournament = {t: SRS_RATINGS[t] for t in all_teams if t in SRS_RATINGS}
    srs_z = normalize_to_zscores(srs_tournament)

    # Source 2: BPI-implied ratings z-scores (weight: 0.35)
    bpi_implied = build_bpi_implied_ratings()
    bpi_tournament = {t: bpi_implied[t] for t in all_teams if t in bpi_implied}
    bpi_z = normalize_to_zscores(bpi_tournament) if bpi_tournament else {}

    # Source 3: Futures odds z-scores (weight: 0.25 for teams that have them)
    futures_raw = build_futures_ratings()
    futures_tournament = {t: futures_raw[t] for t in all_teams if t in futures_raw}
    futures_z = normalize_to_zscores(futures_tournament) if futures_tournament else {}

    # Expert adjustments (from Appendix A insights):
    # - Michigan lost L.J. Cason for the season; market may be overrating them
    #   Apply a small downward adjustment to Michigan's ratings
    if "Michigan" in srs_z:
        srs_z["Michigan"] -= 0.15
    if "Michigan" in bpi_z:
        bpi_z["Michigan"] -= 0.15
    # - VCU is a popular upset pick; slightly boost VCU
    if "VCU" in srs_z:
        srs_z["VCU"] += 0.10
    # - Texas A&M favored by some models over Saint Mary's; slight boost
    if "Texas A&M" in srs_z:
        srs_z["Texas A&M"] += 0.08

    # Blend
    composite = {}
    for team in all_teams:
        sources = []
        weights = []

        if team in srs_z:
            sources.append(srs_z[team])
            weights.append(0.40)

        if team in bpi_z:
            sources.append(bpi_z[team])
            weights.append(0.35)

        if team in futures_z:
            sources.append(futures_z[team])
            weights.append(0.25)

        if sources:
            total_weight = sum(weights)
            composite[team] = sum(s * w for s, w in zip(sources, weights)) / total_weight
        else:
            # Fallback: estimate from seed
            seed = TEAM_SEEDS.get(team, 16)
            composite[team] = (17 - seed) / 8.0 - 1.0  # rough scale from -1 to +1

    return composite


# ============================================================================
# PHASE 4: PREDICT BRACKET
# ============================================================================

def pick_winner(team_a, team_b, composite, round_num):
    """
    Pick the winner of a matchup using composite ratings + upset heuristics.
    """
    rating_a = composite.get(team_a, 0)
    rating_b = composite.get(team_b, 0)
    gap = rating_a - rating_b  # positive means team_a is stronger

    seed_a = TEAM_SEEDS.get(team_a, 8)
    seed_b = TEAM_SEEDS.get(team_b, 8)

    # Determine higher and lower seed
    if seed_a < seed_b:
        higher_seed_team, lower_seed_team = team_a, team_b
        higher_seed, lower_seed = seed_a, seed_b
        gap_favoring_higher = gap
    elif seed_b < seed_a:
        higher_seed_team, lower_seed_team = team_b, team_a
        higher_seed, lower_seed = seed_b, seed_a
        gap_favoring_higher = -gap
    else:
        # Same seed - just pick higher composite
        return team_a if rating_a >= rating_b else team_b

    # ----------------------------------------------------------------
    # Targeted upset overrides based on BPI data and expert analysis
    # ----------------------------------------------------------------
    # These are specific matchups where the data strongly supports an
    # upset or the game is essentially a toss-up leaning to the lower seed.
    UPSET_OVERRIDES = {
        # VCU (11) over North Carolina (6): popular expert upset pick,
        # BPI spread only 2.9, VCU is battle-tested mid-major
        ("North Carolina", "VCU"): "VCU",
        # Texas A&M (10) over Saint Mary's (7): favored by multiple models,
        # BPI spread only 0.8 (near toss-up), SEC strength-of-schedule edge
        ("Saint Mary's", "Texas A&M"): "Texas A&M",
        # Iowa (9) over Clemson (8): BPI has Clemson by only 0.1 (pure toss-up),
        # Iowa has stronger SRS; picking the "9-seed upset" in a coin-flip game
        ("Clemson", "Iowa"): "Iowa",
        # McNeese (12) over Vanderbilt (5): picking one 12-over-5 upset
        # (historically 35% rate). McNeese is a strong mid-major; gap is
        # moderate but 5v12 upsets happen every year.
        # Actually BPI has Vanderbilt by 9.2, too wide. Skip this one.
        # High Point (12) over Wisconsin (5): BPI flagged as most likely
        # big upset, spread is Wisconsin by 7.3. Still wide, but picking
        # one 12-seed upset for historical accuracy.
        # Keep Vanderbilt and Wisconsin; instead pick:
        # Missouri (10) over Miami FL (7): BPI spread only 1.3, very close
        ("Miami (FL)", "Missouri"): "Missouri",
    }

    matchup_pair = (team_a, team_b)
    matchup_pair_rev = (team_b, team_a)
    if matchup_pair in UPSET_OVERRIDES:
        return UPSET_OVERRIDES[matchup_pair]
    if matchup_pair_rev in UPSET_OVERRIDES:
        return UPSET_OVERRIDES[matchup_pair_rev]

    # Round 1 seed-based heuristics
    if round_num == 1:
        matchup_key = f"{higher_seed}v{lower_seed}"

        # Never pick 16 over 1
        if matchup_key == "1v16":
            return higher_seed_team

        # 2 vs 15: always pick 2 (upset rate ~6%)
        if matchup_key == "2v15":
            return higher_seed_team

        # 3 vs 14: always pick 3 (upset rate ~15%)
        if matchup_key == "3v14":
            return higher_seed_team

        # 4 vs 13: pick 4 unless gap < 0.3σ
        if matchup_key == "4v13":
            if gap_favoring_higher < 0.3:
                return lower_seed_team
            return higher_seed_team

        # 5 vs 12: historically 35% upset rate - pick 12 if gap < 0.5σ
        if matchup_key == "5v12":
            if gap_favoring_higher < 0.5:
                return lower_seed_team
            return higher_seed_team

        # 6v11, 7v10, 8v9: pick higher composite regardless of seed
        if matchup_key in ("6v11", "7v10", "8v9"):
            return team_a if rating_a >= rating_b else team_b

    # Later rounds: pick higher composite
    return team_a if rating_a >= rating_b else team_b


def predict_region(region_name, matchups, composite):
    """Predict all games in a region, return results and champion."""
    results = {"Round of 64": [], "Round of 32": [], "Sweet 16": [], "Elite 8": []}

    # Round of 64
    r64_winners = []
    for m in matchups:
        team_a, team_b = m["teams"]
        winner = pick_winner(team_a, team_b, composite, round_num=1)
        loser = team_b if winner == team_a else team_a
        results["Round of 64"].append({
            "matchup": f"({TEAM_SEEDS[team_a]}) {team_a} vs ({TEAM_SEEDS[team_b]}) {team_b}",
            "winner": winner,
            "winner_seed": TEAM_SEEDS[winner],
            "gap": abs(composite.get(team_a, 0) - composite.get(team_b, 0)),
        })
        r64_winners.append(winner)

    # Round of 32
    r32_winners = []
    for i in range(0, len(r64_winners), 2):
        team_a, team_b = r64_winners[i], r64_winners[i + 1]
        winner = pick_winner(team_a, team_b, composite, round_num=2)
        results["Round of 32"].append({
            "matchup": f"({TEAM_SEEDS[team_a]}) {team_a} vs ({TEAM_SEEDS[team_b]}) {team_b}",
            "winner": winner,
            "winner_seed": TEAM_SEEDS[winner],
        })
        r32_winners.append(winner)

    # Sweet 16
    s16_winners = []
    for i in range(0, len(r32_winners), 2):
        team_a, team_b = r32_winners[i], r32_winners[i + 1]
        winner = pick_winner(team_a, team_b, composite, round_num=3)
        results["Sweet 16"].append({
            "matchup": f"({TEAM_SEEDS[team_a]}) {team_a} vs ({TEAM_SEEDS[team_b]}) {team_b}",
            "winner": winner,
            "winner_seed": TEAM_SEEDS[winner],
        })
        s16_winners.append(winner)

    # Elite 8
    team_a, team_b = s16_winners[0], s16_winners[1]
    winner = pick_winner(team_a, team_b, composite, round_num=4)
    results["Elite 8"].append({
        "matchup": f"({TEAM_SEEDS[team_a]}) {team_a} vs ({TEAM_SEEDS[team_b]}) {team_b}",
        "winner": winner,
        "winner_seed": TEAM_SEEDS[winner],
    })

    return results, winner


def predict_full_bracket():
    """Run the full bracket prediction."""
    composite = build_composite_ratings()

    # Save composite ratings
    sorted_composite = sorted(composite.items(), key=lambda x: -x[1])
    composite_output = [
        {"rank": i + 1, "team": team, "seed": TEAM_SEEDS.get(team, "?"),
         "composite": round(rating, 4)}
        for i, (team, rating) in enumerate(sorted_composite)
    ]

    os.makedirs("data", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    with open("data/composite_ratings.json", "w") as f:
        json.dump(composite_output, f, indent=2)

    # Save bracket
    with open("data/bracket.json", "w") as f:
        json.dump(BRACKET, f, indent=2)

    # Predict each region
    region_results = {}
    region_champions = {}
    for region_name in ["East", "West", "Midwest", "South"]:
        results, champion = predict_region(region_name, BRACKET[region_name], composite)
        region_results[region_name] = results
        region_champions[region_name] = champion

    # Final Four
    # Standard bracket: East vs West, Midwest vs South
    ff_game1_a = region_champions["East"]
    ff_game1_b = region_champions["West"]
    ff_winner1 = pick_winner(ff_game1_a, ff_game1_b, composite, round_num=5)

    ff_game2_a = region_champions["Midwest"]
    ff_game2_b = region_champions["South"]
    ff_winner2 = pick_winner(ff_game2_a, ff_game2_b, composite, round_num=5)

    # Championship
    champion = pick_winner(ff_winner1, ff_winner2, composite, round_num=6)

    # Count upsets in Round of 64
    upset_count = 0
    for region_name, results in region_results.items():
        for game in results["Round of 64"]:
            winner_seed = game["winner_seed"]
            # Parse the matchup to find the higher seed
            parts = game["matchup"].split(" vs ")
            seed1 = int(parts[0].split(")")[0].replace("(", ""))
            seed2 = int(parts[1].split(")")[0].replace("(", ""))
            if winner_seed == max(seed1, seed2):
                upset_count += 1

    # ========================================================================
    # PHASE 5: OUTPUT
    # ========================================================================

    lines = []
    lines.append("=" * 50)
    lines.append("2026 NCAA MEN'S TOURNAMENT PREDICTIONS")
    lines.append("=" * 50)
    lines.append("")
    lines.append("Generated by: Multi-Source Composite Model")
    lines.append("Sources: Sports-Reference SRS, ESPN BPI, DraftKings Futures")
    lines.append(f"First-round upsets predicted: {upset_count}")
    lines.append("")

    # First Four
    lines.append("FIRST FOUR")
    lines.append("-" * 30)
    for game, info in FIRST_FOUR.items():
        lines.append(f"  {game} -> {info['winner']} (BPI: {info['winner']} by {info['bpi_spread']})")
    lines.append("")

    # Each region
    for region_name in ["East", "West", "Midwest", "South"]:
        lines.append(f"{region_name.upper()} REGION")
        lines.append("-" * 30)

        for round_name in ["Round of 64", "Round of 32", "Sweet 16", "Elite 8"]:
            lines.append(f"  {round_name}:")
            for game in region_results[region_name][round_name]:
                lines.append(f"    {game['matchup']} -> {game['winner']}")
        lines.append(f"  {region_name} Champion: ({TEAM_SEEDS[region_champions[region_name]]}) {region_champions[region_name]}")
        lines.append("")

    # Final Four
    lines.append("FINAL FOUR")
    lines.append("-" * 30)
    lines.append(f"  ({TEAM_SEEDS[ff_game1_a]}) {ff_game1_a} vs ({TEAM_SEEDS[ff_game1_b]}) {ff_game1_b} -> {ff_winner1}")
    lines.append(f"  ({TEAM_SEEDS[ff_game2_a]}) {ff_game2_a} vs ({TEAM_SEEDS[ff_game2_b]}) {ff_game2_b} -> {ff_winner2}")
    lines.append("")

    # Championship
    lines.append("NATIONAL CHAMPIONSHIP")
    lines.append("-" * 30)
    lines.append(f"  ({TEAM_SEEDS[ff_winner1]}) {ff_winner1} vs ({TEAM_SEEDS[ff_winner2]}) {ff_winner2} -> {champion}")
    lines.append("")
    lines.append(f"  *** 2026 NATIONAL CHAMPION: ({TEAM_SEEDS[champion]}) {champion} ***")
    lines.append("")

    # Composite ratings summary
    lines.append("=" * 50)
    lines.append("TOP 20 COMPOSITE RATINGS")
    lines.append("=" * 50)
    for entry in composite_output[:20]:
        lines.append(f"  {entry['rank']:>2}. ({entry['seed']:>2}) {entry['team']:<20s}  {entry['composite']:>+.4f}")

    output_text = "\n".join(lines)

    with open("output/bracket_predictions.txt", "w") as f:
        f.write(output_text)

    # Also generate rationale file
    rationale_lines = []
    rationale_lines.append("PREDICTION RATIONALE")
    rationale_lines.append("=" * 50)
    rationale_lines.append("")
    rationale_lines.append("For each game, shows the composite gap between teams.")
    rationale_lines.append("Positive gap = favorite's margin. Upset adjustments noted.")
    rationale_lines.append("")

    for region_name in ["East", "West", "Midwest", "South"]:
        rationale_lines.append(f"\n{region_name.upper()} REGION")
        rationale_lines.append("-" * 40)
        for round_name in ["Round of 64", "Round of 32", "Sweet 16", "Elite 8"]:
            rationale_lines.append(f"\n  {round_name}:")
            for game in region_results[region_name][round_name]:
                gap_str = f"gap={game.get('gap', 0):.3f}" if 'gap' in game else ""
                rationale_lines.append(f"    {game['matchup']} -> {game['winner']}  ({gap_str})")

    rationale_lines.append(f"\nFINAL FOUR")
    rationale_lines.append(f"  {ff_game1_a} vs {ff_game1_b} -> {ff_winner1}")
    rationale_lines.append(f"  {ff_game2_a} vs {ff_game2_b} -> {ff_winner2}")
    rationale_lines.append(f"\nCHAMPIONSHIP: {ff_winner1} vs {ff_winner2} -> {champion}")

    with open("output/prediction_rationale.txt", "w") as f:
        f.write("\n".join(rationale_lines))

    # Verify game count
    total_games = 0
    for region_name, results in region_results.items():
        for round_name, games in results.items():
            total_games += len(games)
    total_games += 2  # Final Four
    total_games += 1  # Championship

    print(output_text)
    print(f"\n{'=' * 50}")
    print(f"VALIDATION: {total_games} main bracket games predicted (expected: 63)")
    print(f"First Four games: {len(FIRST_FOUR)} (expected: 4)")
    print(f"Total: {total_games + len(FIRST_FOUR)} games")
    print(f"\nFiles written:")
    print(f"  output/bracket_predictions.txt")
    print(f"  output/prediction_rationale.txt")
    print(f"  data/composite_ratings.json")
    print(f"  data/bracket.json")

    return champion


if __name__ == "__main__":
    champion = predict_full_bracket()
