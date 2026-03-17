from __future__ import annotations

import logging

import pandas as pd
from bs4 import BeautifulSoup

from utils.common import DATA_INTERIM
from utils.http import CachedSession

LOGGER = logging.getLogger(__name__)


def _parse_game_div(game_div, year: int, round_name: str, region: str, slot: int) -> dict:
    team_divs = game_div.find_all('div', recursive=False)[:2]
    if len(team_divs) < 2:
        raise ValueError(f'Malformed game in {year} {region} {round_name}')

    def team_payload(div) -> dict:
        parts = [part.strip() for part in div.stripped_strings if part.strip()]
        seed = int(parts[0])
        team = parts[1]
        score = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        return {'seed': seed, 'team': team, 'score': score}

    left = team_payload(team_divs[0])
    right = team_payload(team_divs[1])
    winner = left['team'] if 'winner' in (team_divs[0].get('class') or []) else right['team']
    return {
        'year': year,
        'round': round_name,
        'region': region,
        'slot': slot,
        'team1': left['team'],
        'seed1': left['seed'],
        'score1': left['score'],
        'team2': right['team'],
        'seed2': right['seed'],
        'score2': right['score'],
        'winner': winner,
    }


def _parse_region_games(soup: BeautifulSoup, year: int) -> list[dict]:
    rows: list[dict] = []
    round_names = ['R64', 'R32', 'S16', 'E8']
    brackets = soup.find('div', id='brackets')
    region_divs = [div for div in brackets.find_all('div', recursive=False) if div.get('id') and div.get('id') != 'national']
    if len(region_divs) != 4:
        raise ValueError(f'Expected 4 regions for {year}, found {len(region_divs)}')
    for region in region_divs:
        region_id = region.get('id')
        bracket = region.find('div', id='bracket')
        rounds = bracket.find_all('div', class_='round', recursive=False)
        for round_name, round_div in zip(round_names, rounds[:4]):
            for slot, game_div in enumerate(round_div.find_all('div', recursive=False), start=1):
                rows.append(_parse_game_div(game_div, year, round_name, region_id.title(), slot))
    return rows


def _parse_national_games(soup: BeautifulSoup, year: int) -> list[dict]:
    rows: list[dict] = []
    national = soup.find('div', id='national')
    if national is None:
        return rows
    bracket = national.find('div', id='bracket')
    rounds = bracket.find_all('div', class_='round', recursive=False)
    if len(rounds) >= 2:
        for slot, game_div in enumerate(rounds[0].find_all('div', recursive=False), start=1):
            rows.append(_parse_game_div(game_div, year, 'F4', '', slot))
        for slot, game_div in enumerate(rounds[1].find_all('div', recursive=False), start=1):
            rows.append(_parse_game_div(game_div, year, 'NCG', '', slot))
    return rows


def fetch_historical_data(start_year: int, end_year: int, metadata: dict, session: CachedSession) -> tuple[pd.DataFrame, pd.DataFrame]:
    games: list[dict] = []
    ratings_frames: list[pd.DataFrame] = []
    from fetch_team_ratings import fetch_team_ratings

    for year in range(start_year, end_year + 1):
        if year == 2020:
            LOGGER.info('Skipping 2020 because the tournament was canceled')
            continue
        url = f'https://www.sports-reference.com/cbb/postseason/men/{year}-ncaa.html'
        html, _ = session.get_text(url, cache_group=f'historical_bracket_{year}')
        soup = BeautifulSoup(html, 'lxml')
        games.extend(_parse_region_games(soup, year))
        games.extend(_parse_national_games(soup, year))
        ratings_frames.append(fetch_team_ratings(year, metadata=metadata, session=session))
        LOGGER.info('Fetched historical tournament data for %s', year)

    games_df = pd.DataFrame(games)
    ratings_df = pd.concat(ratings_frames, ignore_index=True)
    games_path = DATA_INTERIM / f'historical_tournament_games_{start_year}_{end_year}.csv'
    ratings_path = DATA_INTERIM / f'historical_team_ratings_{start_year}_{end_year}.csv'
    games_df.to_csv(games_path, index=False)
    ratings_df.to_csv(ratings_path, index=False)
    metadata.setdefault('datasets', []).extend(
        [
            {'name': 'historical_tournament_games', 'rows': int(len(games_df)), 'path': str(games_path)},
            {'name': 'historical_team_ratings', 'rows': int(len(ratings_df)), 'path': str(ratings_path)},
        ]
    )
    return games_df, ratings_df
