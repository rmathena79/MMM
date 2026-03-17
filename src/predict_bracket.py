from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

from common import log, numeric_game_sort_key, read_json
from config import (
    BASELINE_COMPARISON_PATH,
    BRACKET_JSON_PATH,
    BRACKET_PROBABILITIES_PATH,
    FINAL_PREDICTIONS_CSV_PATH,
    FINAL_PREDICTIONS_MD_PATH,
    FIRST_FOUR_OUTPUT_PATH,
    LOGISTIC_SLOPE,
    MATCHUP_PROBABILITIES_PATH,
    OUTPUT_DIR,
    SIMULATION_COUNT,
    SOURCE_MANIFEST_PATH,
    SUMMARY_PATH,
    TEAM_FEATURES_PATH,
)


ChildNode = Union[str, "GameNode"]

ROUND_TO_ADVANCE_KEY = {
    "Round of 64": "reach_round_of_32_prob",
    "Round of 32": "reach_sweet_16_prob",
    "Sweet 16": "reach_elite_8_prob",
    "Elite Eight": "reach_final_four_prob",
    "Final Four": "reach_title_game_prob",
    "Championship": "win_title_prob",
}


@dataclass
class GameNode:
    game_id: str
    round_name: str
    region: str
    slot_or_game_path: str
    left: ChildNode
    right: ChildNode
    depends_on_games: list[str]


def _team_lookup(features: pd.DataFrame) -> dict[str, dict[str, object]]:
    return features.set_index("team").to_dict(orient="index")


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _pairwise_probability_matrix(features: pd.DataFrame) -> dict[str, dict[str, float]]:
    teams = features["team"].tolist()
    strength = features.set_index("team")["composite_strength"].to_dict()
    matrix: dict[str, dict[str, float]] = {}
    rows: list[dict[str, object]] = []

    for team in teams:
        matrix[team] = {}
        for opponent in teams:
            if team == opponent:
                probability = 0.5
            else:
                diff = strength[team] - strength[opponent]
                probability = _sigmoid(LOGISTIC_SLOPE * diff)
            matrix[team][opponent] = probability

    for index, team_1 in enumerate(teams):
        for team_2 in teams[index + 1 :]:
            rows.append(
                {
                    "team_1": team_1,
                    "team_2": team_2,
                    "team_1_win_prob": matrix[team_1][team_2],
                    "team_2_win_prob": matrix[team_2][team_1],
                }
            )
    pd.DataFrame(rows).to_csv(MATCHUP_PROBABILITIES_PATH, index=False)
    return matrix


def _build_region_nodes(
    region: str,
    participants: list[ChildNode],
    starting_game_number: int,
    round32_start: int,
    sweet16_start: int,
    elite8_game_id: str,
) -> tuple[GameNode, dict[str, GameNode]]:
    nodes: dict[str, GameNode] = {}
    seed_pairs = [(1, 16), (8, 9), (5, 12), (4, 13), (6, 11), (3, 14), (7, 10), (2, 15)]

    round64_nodes: list[GameNode] = []
    for offset, ((seed_1, seed_2), left, right) in enumerate(zip(seed_pairs, participants[::2], participants[1::2]), start=0):
        game_id = f"G{starting_game_number + offset:02d}"
        node = GameNode(
            game_id=game_id,
            round_name="Round of 64",
            region=region,
            slot_or_game_path=f"{region} {seed_1} vs {seed_2}",
            left=left,
            right=right,
            depends_on_games=[],
        )
        nodes[game_id] = node
        round64_nodes.append(node)

    round32_nodes: list[GameNode] = []
    for offset, pair in enumerate([(0, 1), (2, 3), (4, 5), (6, 7)], start=0):
        left = round64_nodes[pair[0]]
        right = round64_nodes[pair[1]]
        game_id = f"G{round32_start + offset:02d}"
        node = GameNode(
            game_id=game_id,
            round_name="Round of 32",
            region=region,
            slot_or_game_path=f"Winner {left.game_id} vs Winner {right.game_id}",
            left=left,
            right=right,
            depends_on_games=[left.game_id, right.game_id],
        )
        nodes[game_id] = node
        round32_nodes.append(node)

    sweet16_nodes: list[GameNode] = []
    for offset, pair in enumerate([(0, 1), (2, 3)], start=0):
        left = round32_nodes[pair[0]]
        right = round32_nodes[pair[1]]
        game_id = f"G{sweet16_start + offset:02d}"
        node = GameNode(
            game_id=game_id,
            round_name="Sweet 16",
            region=region,
            slot_or_game_path=f"Winner {left.game_id} vs Winner {right.game_id}",
            left=left,
            right=right,
            depends_on_games=[left.game_id, right.game_id],
        )
        nodes[game_id] = node
        sweet16_nodes.append(node)

    elite8_node = GameNode(
        game_id=elite8_game_id,
        round_name="Elite Eight",
        region=region,
        slot_or_game_path=f"Winner {sweet16_nodes[0].game_id} vs Winner {sweet16_nodes[1].game_id}",
        left=sweet16_nodes[0],
        right=sweet16_nodes[1],
        depends_on_games=[sweet16_nodes[0].game_id, sweet16_nodes[1].game_id],
    )
    nodes[elite8_node.game_id] = elite8_node
    return elite8_node, nodes


def _build_bracket_tree(
    bracket: dict[str, object],
    *,
    predicted_play_in_winners: dict[str, str] | None,
    include_first_four_subtrees: bool,
) -> tuple[GameNode, dict[str, GameNode]]:
    participants_by_region: dict[str, list[ChildNode]] = {}
    first_four_nodes: dict[str, GameNode] = {}

    for play_in_game_id, game in bracket["first_four"].items():
        first_four_nodes[play_in_game_id] = GameNode(
            game_id=play_in_game_id,
            round_name="First Four",
            region="Dayton",
            slot_or_game_path=str(game["feeds_main_bracket_slot"]),
            left=str(game["team_1"]),
            right=str(game["team_2"]),
            depends_on_games=[],
        )

    for region, slots in bracket["regions"].items():
        participants: list[ChildNode] = []
        for slot in slots:
            if slot["play_in_game_id"]:
                play_in_game_id = str(slot["play_in_game_id"])
                if include_first_four_subtrees:
                    participants.append(first_four_nodes[play_in_game_id])
                else:
                    if predicted_play_in_winners is None:
                        raise ValueError("Predicted play-in winners are required for resolved bracket construction")
                    participants.append(predicted_play_in_winners[play_in_game_id])
            else:
                participants.append(str(slot["team"]))
        participants_by_region[region] = participants

    east_root, east_nodes = _build_region_nodes("East", participants_by_region["East"], 1, 33, 49, "G57")
    west_root, west_nodes = _build_region_nodes("West", participants_by_region["West"], 9, 37, 51, "G58")
    south_root, south_nodes = _build_region_nodes("South", participants_by_region["South"], 17, 41, 53, "G59")
    midwest_root, midwest_nodes = _build_region_nodes("Midwest", participants_by_region["Midwest"], 25, 45, 55, "G60")

    semifinal_left = GameNode(
        game_id="G61",
        round_name="Final Four",
        region="National",
        slot_or_game_path="Winner G57 vs Winner G59",
        left=east_root,
        right=south_root,
        depends_on_games=["G57", "G59"],
    )
    semifinal_right = GameNode(
        game_id="G62",
        round_name="Final Four",
        region="National",
        slot_or_game_path="Winner G58 vs Winner G60",
        left=west_root,
        right=midwest_root,
        depends_on_games=["G58", "G60"],
    )
    championship = GameNode(
        game_id="G63",
        round_name="Championship",
        region="National",
        slot_or_game_path="Winner G61 vs Winner G62",
        left=semifinal_left,
        right=semifinal_right,
        depends_on_games=["G61", "G62"],
    )

    nodes = {}
    nodes.update(first_four_nodes)
    nodes.update(east_nodes)
    nodes.update(west_nodes)
    nodes.update(south_nodes)
    nodes.update(midwest_nodes)
    nodes["G61"] = semifinal_left
    nodes["G62"] = semifinal_right
    nodes["G63"] = championship
    return championship, nodes


def _leaf_analysis(team: str) -> dict[str, object]:
    return {
        "win_prob": {team: 1.0},
        "best_by_winner": {team: {"score": 0.0, "left_winner": None, "right_winner": None}},
        "best_winner": team,
    }


def _analyze_child(
    child: ChildNode,
    pairwise_probability: dict[str, dict[str, float]],
    cache: dict[str, dict[str, object]],
) -> dict[str, object]:
    if isinstance(child, str):
        return _leaf_analysis(child)
    return _analyze_node(child, pairwise_probability, cache)


def _analyze_node(
    node: GameNode,
    pairwise_probability: dict[str, dict[str, float]],
    cache: dict[str, dict[str, object]],
) -> dict[str, object]:
    if node.game_id in cache:
        return cache[node.game_id]

    left_info = _analyze_child(node.left, pairwise_probability, cache)
    right_info = _analyze_child(node.right, pairwise_probability, cache)

    win_prob: dict[str, float] = {}
    for left_team, left_probability in left_info["win_prob"].items():
        matchup_probability = 0.0
        for right_team, right_probability in right_info["win_prob"].items():
            matchup_probability += right_probability * pairwise_probability[left_team][right_team]
        win_prob[left_team] = left_probability * matchup_probability

    for right_team, right_probability in right_info["win_prob"].items():
        matchup_probability = 0.0
        for left_team, left_probability in left_info["win_prob"].items():
            matchup_probability += left_probability * pairwise_probability[right_team][left_team]
        win_prob[right_team] = right_probability * matchup_probability

    best_left_winner = max(left_info["best_by_winner"], key=lambda team: left_info["best_by_winner"][team]["score"])
    best_right_winner = max(
        right_info["best_by_winner"], key=lambda team: right_info["best_by_winner"][team]["score"]
    )
    best_left_score = float(left_info["best_by_winner"][best_left_winner]["score"])
    best_right_score = float(right_info["best_by_winner"][best_right_winner]["score"])

    best_by_winner: dict[str, dict[str, object]] = {}
    for team in left_info["win_prob"]:
        best_by_winner[team] = {
            "score": float(left_info["best_by_winner"][team]["score"]) + best_right_score + win_prob[team],
            "left_winner": team,
            "right_winner": best_right_winner,
        }
    for team in right_info["win_prob"]:
        best_by_winner[team] = {
            "score": best_left_score + float(right_info["best_by_winner"][team]["score"]) + win_prob[team],
            "left_winner": best_left_winner,
            "right_winner": team,
        }

    best_winner = max(best_by_winner, key=lambda team: best_by_winner[team]["score"])
    cache[node.game_id] = {
        "win_prob": win_prob,
        "best_by_winner": best_by_winner,
        "best_winner": best_winner,
    }
    return cache[node.game_id]


def _reconstruct_predictions(
    node: GameNode,
    analysis: dict[str, dict[str, object]],
    *,
    chosen_winner: str | None = None,
) -> list[dict[str, object]]:
    if chosen_winner is None:
        chosen_winner = str(analysis[node.game_id]["best_winner"])
    choice = analysis[node.game_id]["best_by_winner"][chosen_winner]

    predictions: list[dict[str, object]] = []
    if isinstance(node.left, GameNode):
        predictions.extend(_reconstruct_predictions(node.left, analysis, chosen_winner=str(choice["left_winner"])))
    if isinstance(node.right, GameNode):
        predictions.extend(_reconstruct_predictions(node.right, analysis, chosen_winner=str(choice["right_winner"])))

    predictions.append(
        {
            "game_id": node.game_id,
            "round": node.round_name,
            "region": node.region,
            "slot_or_game_path": node.slot_or_game_path,
            "team_1": str(choice["left_winner"]),
            "team_2": str(choice["right_winner"]),
            "predicted_winner": chosen_winner,
            "depends_on_games": ",".join(node.depends_on_games),
            "winner_prob": float(analysis[node.game_id]["win_prob"][chosen_winner]),
        }
    )
    return predictions


def _build_rule_predictions(
    node: GameNode,
    team_info: dict[str, dict[str, object]],
    *,
    rule: str,
) -> tuple[list[dict[str, object]], str]:
    if isinstance(node.left, GameNode):
        left_predictions, left_winner = _build_rule_predictions(node.left, team_info, rule=rule)
    else:
        left_predictions, left_winner = [], node.left

    if isinstance(node.right, GameNode):
        right_predictions, right_winner = _build_rule_predictions(node.right, team_info, rule=rule)
    else:
        right_predictions, right_winner = [], node.right

    if rule == "seed":
        left_seed = int(team_info[left_winner]["seed"])
        right_seed = int(team_info[right_winner]["seed"])
        if left_seed < right_seed:
            winner = left_winner
        elif right_seed < left_seed:
            winner = right_winner
        else:
            winner = (
                left_winner
                if float(team_info[left_winner]["composite_strength"])
                >= float(team_info[right_winner]["composite_strength"])
                else right_winner
            )
    elif rule == "composite":
        winner = (
            left_winner
            if float(team_info[left_winner]["composite_strength"])
            >= float(team_info[right_winner]["composite_strength"])
            else right_winner
        )
    else:
        raise ValueError(f"Unknown rule: {rule}")

    prediction = {
        "game_id": node.game_id,
        "round": node.round_name,
        "region": node.region,
        "slot_or_game_path": node.slot_or_game_path,
        "team_1": left_winner,
        "team_2": right_winner,
        "predicted_winner": winner,
        "depends_on_games": ",".join(node.depends_on_games),
    }
    return left_predictions + right_predictions + [prediction], winner


def _expected_score(predictions: list[dict[str, object]], analysis: dict[str, dict[str, object]]) -> float:
    total = 0.0
    for prediction in predictions:
        total += float(analysis[prediction["game_id"]]["win_prob"][prediction["predicted_winner"]])
    return total


def _simulate_tournament(
    root: GameNode,
    pairwise_probability: dict[str, dict[str, float]],
    teams: list[str],
    *,
    iterations: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(20260316)
    counters = {
        team: {
            "reach_round_of_32_prob": 0,
            "reach_sweet_16_prob": 0,
            "reach_elite_8_prob": 0,
            "reach_final_four_prob": 0,
            "reach_title_game_prob": 0,
            "win_title_prob": 0,
        }
        for team in teams
    }

    def play(child: ChildNode) -> str:
        if isinstance(child, str):
            return child
        left_winner = play(child.left)
        right_winner = play(child.right)
        probability = pairwise_probability[left_winner][right_winner]
        winner = left_winner if rng.random() < probability else right_winner
        if child.round_name in ROUND_TO_ADVANCE_KEY:
            counters[winner][ROUND_TO_ADVANCE_KEY[child.round_name]] += 1
        return winner

    for _ in range(iterations):
        play(root)

    rows = []
    for team in teams:
        row = {"team": team}
        for column, count in counters[team].items():
            row[column] = count / iterations
        rows.append(row)
    return pd.DataFrame(rows)


def _advancement_probabilities(
    teams: list[str],
    nodes: dict[str, GameNode],
    analysis: dict[str, dict[str, object]],
) -> pd.DataFrame:
    rows = {
        team: {
            "team": team,
            "reach_round_of_32_prob": 0.0,
            "reach_sweet_16_prob": 0.0,
            "reach_elite_8_prob": 0.0,
            "reach_final_four_prob": 0.0,
            "reach_title_game_prob": 0.0,
            "win_title_prob": 0.0,
        }
        for team in teams
    }

    for game_id, node in nodes.items():
        if node.round_name not in ROUND_TO_ADVANCE_KEY:
            continue
        column = ROUND_TO_ADVANCE_KEY[node.round_name]
        for team, probability in analysis[game_id]["win_prob"].items():
            rows[team][column] += float(probability)

    return pd.DataFrame(rows.values()).sort_values("team")


def _render_markdown(
    predictions: pd.DataFrame,
    first_four_predictions: pd.DataFrame,
    summary_inputs: dict[str, object],
) -> str:
    champion = predictions.loc[predictions["game_id"] == "G63", "predicted_winner"].iloc[0]
    runner_up_row = predictions.loc[predictions["game_id"] == "G63"].iloc[0]
    runner_up = runner_up_row["team_1"] if runner_up_row["team_2"] == champion else runner_up_row["team_2"]
    final_four = predictions[predictions["game_id"].isin(["G61", "G62"])]["team_1"].tolist() + predictions[
        predictions["game_id"].isin(["G61", "G62"])
    ]["team_2"].tolist()
    elite_eight = predictions[predictions["game_id"].isin(["G57", "G58", "G59", "G60"])]["team_1"].tolist() + predictions[
        predictions["game_id"].isin(["G57", "G58", "G59", "G60"])
    ]["team_2"].tolist()

    lines = [
        "# 2026 Men's NCAA Tournament Predictions",
        "",
        "Methodology: fallback weighted ensemble of public pre-tournament ratings with dynamic-programming bracket selection, frozen on March 16, 2026 before the First Four.",
        "",
        f"Champion: {champion}",
        f"Runner-up: {runner_up}",
        f"Final Four: {', '.join(final_four)}",
        f"Elite Eight: {', '.join(elite_eight)}",
        "",
        "## First Four",
    ]
    for row in first_four_predictions.sort_values("play_in_game_id").itertuples(index=False):
        lines.append(
            f"- {row.play_in_game_id} | {row.team_1} vs {row.team_2} -> {row.predicted_winner} "
            f"(feeds {row.feeds_main_bracket_slot})"
        )

    for round_name in ["Round of 64", "Round of 32", "Sweet 16", "Elite Eight", "Final Four", "Championship"]:
        lines.extend(["", f"## {round_name}"])
        round_frame = predictions[predictions["round"] == round_name].sort_values("game_id", key=lambda s: s.map(numeric_game_sort_key))
        for row in round_frame.itertuples(index=False):
            lines.append(
                f"- {row.game_id} | {row.region} | {row.team_1} vs {row.team_2} -> {row.predicted_winner}"
            )

    lines.extend(
        [
            "",
            "## Notes",
            f"- Expected correct picks under the model: {summary_inputs['dp_expected_score']:.2f}",
            f"- Seed baseline expected score: {summary_inputs['seed_expected_score']:.2f}",
            f"- Composite favorite baseline expected score: {summary_inputs['composite_expected_score']:.2f}",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_summary(
    baseline_frame: pd.DataFrame,
    advancement: pd.DataFrame,
    champion: str,
) -> str:
    champion_probability = advancement.loc[advancement["team"] == champion, "win_title_prob"].iloc[0]
    source_lines = []
    with SOURCE_MANIFEST_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source_lines.append(f"- {row['source_id']}: {row['url']}")

    lines = [
        "# Run Summary",
        "",
        "Chosen model path: fallback weighted ensemble.",
        "",
        "Validation summary:",
    ]
    for row in baseline_frame.itertuples(index=False):
        lines.append(f"- {row.bracket_name}: expected correct picks {row.expected_correct_picks:.2f}")
    lines.extend(
        [
            f"- Selected champion title probability in Monte Carlo/analytic outputs: {champion_probability:.3f}",
            "",
            "Important caveats:",
            "- Historical calibration was not used because collecting archived, same-moment pre-tournament feature sets was too brittle for this local run.",
            "- No manual injury adjustments were applied; the ensemble uses public rating systems and recent form only.",
            "- Final Four pairings were taken from the official printable bracket layout.",
            "",
            "Data sources used:",
            *source_lines,
            "",
            "File inventory:",
            "- logs/source_manifest.csv",
            "- logs/run_log.txt",
            "- data/final/bracket_68.json",
            "- data/final/team_features.csv",
            "- data/final/matchup_probabilities.csv",
            "- data/final/bracket_probabilities.csv",
            "- outputs/first_four_predictions.csv",
            "- outputs/final_predictions.csv",
            "- outputs/final_predictions.md",
            "- outputs/summary.md",
        ]
    )
    return "\n".join(lines) + "\n"


def run_prediction_pipeline() -> dict[str, object]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bracket = read_json(BRACKET_JSON_PATH)
    features = pd.read_csv(TEAM_FEATURES_PATH)
    team_info = _team_lookup(features)
    pairwise_probability = _pairwise_probability_matrix(features)

    first_four_rows = []
    predicted_play_in_winners: dict[str, str] = {}
    for play_in_game_id in ["FF_MW16", "FF_W11", "FF_S16", "FF_MW11"]:
        game = bracket["first_four"][play_in_game_id]
        team_1 = str(game["team_1"])
        team_2 = str(game["team_2"])
        probability = pairwise_probability[team_1][team_2]
        winner = team_1 if probability >= 0.5 else team_2
        predicted_play_in_winners[play_in_game_id] = winner
        first_four_rows.append(
            {
                "play_in_game_id": play_in_game_id,
                "team_1": team_1,
                "team_2": team_2,
                "predicted_winner": winner,
                "feeds_main_bracket_slot": game["feeds_main_bracket_slot"],
                "winner_prob": probability if winner == team_1 else pairwise_probability[team_2][team_1],
            }
        )
    first_four_predictions = pd.DataFrame(first_four_rows).sort_values("play_in_game_id")
    first_four_predictions.to_csv(FIRST_FOUR_OUTPUT_PATH, index=False)

    full_root, full_nodes = _build_bracket_tree(
        bracket,
        predicted_play_in_winners=predicted_play_in_winners,
        include_first_four_subtrees=True,
    )
    full_analysis: dict[str, dict[str, object]] = {}
    _analyze_node(full_root, pairwise_probability, full_analysis)
    advancement = _advancement_probabilities(features["team"].tolist(), full_nodes, full_analysis)
    advancement.to_csv(BRACKET_PROBABILITIES_PATH, index=False)

    simulations = _simulate_tournament(
        full_root,
        pairwise_probability,
        features["team"].tolist(),
        iterations=SIMULATION_COUNT,
    )

    resolved_root, resolved_nodes = _build_bracket_tree(
        bracket,
        predicted_play_in_winners=predicted_play_in_winners,
        include_first_four_subtrees=False,
    )
    resolved_analysis: dict[str, dict[str, object]] = {}
    _analyze_node(resolved_root, pairwise_probability, resolved_analysis)
    dp_predictions = _reconstruct_predictions(resolved_root, resolved_analysis)
    dp_frame = pd.DataFrame(dp_predictions).sort_values("game_id", key=lambda s: s.map(numeric_game_sort_key))
    dp_frame["winner_seed"] = dp_frame["predicted_winner"].map(lambda team: int(team_info[team]["seed"]))
    dp_frame.to_csv(FINAL_PREDICTIONS_CSV_PATH, index=False)

    seed_predictions, _ = _build_rule_predictions(resolved_root, team_info, rule="seed")
    composite_predictions, _ = _build_rule_predictions(resolved_root, team_info, rule="composite")
    baseline_frame = pd.DataFrame(
        [
            {"bracket_name": "dp_optimized", "expected_correct_picks": _expected_score(dp_predictions, resolved_analysis)},
            {"bracket_name": "seed_baseline", "expected_correct_picks": _expected_score(seed_predictions, resolved_analysis)},
            {
                "bracket_name": "composite_baseline",
                "expected_correct_picks": _expected_score(composite_predictions, resolved_analysis),
            },
        ]
    ).sort_values("expected_correct_picks", ascending=False)
    baseline_frame.to_csv(BASELINE_COMPARISON_PATH, index=False)

    markdown = _render_markdown(
        dp_frame,
        first_four_predictions,
        summary_inputs={
            "dp_expected_score": baseline_frame.loc[
                baseline_frame["bracket_name"] == "dp_optimized", "expected_correct_picks"
            ].iloc[0],
            "seed_expected_score": baseline_frame.loc[
                baseline_frame["bracket_name"] == "seed_baseline", "expected_correct_picks"
            ].iloc[0],
            "composite_expected_score": baseline_frame.loc[
                baseline_frame["bracket_name"] == "composite_baseline", "expected_correct_picks"
            ].iloc[0],
        },
    )
    FINAL_PREDICTIONS_MD_PATH.write_text(markdown, encoding="utf-8")

    champion = dp_frame.loc[dp_frame["game_id"] == "G63", "predicted_winner"].iloc[0]
    summary_markdown = _render_summary(baseline_frame, advancement, champion)
    SUMMARY_PATH.write_text(summary_markdown, encoding="utf-8")

    log(f"Predicted First Four winners: {', '.join(first_four_predictions['predicted_winner'])}")
    log(f"Predicted champion: {champion}")
    return {
        "first_four_predictions": first_four_predictions,
        "final_predictions": dp_frame,
        "baseline_comparison": baseline_frame,
        "advancement_probabilities": advancement,
        "simulation_probabilities": simulations,
    }
