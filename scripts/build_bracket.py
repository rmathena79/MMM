from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from utils.common import REGION_ORDER


@dataclass
class LeafTeam:
    team_name: str
    seed: int
    region: str


@dataclass
class Node:
    round_name: str
    game_id: str
    region: str
    slot: int
    left: 'Node | LeafTeam'
    right: 'Node | LeafTeam'


def _pairwise_lookup(pairwise: pd.DataFrame) -> dict[tuple[str, str], float]:
    return {(row['team1'], row['team2']): float(row['team1_win_prob']) for _, row in pairwise.iterrows()}


def _leaf_result(leaf: LeafTeam) -> dict[str, dict]:
    return {leaf.team_name: {'prob': 1.0, 'seed': leaf.seed, 'team': leaf.team_name, 'picks': []}}


def _solve_node(node: Node, pair_probs: dict[tuple[str, str], float]) -> dict[str, dict]:
    left_states = _solve_node(node.left, pair_probs) if isinstance(node.left, Node) else _leaf_result(node.left)
    right_states = _solve_node(node.right, pair_probs) if isinstance(node.right, Node) else _leaf_result(node.right)
    options = {}
    for left_team, left_payload in left_states.items():
        for right_team, right_payload in right_states.items():
            prob_left = pair_probs[(left_team, right_team)]
            joint_left = left_payload['prob'] * right_payload['prob'] * prob_left
            left_pick = {
                'game_id': node.game_id,
                'round': node.round_name,
                'region': node.region,
                'slot': node.slot,
                'team1': left_team,
                'seed1': left_payload['seed'],
                'team2': right_team,
                'seed2': right_payload['seed'],
                'predicted_winner': left_team,
                'predicted_winner_seed': left_payload['seed'],
                'win_prob': prob_left,
            }
            if joint_left > options.get(left_team, {}).get('prob', -1.0):
                options[left_team] = {
                    'prob': joint_left,
                    'seed': left_payload['seed'],
                    'team': left_team,
                    'picks': left_payload['picks'] + right_payload['picks'] + [left_pick],
                }

            prob_right = pair_probs[(right_team, left_team)]
            joint_right = left_payload['prob'] * right_payload['prob'] * prob_right
            right_pick = {
                'game_id': node.game_id,
                'round': node.round_name,
                'region': node.region,
                'slot': node.slot,
                'team1': left_team,
                'seed1': left_payload['seed'],
                'team2': right_team,
                'seed2': right_payload['seed'],
                'predicted_winner': right_team,
                'predicted_winner_seed': right_payload['seed'],
                'win_prob': prob_right,
            }
            if joint_right > options.get(right_team, {}).get('prob', -1.0):
                options[right_team] = {
                    'prob': joint_right,
                    'seed': right_payload['seed'],
                    'team': right_team,
                    'picks': left_payload['picks'] + right_payload['picks'] + [right_pick],
                }
    return options


def _region_tree(region: str, teams: list[LeafTeam]) -> Node:
    r64 = [Node('R64', f'R64_{region}_{idx}', region, idx, teams[idx * 2 - 2], teams[idx * 2 - 1]) for idx in range(1, 9)]
    r32 = [Node('R32', f'R32_{region}_{idx}', region, idx, r64[idx * 2 - 2], r64[idx * 2 - 1]) for idx in range(1, 5)]
    s16 = [Node('S16', f'S16_{region}_{idx}', region, idx, r32[idx * 2 - 2], r32[idx * 2 - 1]) for idx in range(1, 3)]
    return Node('E8', f'E8_{region}_1', region, 1, s16[0], s16[1])


def build_tree(main_bracket: pd.DataFrame) -> Node:
    region_winners = []
    for region in REGION_ORDER:
        subset = main_bracket[main_bracket['region'] == region].sort_values('slot')
        teams = []
        for _, row in subset.iterrows():
            teams.append(LeafTeam(team_name=row['team1'], seed=int(row['seed1']), region=region))
            teams.append(LeafTeam(team_name=row['team2'], seed=int(row['seed2']), region=region))
        region_winners.append(_region_tree(region, teams))
    semi_1 = Node('F4', 'F4_1', '', 1, region_winners[0], region_winners[1])
    semi_2 = Node('F4', 'F4_2', '', 2, region_winners[2], region_winners[3])
    return Node('NCG', 'NCG', '', 1, semi_1, semi_2)


def _sample_game(team1: dict, team2: dict, pair_probs: dict[tuple[str, str], float], rng: np.random.Generator) -> dict:
    prob = pair_probs[(team1['team'], team2['team'])]
    if rng.random() <= prob:
        return {'team': team1['team'], 'seed': team1['seed']}
    return {'team': team2['team'], 'seed': team2['seed']}


def _simulate_node(node: Node, pair_probs: dict[tuple[str, str], float], rng: np.random.Generator) -> dict:
    left = _simulate_node(node.left, pair_probs, rng) if isinstance(node.left, Node) else {'team': node.left.team_name, 'seed': node.left.seed}
    right = _simulate_node(node.right, pair_probs, rng) if isinstance(node.right, Node) else {'team': node.right.team_name, 'seed': node.right.seed}
    return _sample_game(left, right, pair_probs, rng)


def run_monte_carlo(root: Node, pairwise: pd.DataFrame, simulations: int, random_seed: int) -> dict:
    lookup = _pairwise_lookup(pairwise)
    rng = np.random.default_rng(random_seed)
    champions = {}
    for _ in range(simulations):
        champion = _simulate_node(root, lookup, rng)['team']
        champions[champion] = champions.get(champion, 0) + 1
    leader = max(champions.items(), key=lambda item: item[1])
    return {'most_common_champion': leader[0], 'frequency': leader[1] / simulations}


def build_bracket_predictions(main_bracket: pd.DataFrame, pairwise: pd.DataFrame, model_version: str, generated_at_utc: str) -> pd.DataFrame:
    root = build_tree(main_bracket)
    options = _solve_node(root, _pairwise_lookup(pairwise))
    champion = max(options.values(), key=lambda item: item['prob'])
    output = pd.DataFrame(champion['picks']).drop_duplicates(subset=['game_id']).copy()
    output['model_version'] = model_version
    output['generated_at_utc'] = generated_at_utc
    round_order = {'R64': 0, 'R32': 1, 'S16': 2, 'E8': 3, 'F4': 4, 'NCG': 5}
    output['round_order'] = output['round'].map(round_order)
    output = output.sort_values(['round_order', 'region', 'slot', 'game_id']).drop(columns=['round_order']).reset_index(drop=True)
    return output
