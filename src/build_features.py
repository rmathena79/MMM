from __future__ import annotations

import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import log, read_json, write_json
from config import BRACKET_JSON_PATH, COMPOSITE_WEIGHTS, INTERMEDIATE_DIR, MODEL_SPEC_PATH, TEAM_FEATURES_PATH
from normalize_teams import canonicalize_team_name, clean_bart_team_name


def _flatten_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [
        "__".join([str(part) for part in column if str(part) != "nan"]).strip("_")
        if isinstance(column, tuple)
        else str(column)
        for column in frame.columns
    ]
    return frame


def _extract_first_number(value: object) -> float:
    text = str(value).strip()
    return float(pd.Series([text]).str.extract(r"([-+]?\d*\.?\d+)").iloc[0, 0])


def _zscore(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    std = series.std(ddof=0)
    if std == 0 or pd.isna(std):
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def _official_team_frame() -> pd.DataFrame:
    bracket = read_json(BRACKET_JSON_PATH)
    rows: list[dict[str, object]] = []

    for region, slots in bracket["regions"].items():
        for slot in slots:
            if slot["play_in_game_id"]:
                continue
            rows.append(
                {
                    "team": slot["team"],
                    "seed": slot["seed"],
                    "region": region,
                    "record": slot["record"],
                    "from_first_four": False,
                }
            )

    for game in bracket["first_four"].values():
        rows.extend(
            [
                {
                    "team": game["team_1"],
                    "seed": game["seed"],
                    "region": game["region"],
                    "record": game["record_1"],
                    "from_first_four": True,
                },
                {
                    "team": game["team_2"],
                    "seed": game["seed"],
                    "region": game["region"],
                    "record": game["record_2"],
                    "from_first_four": True,
                },
            ]
        )

    official = pd.DataFrame(rows).drop_duplicates(subset=["team"]).sort_values(["region", "seed", "team"])
    official["wins"] = official["record"].str.split("-").str[0].astype(int)
    official["losses"] = official["record"].str.split("-").str[1].astype(int)
    return official


def _map_source_to_official(frame: pd.DataFrame, *, official_names: list[str], source_label: str) -> pd.DataFrame:
    frame = frame.copy()
    def try_map(name: str) -> str | None:
        try:
            return canonicalize_team_name(name, official_names)
        except KeyError:
            return None

    frame["team"] = frame["team_raw"].apply(try_map)
    frame = frame[frame["team"].notna()].copy()
    frame = frame.drop_duplicates(subset=["team"])
    missing = sorted(set(official_names) - set(frame["team"]))
    if missing:
        preview = ", ".join(missing[:8])
        log(f"{source_label} missing {len(missing)} bracket teams after mapping: {preview}")
    return frame


def _parse_barttorvik(path: Path, official_names: list[str]) -> pd.DataFrame:
    html = path.read_text(encoding="utf-8")
    frame = pd.read_html(StringIO(html))[0]
    frame = _flatten_columns(frame)
    frame = frame[pd.to_numeric(frame["Unnamed: 0_level_0__Rk"], errors="coerce").notna()].copy()
    frame["team_raw"] = frame["Unnamed: 1_level_0__Team"].astype(str).apply(clean_bart_team_name)
    frame["bart_rank"] = pd.to_numeric(frame["Unnamed: 0_level_0__Rk"], errors="coerce")
    frame["bart_adj_oe"] = frame["109__AdjOE"].map(_extract_first_number)
    frame["bart_adj_de"] = frame["109__AdjDE"].map(_extract_first_number)
    frame["bart_barthag"] = frame["0.4893__Barthag"].map(_extract_first_number)
    frame["bart_em"] = frame["bart_adj_oe"] - frame["bart_adj_de"]
    frame = _map_source_to_official(
        frame[["team_raw", "bart_rank", "bart_adj_oe", "bart_adj_de", "bart_barthag", "bart_em"]],
        official_names=official_names,
        source_label="BartTorvik",
    )
    return frame


def _parse_haslametrics(path: Path, official_names: list[str]) -> pd.DataFrame:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    rows = []
    for node in root.findall("mr"):
        if not node.attrib.get("t"):
            continue
        last5 = node.attrib.get("p5wl", "")
        rows.append(
            {
                "team_raw": node.attrib["t"],
                "hasla_rank": float(node.attrib["rk"]),
                "hasla_off": float(node.attrib["oe"]),
                "hasla_def": float(node.attrib["de"]),
                "hasla_em": float(node.attrib["oe"]) - float(node.attrib["de"]),
                "hasla_mom": float(node.attrib["mom"]),
                "hasla_sos": float(node.attrib["sos"]),
                "recent_form_raw": last5.count("W") / len(last5) if last5 else None,
                "conference": node.attrib.get("c"),
            }
        )
    frame = pd.DataFrame(rows)
    frame = _map_source_to_official(frame, official_names=official_names, source_label="Haslametrics")
    return frame


def _parse_warrennolan(path: Path, official_names: list[str], kind: str) -> pd.DataFrame:
    html = path.read_text(encoding="utf-8")
    frame = pd.read_html(StringIO(html))[0]
    if kind == "elo":
        frame = frame.rename(columns={"Team": "team_raw", "Rank": "warrennolan_elo_rank", "ELO": "warrennolan_elo"})
        keep = ["team_raw", "warrennolan_elo_rank", "warrennolan_elo"]
        label = "WarrenNolan ELO"
    else:
        frame = frame.rename(columns={"Team": "team_raw", "NET Rank": "warrennolan_net_rank"})
        frame["warrennolan_net_score"] = -pd.to_numeric(frame["warrennolan_net_rank"], errors="coerce")
        keep = ["team_raw", "warrennolan_net_rank", "warrennolan_net_score"]
        label = "WarrenNolan NET"
    frame = _map_source_to_official(frame[keep], official_names=official_names, source_label=label)
    return frame


def _parse_deepmetric(path: Path, official_names: list[str]) -> pd.DataFrame:
    html = path.read_text(encoding="utf-8")
    frame = pd.read_html(StringIO(html))[0]
    frame = frame.rename(
        columns={
            "Team": "team_raw",
            "DM Rank": "deepmetric_rank",
            "Elo (Rank)": "deepmetric_elo_raw",
            "Net": "deepmetric_net",
            "Off": "deepmetric_off",
            "Def": "deepmetric_def",
        }
    )
    frame["deepmetric_elo"] = frame["deepmetric_elo_raw"].astype(str).str.extract(r"([-+]?\d*\.?\d+)").astype(float)
    frame["deepmetric_em"] = pd.to_numeric(frame["deepmetric_off"], errors="coerce") - pd.to_numeric(
        frame["deepmetric_def"], errors="coerce"
    )
    frame = _map_source_to_official(
        frame[
            [
                "team_raw",
                "deepmetric_rank",
                "deepmetric_elo",
                "deepmetric_net",
                "deepmetric_off",
                "deepmetric_def",
                "deepmetric_em",
            ]
        ],
        official_names=official_names,
        source_label="DeepMetric",
    )
    return frame


def _parse_prg(path: Path, official_names: list[str]) -> pd.DataFrame:
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    frame = pd.read_html(StringIO(html))[0]
    team_names = [tag.get_text(strip=True) for tag in soup.select("span.full-name")]
    frame = frame.iloc[: len(team_names)].copy()
    frame["team_raw"] = team_names[: len(frame)]
    conference_column = next(column for column in frame.columns if "CONF" in str(column) and "TEAM" not in str(column))
    average_rank_column = next(column for column in frame.columns if "AVERAGE" in str(column))
    frame = frame.rename(columns={conference_column: "prg_conference", average_rank_column: "prg_average_rank"})
    frame["prg_average_rank"] = pd.to_numeric(frame["prg_average_rank"], errors="coerce")
    frame["prg_score"] = -frame["prg_average_rank"]
    frame = _map_source_to_official(
        frame[["team_raw", "prg_conference", "prg_average_rank", "prg_score"]],
        official_names=official_names,
        source_label="PowerRankingsGuru",
    )
    return frame


def build_team_features(raw_source_paths: dict[str, Path]) -> pd.DataFrame:
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    official = _official_team_frame()
    official_names = official["team"].tolist()

    bart = _parse_barttorvik(raw_source_paths["barttorvik_trank"], official_names)
    hasla = _parse_haslametrics(raw_source_paths["haslametrics_ratings"], official_names)
    wn_elo = _parse_warrennolan(raw_source_paths["warrennolan_elo"], official_names, kind="elo")
    wn_net = _parse_warrennolan(raw_source_paths["warrennolan_net"], official_names, kind="net")
    deepmetric = _parse_deepmetric(raw_source_paths["deepmetric_standings"], official_names)
    prg = _parse_prg(raw_source_paths["powerrankingsguru_composite"], official_names)

    source_frames = {
        "barttorvik": bart,
        "haslametrics": hasla,
        "warrennolan_elo": wn_elo,
        "warrennolan_net": wn_net,
        "deepmetric": deepmetric,
        "powerrankingsguru": prg,
    }
    for label, frame in source_frames.items():
        frame.sort_values("team").to_csv(INTERMEDIATE_DIR / f"{label}_parsed.csv", index=False)

    merged = official.copy()
    merged = merged.merge(hasla[["team", "conference"]], on="team", how="left")
    merged = merged.merge(bart.drop(columns=["team_raw"]), on="team", how="left")
    merged = merged.merge(hasla.drop(columns=["team_raw", "conference"]), on="team", how="left")
    merged = merged.merge(wn_elo.drop(columns=["team_raw"]), on="team", how="left")
    merged = merged.merge(wn_net.drop(columns=["team_raw"]), on="team", how="left")
    merged = merged.merge(deepmetric.drop(columns=["team_raw"]), on="team", how="left")
    merged = merged.merge(prg.drop(columns=["team_raw", "prg_conference"]), on="team", how="left")

    for raw_column in [
        "bart_em",
        "hasla_em",
        "deepmetric_net",
        "warrennolan_elo",
        "prg_score",
        "recent_form_raw",
    ]:
        merged[raw_column] = pd.to_numeric(merged[raw_column], errors="coerce")
        merged[raw_column] = merged[raw_column].fillna(merged[raw_column].mean())

    merged["bart_em_z"] = _zscore(merged["bart_em"])
    merged["hasla_em_z"] = _zscore(merged["hasla_em"])
    merged["deepmetric_net_z"] = _zscore(merged["deepmetric_net"])
    merged["warrennolan_elo_z"] = _zscore(merged["warrennolan_elo"])
    merged["prg_score_z"] = _zscore(merged["prg_score"])
    merged["recent_form_z"] = _zscore(merged["recent_form_raw"])

    merged["composite_strength"] = 0.0
    for column, weight in COMPOSITE_WEIGHTS.items():
        merged["composite_strength"] += merged[column] * weight

    merged = merged.sort_values(["region", "seed", "team"]).reset_index(drop=True)
    merged.to_csv(TEAM_FEATURES_PATH, index=False)

    model_spec = {
        "model_path": "fallback_weighted_ensemble",
        "weights": COMPOSITE_WEIGHTS,
        "injury_adjustments_applied": False,
        "injury_note": "No tournament-wide, pre-tip injury dataset met the reliability bar during this run, so no manual injury adjustments were applied.",
        "feature_sources": {
            "bart_em_z": "Bart Torvik adjusted efficiency margin",
            "hasla_em_z": "Haslametrics efficiency margin",
            "deepmetric_net_z": "DeepMetric net rating",
            "warrennolan_elo_z": "WarrenNolan Elo",
            "prg_score_z": "PowerRankingsGuru inverse average rank",
            "recent_form_z": "Haslametrics last-five win rate",
        },
    }
    write_json(MODEL_SPEC_PATH, model_spec)
    log("Built merged team feature table and saved fallback model specification")
    return merged
