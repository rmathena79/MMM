from __future__ import annotations

import logging
import re
from io import StringIO

import pandas as pd

from utils.common import DATA_INTERIM, FIRST_ROUND_SEED_PAIRS, REGION_ORDER
from utils.http import CachedSession

LOGGER = logging.getLogger(__name__)


def _extract_region_tables(html: str) -> list[pd.DataFrame]:
    tables = pd.read_html(StringIO(html))
    region_tables = []
    for table in tables:
        if 'School' in table.columns and 'Seed' in table.columns and len(table) >= 16:
            region_tables.append(table.copy())
    if len(region_tables) < 4:
        raise ValueError('Could not find four region seed tables on the Wikipedia page.')
    return region_tables[:4]


def _clean_seed(value: object) -> int:
    text = str(value).strip()
    match = re.search(r'(\d+)', text)
    if not match:
        raise ValueError(f'Could not parse seed from {value!r}')
    return int(match.group(1))


def _build_play_in_games(region_tables: list[pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for region_name, table in zip(REGION_ORDER, region_tables):
        tmp = table.copy()
        tmp['seed_value'] = tmp['Seed'].map(_clean_seed)
        dupes = tmp[tmp['seed_value'].duplicated(keep=False)].sort_values(['seed_value', 'School'])
        for seed, group in dupes.groupby('seed_value'):
            if len(group) != 2:
                continue
            teams = group['School'].tolist()
            rows.append(
                {
                    'play_in_id': f'PI_{region_name}_{seed}',
                    'region': region_name,
                    'seed': seed,
                    'team1': teams[0],
                    'team2': teams[1],
                }
            )
    if len(rows) != 4:
        raise ValueError(f'Expected 4 First Four games, found {len(rows)}')
    return pd.DataFrame(rows)


def _build_main_slots(region_tables: list[pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for region_name, table in zip(REGION_ORDER, region_tables):
        seed_groups: dict[int, list[str]] = {}
        for _, row in table.iterrows():
            seed = _clean_seed(row['Seed'])
            seed_groups.setdefault(seed, []).append(str(row['School']).strip())
        for slot_index, (seed1, seed2) in enumerate(FIRST_ROUND_SEED_PAIRS, start=1):
            teams1 = seed_groups[seed1]
            teams2 = seed_groups[seed2]
            team1 = teams1[0] if len(teams1) == 1 else f'WINNER::{region_name}::{seed1}'
            team2 = teams2[0] if len(teams2) == 1 else f'WINNER::{region_name}::{seed2}'
            rows.append(
                {
                    'game_id': f'R64_{region_name}_{slot_index}',
                    'round': 'R64',
                    'region': region_name,
                    'slot': slot_index,
                    'seed1': seed1,
                    'team1': team1,
                    'seed2': seed2,
                    'team2': team2,
                }
            )
    return pd.DataFrame(rows)


def fetch_bracket(year: int, metadata: dict, session: CachedSession) -> tuple[pd.DataFrame, pd.DataFrame]:
    url = f"https://en.wikipedia.org/wiki/{year}_NCAA_Division_I_men%27s_basketball_tournament"
    html, _ = session.get_text(url, cache_group=f'bracket_{year}')
    region_tables = _extract_region_tables(html)
    play_in = _build_play_in_games(region_tables)
    main_slots = _build_main_slots(region_tables)
    play_in.to_csv(DATA_INTERIM / f'play_in_structure_{year}.csv', index=False)
    main_slots.to_csv(DATA_INTERIM / f'main_bracket_structure_{year}.csv', index=False)
    metadata.setdefault('datasets', []).extend(
        [
            {'name': f'play_in_structure_{year}', 'rows': int(len(play_in)), 'path': str(DATA_INTERIM / f'play_in_structure_{year}.csv')},
            {'name': f'main_bracket_structure_{year}', 'rows': int(len(main_slots)), 'path': str(DATA_INTERIM / f'main_bracket_structure_{year}.csv')},
        ]
    )
    LOGGER.info('Fetched %s main bracket slots and %s play-in games', len(main_slots), len(play_in))
    return play_in, main_slots
