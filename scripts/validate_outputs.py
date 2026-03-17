from __future__ import annotations

import pandas as pd


ROUND_FLOW = {
    'R64': 'R32',
    'R32': 'S16',
    'S16': 'E8',
    'E8': 'F4',
    'F4': 'NCG',
}


def validate_outputs(main_bracket_predictions: pd.DataFrame) -> None:
    if len(main_bracket_predictions) != 63:
        raise ValueError(f'Expected 63 predicted main bracket games, found {len(main_bracket_predictions)}')
    if not main_bracket_predictions['win_prob'].between(0, 1).all():
        raise ValueError('Found probabilities outside [0, 1]')
    r64 = main_bracket_predictions[main_bracket_predictions['round'] == 'R64']
    teams = pd.concat([r64['team1'], r64['team2']], ignore_index=True)
    if teams.nunique() != 64:
        raise ValueError('Round of 64 does not contain 64 distinct teams')
    required_rounds = {'R64': 32, 'R32': 16, 'S16': 8, 'E8': 4, 'F4': 2, 'NCG': 1}
    counts = main_bracket_predictions['round'].value_counts().to_dict()
    for round_name, expected in required_rounds.items():
        if counts.get(round_name, 0) != expected:
            raise ValueError(f'Expected {expected} games in {round_name}, found {counts.get(round_name, 0)}')

    for current_round, next_round in ROUND_FLOW.items():
        winners = main_bracket_predictions.loc[main_bracket_predictions['round'] == current_round, 'predicted_winner']
        next_games = main_bracket_predictions[main_bracket_predictions['round'] == next_round]
        next_teams = pd.concat([next_games['team1'], next_games['team2']], ignore_index=True)
        missing = sorted(set(winners) - set(next_teams))
        if missing:
            raise ValueError(f'Winners from {current_round} do not all advance into {next_round}: {missing[:5]}')
