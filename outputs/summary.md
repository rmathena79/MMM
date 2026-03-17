# Run Summary

Chosen model path: fallback weighted ensemble.

Validation summary:
- dp_optimized: expected correct picks 41.07
- composite_baseline: expected correct picks 41.07
- seed_baseline: expected correct picks 40.69
- Selected champion title probability in Monte Carlo/analytic outputs: 0.214

Important caveats:
- Historical calibration was not used because collecting archived, same-moment pre-tournament feature sets was too brittle for this local run.
- No manual injury adjustments were applied; the ensemble uses public rating systems and recent form only.
- Final Four pairings were taken from the official printable bracket layout.

Data sources used:
- ncaa_bracket_pdf: https://www.ncaa.com/brackets/print/basketball-men/d1/2026
- barttorvik_trank: https://barttorvik.com/trank.php?year=2026
- haslametrics_ratings: https://haslametrics.com/ratings.xml
- warrennolan_net: https://www.warrennolan.com/basketball/2026/net
- warrennolan_elo: https://www.warrennolan.com/basketball/2026/elo
- deepmetric_standings: https://deepmetricanalytics.com/ncaabb/standings?season=2026
- powerrankingsguru_composite: https://powerrankingsguru.com/mens-college-basketball/team-power-rankings.php

File inventory:
- logs/source_manifest.csv
- logs/run_log.txt
- data/final/bracket_68.json
- data/final/team_features.csv
- data/final/matchup_probabilities.csv
- data/final/bracket_probabilities.csv
- outputs/first_four_predictions.csv
- outputs/final_predictions.csv
- outputs/final_predictions.md
- outputs/summary.md
