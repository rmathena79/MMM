from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

WORKSPACE_DIRS = [
    "plan",
    "data/raw",
    "data/intermediate",
    "data/final",
    "src",
    "logs",
    "outputs",
]

RAW_SOURCE_DIR = REPO_ROOT / "data" / "raw"
INTERMEDIATE_DIR = REPO_ROOT / "data" / "intermediate"
FINAL_DATA_DIR = REPO_ROOT / "data" / "final"
LOG_DIR = REPO_ROOT / "logs"
OUTPUT_DIR = REPO_ROOT / "outputs"

RUN_LOG_PATH = LOG_DIR / "run_log.txt"
SOURCE_MANIFEST_PATH = LOG_DIR / "source_manifest.csv"

BRACKET_JSON_PATH = FINAL_DATA_DIR / "bracket_68.json"
FIRST_FOUR_SLOTS_PATH = FINAL_DATA_DIR / "first_four_slots.csv"
MAIN_BRACKET_SLOTS_PATH = FINAL_DATA_DIR / "main_bracket_slots.csv"
TEAM_FEATURES_PATH = FINAL_DATA_DIR / "team_features.csv"
MATCHUP_PROBABILITIES_PATH = FINAL_DATA_DIR / "matchup_probabilities.csv"
BRACKET_PROBABILITIES_PATH = FINAL_DATA_DIR / "bracket_probabilities.csv"
MODEL_SPEC_PATH = FINAL_DATA_DIR / "model_spec.json"
BASELINE_COMPARISON_PATH = FINAL_DATA_DIR / "baseline_comparison.csv"

FIRST_FOUR_OUTPUT_PATH = OUTPUT_DIR / "first_four_predictions.csv"
FINAL_PREDICTIONS_CSV_PATH = OUTPUT_DIR / "final_predictions.csv"
FINAL_PREDICTIONS_MD_PATH = OUTPUT_DIR / "final_predictions.md"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"

SOURCES = [
    {
        "id": "ncaa_bracket_pdf",
        "url": "https://www.ncaa.com/brackets/print/basketball-men/d1/2026",
        "filename": "ncaa_2026_bracket.pdf",
        "description": "Official NCAA 2026 Division I men's bracket PDF",
        "content_type": "binary",
    },
    {
        "id": "barttorvik_trank",
        "url": "https://barttorvik.com/trank.php?year=2026",
        "filename": "barttorvik_trank_2026.html",
        "description": "Bart Torvik 2026 T-Rank page",
        "content_type": "text",
        "mode": "barttorvik",
    },
    {
        "id": "haslametrics_ratings",
        "url": "https://haslametrics.com/ratings.xml",
        "filename": "haslametrics_ratings_2026.xml",
        "description": "Haslametrics 2025-26 ratings XML feed",
        "content_type": "text",
    },
    {
        "id": "warrennolan_net",
        "url": "https://www.warrennolan.com/basketball/2026/net",
        "filename": "warrennolan_net_2026.html",
        "description": "WarrenNolan 2026 NET rankings page",
        "content_type": "text",
    },
    {
        "id": "warrennolan_elo",
        "url": "https://www.warrennolan.com/basketball/2026/elo",
        "filename": "warrennolan_elo_2026.html",
        "description": "WarrenNolan 2026 ELO rankings page",
        "content_type": "text",
    },
    {
        "id": "deepmetric_standings",
        "url": "https://deepmetricanalytics.com/ncaabb/standings?season=2026",
        "filename": "deepmetric_standings_2026.html",
        "description": "DeepMetric Analytics 2026 NCAA basketball standings and ratings",
        "content_type": "text",
    },
    {
        "id": "powerrankingsguru_composite",
        "url": "https://powerrankingsguru.com/mens-college-basketball/team-power-rankings.php",
        "filename": "powerrankingsguru_composite_2026.html",
        "description": "Power Rankings Guru composite men's college basketball rankings",
        "content_type": "text",
    },
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

REGION_ORDER = ["East", "West", "South", "Midwest"]
REGION_DISPLAY_ORDER = ["East", "West", "South", "Midwest"]
R64_SEED_ORDER = [1, 16, 8, 9, 5, 12, 4, 13, 6, 11, 3, 14, 7, 10, 2, 15]
REGION_SEMIFINAL_PAIRINGS = [("East", "South"), ("West", "Midwest")]

FIRST_FOUR_FEEDS = {
    "FF_MW16": {"region": "Midwest", "seed": 16, "placeholder": "16HOWvs16UMBC"},
    "FF_W11": {"region": "West", "seed": 11, "placeholder": "11NC STvs11TEXAS"},
    "FF_S16": {"region": "South", "seed": 16, "placeholder": "16LEHIGHvs16PVAMU"},
    "FF_MW11": {"region": "Midwest", "seed": 11, "placeholder": "11SMUvs11MIA OH"},
}

COMPOSITE_WEIGHTS = {
    "bart_em_z": 0.28,
    "hasla_em_z": 0.22,
    "deepmetric_net_z": 0.18,
    "warrennolan_elo_z": 0.12,
    "prg_score_z": 0.10,
    "recent_form_z": 0.10,
}

LOGISTIC_SLOPE = 1.15
SIMULATION_COUNT = 100_000
