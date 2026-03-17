from __future__ import annotations

import logging
import pickle

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

from utils.common import DATA_PROCESSED, MODELS_DIR, canonicalize_team_name, safe_git_commit, sha256_text
from utils.name_matching import match_name

LOGGER = logging.getLogger(__name__)
FEATURE_COLUMNS = ['seed_diff', 'srs_diff', 'sos_diff', 'win_pct_diff', 'points_margin_diff']


def _prepare_rating_lookup(ratings: pd.DataFrame) -> pd.DataFrame:
    lookup = ratings.copy()
    lookup['team_canonical'] = lookup['team_name'].map(canonicalize_team_name)
    lookup['points_margin'] = lookup['points_for'] - lookup['points_against']
    return lookup


def _lookup_team_row(team: str, ratings: pd.DataFrame) -> pd.Series:
    canonical = canonicalize_team_name(team)
    exact = ratings[ratings['team_canonical'] == canonical]
    if not exact.empty:
        return exact.iloc[0]
    matched = match_name(team, ratings['team_name'].tolist(), min_score=86)
    if matched is None:
        raise KeyError(f'Could not match team {team!r} to ratings table')
    return ratings.iloc[matched.matched_index]


def build_training_matrix(games: pd.DataFrame, ratings: pd.DataFrame, metadata: dict) -> pd.DataFrame:
    ratings_lookup = _prepare_rating_lookup(ratings)
    rows = []
    unresolved = []
    for _, game in games.iterrows():
        year_ratings = ratings_lookup[ratings_lookup['year'] == game['year']]
        try:
            team1 = _lookup_team_row(game['team1'], year_ratings)
            team2 = _lookup_team_row(game['team2'], year_ratings)
        except KeyError as exc:
            unresolved.append(str(exc))
            continue

        base = {
            'year': game['year'],
            'round': game['round'],
            'team1': game['team1'],
            'team2': game['team2'],
            'winner': game['winner'],
            'seed_diff': float(game['seed1'] - game['seed2']),
            'srs_diff': float(team1['srs'] - team2['srs']),
            'sos_diff': float(team1['sos'] - team2['sos']),
            'win_pct_diff': float(team1['win_pct'] - team2['win_pct']),
            'points_margin_diff': float(team1['points_margin'] - team2['points_margin']),
        }
        rows.append({**base, 'label': float(game['winner'] == game['team1'])})
        rows.append(
            {
                'year': game['year'],
                'round': game['round'],
                'team1': game['team2'],
                'team2': game['team1'],
                'winner': game['winner'],
                'seed_diff': -base['seed_diff'],
                'srs_diff': -base['srs_diff'],
                'sos_diff': -base['sos_diff'],
                'win_pct_diff': -base['win_pct_diff'],
                'points_margin_diff': -base['points_margin_diff'],
                'label': float(game['winner'] == game['team2']),
            }
        )
    if unresolved:
        metadata['unresolved_matches'] = unresolved[:25]
    frame = pd.DataFrame(rows)
    path = DATA_PROCESSED / 'training_matrix.csv'
    frame.to_csv(path, index=False)
    metadata.setdefault('datasets', []).append({'name': 'training_matrix', 'rows': int(len(frame)), 'path': str(path)})
    return frame


def train_model(training: pd.DataFrame, metadata: dict) -> dict:
    metrics = []
    for holdout_year in sorted(training['year'].unique()):
        train_df = training[training['year'] != holdout_year]
        test_df = training[training['year'] == holdout_year]
        model = LogisticRegression(max_iter=1000, random_state=0)
        model.fit(train_df[FEATURE_COLUMNS], train_df['label'])
        probs = model.predict_proba(test_df[FEATURE_COLUMNS])[:, 1]
        metrics.append(
            {
                'year': int(holdout_year),
                'log_loss': float(log_loss(test_df['label'], probs, labels=[0, 1])),
                'brier_score': float(brier_score_loss(test_df['label'], probs)),
            }
        )
    final_model = LogisticRegression(max_iter=1000, random_state=0)
    final_model.fit(training[FEATURE_COLUMNS], training['label'])
    payload = {'model': final_model, 'features': FEATURE_COLUMNS, 'cv_metrics': metrics}
    model_path = MODELS_DIR / 'logistic_model.pkl'
    with model_path.open('wb') as handle:
        pickle.dump(payload, handle)
    config_string = repr({'features': FEATURE_COLUMNS, 'git_commit': safe_git_commit(), 'cv_metrics': metrics})
    metadata['model'] = {
        'path': str(model_path),
        'features': FEATURE_COLUMNS,
        'cv_metrics': metrics,
        'model_version': sha256_text(config_string)[:16],
    }
    LOGGER.info('Trained model with mean log loss %.4f', float(np.mean([item['log_loss'] for item in metrics])))
    return payload
