from __future__ import annotations

import logging
from io import StringIO

import pandas as pd

from utils.common import DATA_INTERIM, flatten_columns
from utils.http import CachedSession

LOGGER = logging.getLogger(__name__)


def fetch_team_ratings(year: int, metadata: dict, session: CachedSession) -> pd.DataFrame:
    url = f'https://www.sports-reference.com/cbb/seasons/men/{year}-school-stats.html'
    html, _ = session.get_text(url, cache_group=f'ratings_{year}')
    tables = pd.read_html(StringIO(html))
    ratings = flatten_columns(tables[0])
    ratings = ratings.rename(columns={'School': 'team_name'})
    ratings['team_name'] = ratings['team_name'].astype(str).str.replace('\xa0NCAA', '', regex=False)
    keep = ['team_name', 'Overall_W', 'Overall_L', 'Overall_W-L%', 'Overall_SRS', 'Overall_SOS', 'Points_Tm.', 'Points_Opp.']
    ratings = ratings[keep].rename(
        columns={
            'Overall_W': 'wins',
            'Overall_L': 'losses',
            'Overall_W-L%': 'win_pct',
            'Overall_SRS': 'srs',
            'Overall_SOS': 'sos',
            'Points_Tm.': 'points_for',
            'Points_Opp.': 'points_against',
        }
    )
    for column in ['wins', 'losses', 'win_pct', 'srs', 'sos', 'points_for', 'points_against']:
        ratings[column] = pd.to_numeric(ratings[column], errors='coerce')
    ratings['year'] = year
    path = DATA_INTERIM / f'team_ratings_{year}.csv'
    ratings.to_csv(path, index=False)
    metadata.setdefault('datasets', []).append({'name': f'team_ratings_{year}', 'rows': int(len(ratings)), 'path': str(path)})
    LOGGER.info('Fetched %s team ratings rows for %s', len(ratings), year)
    return ratings
