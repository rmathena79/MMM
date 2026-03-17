from __future__ import annotations

import argparse
import logging

import pandas as pd

from build_bracket import build_bracket_predictions, build_tree, run_monte_carlo
from fetch_bracket import fetch_bracket
from fetch_historical_data import fetch_historical_data
from fetch_team_ratings import fetch_team_ratings
from predict_matchups import predict_pairwise_probabilities
from train_models import build_training_matrix, train_model
from utils.common import DATA_PROCESSED, DEFAULT_SEED, OUTPUTS_DIR, canonicalize_team_name, configure_logging, ensure_directories, safe_git_commit, utc_now_iso, write_json
from utils.http import CachedSession
from utils.name_matching import match_name
from validate_outputs import validate_outputs

LOGGER = logging.getLogger(__name__)


def _prepare_current_teams(main_slots: pd.DataFrame, play_in_predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    resolved = main_slots.copy()
    for _, row in play_in_predictions.iterrows():
        placeholder = f"WINNER::{row['region']}::{int(row['seed1'])}"
        winner = row['predicted_winner']
        resolved.loc[resolved['team1'] == placeholder, 'team1'] = winner
        resolved.loc[resolved['team2'] == placeholder, 'team2'] = winner
    teams = pd.concat(
        [
            resolved[['region', 'seed1', 'team1']].rename(columns={'seed1': 'seed', 'team1': 'team_name'}),
            resolved[['region', 'seed2', 'team2']].rename(columns={'seed2': 'seed', 'team2': 'team_name'}),
        ],
        ignore_index=True,
    ).drop_duplicates(subset=['team_name'])
    return resolved, teams


def _lookup_current_rating(team: str, ratings: pd.DataFrame) -> pd.Series:
    canonical = canonicalize_team_name(team)
    exact = ratings[ratings['team_name'].map(canonicalize_team_name) == canonical]
    if not exact.empty:
        return exact.iloc[0]
    matched = match_name(team, ratings['team_name'].tolist(), min_score=86)
    if matched is None:
        raise KeyError(f'Could not match {team} to current ratings')
    return ratings.iloc[matched.matched_index]


def _predict_play_in_games(play_in: pd.DataFrame, ratings: pd.DataFrame, model_payload: dict) -> pd.DataFrame:
    model = model_payload['model']
    rows = []
    for _, row in play_in.iterrows():
        team1_row = _lookup_current_rating(row['team1'], ratings)
        team2_row = _lookup_current_rating(row['team2'], ratings)
        features = pd.DataFrame(
            [
                {
                    'seed_diff': 0.0,
                    'srs_diff': float(team1_row['srs'] - team2_row['srs']),
                    'sos_diff': float(team1_row['sos'] - team2_row['sos']),
                    'win_pct_diff': float(team1_row['win_pct'] - team2_row['win_pct']),
                    'points_margin_diff': float((team1_row['points_for'] - team1_row['points_against']) - (team2_row['points_for'] - team2_row['points_against'])),
                }
            ]
        )
        prob = float(model.predict_proba(features)[0, 1])
        winner = row['team1'] if prob >= 0.5 else row['team2']
        rows.append(
            {
                'game_id': row['play_in_id'],
                'round': 'PI',
                'region': row['region'],
                'slot': int(row['seed']),
                'team1': row['team1'],
                'seed1': int(row['seed']),
                'team2': row['team2'],
                'seed2': int(row['seed']),
                'predicted_winner': winner,
                'predicted_winner_seed': int(row['seed']),
                'win_prob': prob if winner == row['team1'] else 1 - prob,
            }
        )
    return pd.DataFrame(rows)


def _write_summary(main_predictions: pd.DataFrame, monte_carlo: dict, metadata: dict, year: int) -> None:
    champion = main_predictions.loc[main_predictions['round'] == 'NCG', 'predicted_winner'].iloc[0]
    final_four = main_predictions.loc[main_predictions['round'] == 'F4', 'predicted_winner'].tolist()
    lines = [
        f'# {year} Main Bracket Prediction Summary',
        '',
        f'- Predicted champion: **{champion}**',
        f"- Predicted Final Four winners feeding title game: {', '.join(final_four)}",
        f"- Monte Carlo most common champion: {monte_carlo['most_common_champion']} ({monte_carlo['frequency']:.2%})",
        f"- Sources used: {len(metadata.get('fetches', []))} fetched pages",
        f"- Git commit: {metadata.get('git_commit', 'unknown')}",
    ]
    (OUTPUTS_DIR / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, default=2026)
    parser.add_argument('--historical-start', type=int, default=2008)
    parser.add_argument('--historical-end', type=int, default=2025)
    parser.add_argument('--simulations', type=int, default=50000)
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    ensure_directories()
    run_paths = configure_logging(args.year)
    metadata = {'year': args.year, 'seed': args.seed, 'git_commit': safe_git_commit(), 'fetches': [], 'datasets': []}
    session = CachedSession(metadata=metadata)

    play_in, main_slots = fetch_bracket(args.year, metadata=metadata, session=session)
    current_ratings = fetch_team_ratings(args.year, metadata=metadata, session=session)
    historical_games, historical_ratings = fetch_historical_data(args.historical_start, args.historical_end, metadata=metadata, session=session)
    training = build_training_matrix(historical_games, historical_ratings, metadata=metadata)
    model_payload = train_model(training, metadata=metadata)

    play_in_predictions = _predict_play_in_games(play_in, current_ratings, model_payload)
    resolved_main, current_teams = _prepare_current_teams(main_slots, play_in_predictions)
    pairwise = predict_pairwise_probabilities(current_teams, current_ratings, model_payload)

    main_predictions = build_bracket_predictions(
        main_bracket=resolved_main,
        pairwise=pairwise,
        model_version=metadata['model']['model_version'],
        generated_at_utc=utc_now_iso(),
    )
    validate_outputs(main_predictions)
    monte_carlo = run_monte_carlo(build_tree(resolved_main), pairwise, simulations=args.simulations, random_seed=args.seed)
    metadata['monte_carlo'] = monte_carlo

    main_csv = OUTPUTS_DIR / f'main_bracket_predictions_{args.year}.csv'
    main_json = OUTPUTS_DIR / f'main_bracket_predictions_{args.year}.json'
    play_in_csv = OUTPUTS_DIR / f'play_in_predictions_{args.year}.csv'
    main_predictions.to_csv(main_csv, index=False)
    main_json.write_text(main_predictions.to_json(orient='records', indent=2), encoding='utf-8')
    play_in_predictions.to_csv(play_in_csv, index=False)
    current_teams.to_csv(DATA_PROCESSED / f'features_{args.year}.csv', index=False)
    _write_summary(main_predictions, monte_carlo, metadata, args.year)
    write_json(run_paths.metadata_path, metadata)
    LOGGER.info('Pipeline complete. Outputs written to %s', OUTPUTS_DIR)


if __name__ == '__main__':
    main()
