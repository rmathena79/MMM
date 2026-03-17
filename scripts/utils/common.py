from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / 'data' / 'raw'
DATA_INTERIM = ROOT / 'data' / 'interim'
DATA_PROCESSED = ROOT / 'data' / 'processed'
MODELS_DIR = ROOT / 'models'
OUTPUTS_DIR = ROOT / 'outputs'
LOGS_DIR = ROOT / 'logs'

REGION_ORDER = ['East', 'West', 'South', 'Midwest']
FIRST_ROUND_SEED_PAIRS = [(1, 16), (8, 9), (5, 12), (4, 13), (6, 11), (3, 14), (7, 10), (2, 15)]
STANDARD_USER_AGENT = 'MMM Pipeline/1.0 (+https://github.com/openai/codex)'
DEFAULT_SEED = 20260316


def ensure_directories() -> None:
    for path in [DATA_RAW, DATA_INTERIM, DATA_PROCESSED, MODELS_DIR, OUTPUTS_DIR, LOGS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def timestamp_slug() -> str:
    return utc_now().strftime('%Y%m%dT%H%M%SZ')


def canonicalize_team_name(name: str) -> str:
    text = name.replace('\xa0', ' ').strip().lower()
    text = re.sub(r'\s*ncaa\s*$', '', text)
    text = text.replace('&', 'and').replace("'", '').replace('.', '').replace('-', ' ')
    text = text.replace('(', ' ').replace(')', ' ').replace(',', ' ')
    replacements = {
        'st ': 'saint ',
        'st.': 'saint',
        "saint mary's": 'saint marys',
        'uconn': 'connecticut',
        'ole miss': 'mississippi',
        'south florida': 'usf',
        'ucf': 'central florida',
        'tcu': 'texas christian',
        'vcu': 'virginia commonwealth',
        'liu': 'long island university',
        'byu': 'brigham young',
        'smu': 'southern methodist',
        'umbc': 'maryland baltimore county',
        'unc wilmington': 'north carolina wilmington',
        'texas a&m': 'texas am',
        'prairie view a&m': 'prairie view',
        'unlv': 'nevada las vegas',
        'usc': 'southern california',
        'etsu': 'east tennessee state',
        'lsu': 'louisiana state',
        'umass': 'massachusetts',
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r'\s+', ' ', text).strip()


def slugify(text: str) -> str:
    text = canonicalize_team_name(text)
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


def flatten_columns(df) -> Any:
    df = df.copy()
    columns = []
    for col in df.columns:
        if isinstance(col, tuple):
            pieces = [str(piece).strip() for piece in col if str(piece).strip() and 'Unnamed' not in str(piece)]
            columns.append('_'.join(pieces) if pieces else 'value')
        else:
            columns.append(str(col).strip())
    df.columns = columns
    return df


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')


def safe_git_commit() -> str | None:
    import subprocess

    try:
        result = subprocess.run(
            ['git', '-c', f'safe.directory={ROOT}', 'rev-parse', 'HEAD'],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


@dataclass
class RunPaths:
    log_path: Path
    metadata_path: Path


def configure_logging(year: int) -> RunPaths:
    ensure_directories()
    stamp = timestamp_slug()
    log_path = LOGS_DIR / f'run_{year}_{stamp}.log'
    metadata_path = LOGS_DIR / 'run_metadata.json'
    handlers = [logging.FileHandler(log_path, encoding='utf-8'), logging.StreamHandler()]
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
        handlers=handlers,
        force=True,
    )
    return RunPaths(log_path=log_path, metadata_path=metadata_path)
