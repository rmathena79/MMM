from __future__ import annotations

import shutil
from pathlib import Path

from build_features import build_team_features
from common import ensure_workspace, log, reset_run_log, reset_source_manifest
from config import REPO_ROOT
from fetch_sources import fetch_all_sources
from parse_bracket import parse_bracket
from predict_bracket import run_prediction_pipeline


def _copy_plan() -> None:
    source_path = REPO_ROOT / "2026_march_madness_project_plan.txt"
    destination_path = REPO_ROOT / "plan" / source_path.name
    if source_path.exists():
        shutil.copy2(source_path, destination_path)


def main() -> None:
    ensure_workspace()
    reset_run_log()
    reset_source_manifest()
    _copy_plan()
    log("Execution started")
    log("Information set frozen before the 2026 First Four tipoff using March 16, 2026 sources")
    log("Historical calibration path skipped in favor of the documented fallback ensemble")

    raw_source_paths = fetch_all_sources()
    parse_bracket(raw_source_paths["ncaa_bracket_pdf"])
    build_team_features(raw_source_paths)
    run_prediction_pipeline()
    log("Execution completed successfully")


if __name__ == "__main__":
    main()
