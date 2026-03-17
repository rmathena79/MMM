from __future__ import annotations

import itertools

import pandas as pd

from train_models import FEATURE_COLUMNS
from utils.common import DATA_PROCESSED, canonicalize_team_name
from utils.name_matching import match_name


def _prepare_lookup(ratings: pd.DataFrame) -> pd.DataFrame:
    lookup = ratings.copy()
    lookup['team_canonical'] = lookup['team_name'].map(canonicalize_team_name)
    return lookup


def _row_for_team(team: str, ratings_lookup: pd.DataFrame) -> pd.Series:
    canonical = canonicalize_team_name(team)
    exact = ratings_lookup[ratings_lookup['team_canonical'] == canonical]
    if not exact.empty:
        return exact.iloc[0]
    matched = match_name(team, ratings_lookup['team_name'].tolist(), min_score=86)
    if matched is None:
        raise KeyError(f'Unable to find ratings row for {team}')
    return ratings_lookup.iloc[matched.matched_index]


def matchup_features(team1: str, seed1: int, team2: str, seed2: int, ratings_lookup: pd.DataFrame) -> dict:
    row1 = _row_for_team(team1, ratings_lookup)
    row2 = _row_for_team(team2, ratings_lookup)
    return {
        'seed_diff': float(seed1 - seed2),
        'srs_diff': float(row1['srs'] - row2['srs']),
        'sos_diff': float(row1['sos'] - row2['sos']),
        'win_pct_diff': float(row1['win_pct'] - row2['win_pct']),
        'points_margin_diff': float((row1['points_for'] - row1['points_against']) - (row2['points_for'] - row2['points_against'])),
    }


def predict_pairwise_probabilities(teams: pd.DataFrame, ratings: pd.DataFrame, model_payload: dict) -> pd.DataFrame:
    lookup = _prepare_lookup(ratings)
    model = model_payload['model']
    rows = []
    for left_idx, right_idx in itertools.permutations(teams.index.tolist(), 2):
        left = teams.loc[left_idx]
        right = teams.loc[right_idx]
        features = matchup_features(left['team_name'], int(left['seed']), right['team_name'], int(right['seed']), lookup)
        prob = float(model.predict_proba(pd.DataFrame([features], columns=FEATURE_COLUMNS))[0, 1])
        rows.append(
            {
                'team1': left['team_name'],
                'seed1': int(left['seed']),
                'team2': right['team_name'],
                'seed2': int(right['seed']),
                'team1_win_prob': prob,
            }
        )
    pairwise = pd.DataFrame(rows)
    pairwise.to_csv(DATA_PROCESSED / 'pairwise_probabilities_2026.csv', index=False)
    return pairwise
