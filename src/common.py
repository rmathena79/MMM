from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from config import LOG_DIR, RUN_LOG_PATH, SOURCE_MANIFEST_PATH, WORKSPACE_DIRS, REPO_ROOT


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_workspace() -> None:
    for relative_dir in WORKSPACE_DIRS:
        (REPO_ROOT / relative_dir).mkdir(parents=True, exist_ok=True)


def reset_run_log() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUN_LOG_PATH.write_text("", encoding="utf-8")


def log(message: str) -> None:
    line = f"[{now_iso()}] {message}"
    print(line)
    with RUN_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def reset_source_manifest() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with SOURCE_MANIFEST_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source_id", "url", "accessed_at", "file_path", "description"])


def add_source_manifest(source_id: str, url: str, file_path: Path, description: str) -> None:
    with SOURCE_MANIFEST_PATH.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([source_id, url, now_iso(), str(file_path), description])


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def numeric_game_sort_key(game_id: str) -> int:
    return int(game_id[1:])
