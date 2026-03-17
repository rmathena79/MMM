from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path

import pdfplumber

from common import log, now_iso, write_json
from config import (
    BRACKET_JSON_PATH,
    FIRST_FOUR_FEEDS,
    FIRST_FOUR_SLOTS_PATH,
    MAIN_BRACKET_SLOTS_PATH,
    R64_SEED_ORDER,
)


logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)

STANDARD_ENTRY_RE = re.compile(r"^(?P<seed>\d{1,2})(?P<team>.+?)(?:\((?P<record>\d{1,2}-\d{1,2})\))?$")
REVERSED_ENTRY_RE = re.compile(r"^\((?P<record>\d{1,2}-\d{1,2})\)(?P<team>.+?)(?P<seed>\d{1,2})$")


def _group_lines(words: list[dict], *, x_min: float, x_max: float, y_min: float, y_max: float) -> list[str]:
    selected = [
        word
        for word in words
        if x_min <= float(word["x0"]) <= x_max and y_min <= float(word["top"]) <= y_max
    ]
    buckets: dict[int, list[dict]] = {}
    for word in selected:
        buckets.setdefault(round(float(word["top"])), []).append(word)

    lines: list[str] = []
    for top in sorted(buckets):
        parts = sorted(buckets[top], key=lambda item: float(item["x0"]))
        line = " ".join(part["text"] for part in parts)
        line = re.sub(r"\s+", " ", line).strip()
        lines.append(line)
    return lines


def _parse_team_entry(line: str) -> dict[str, object]:
    cleaned = line.replace("Ž", "").strip()
    if "vs" in cleaned and "(" not in cleaned:
        seed_match = re.match(r"^(\d{1,2})", cleaned)
        if not seed_match:
            raise ValueError(f"Could not parse play-in placeholder line: {line}")
        return {
            "seed": int(seed_match.group(1)),
            "team": None,
            "record": None,
            "play_in_placeholder": cleaned,
        }

    standard_match = STANDARD_ENTRY_RE.match(cleaned)
    if standard_match:
        return {
            "seed": int(standard_match.group("seed")),
            "team": standard_match.group("team").strip(),
            "record": standard_match.group("record"),
            "play_in_placeholder": None,
        }

    reversed_match = REVERSED_ENTRY_RE.match(cleaned)
    if reversed_match:
        return {
            "seed": int(reversed_match.group("seed")),
            "team": reversed_match.group("team").strip(),
            "record": reversed_match.group("record"),
            "play_in_placeholder": None,
        }

    raise ValueError(f"Could not parse bracket entry line: {line}")


def parse_bracket(pdf_path: Path) -> dict[str, object]:
    with pdfplumber.open(io.BytesIO(pdf_path.read_bytes())) as pdf:
        words = pdf.pages[0].extract_words(use_text_flow=True)

    first_four_clusters = {
        "FF_MW16": _group_lines(words, x_min=165, x_max=260, y_min=72, y_max=96),
        "FF_W11": _group_lines(words, x_min=280, x_max=360, y_min=72, y_max=96),
        "FF_S16": _group_lines(words, x_min=470, x_max=590, y_min=72, y_max=96),
        "FF_MW11": _group_lines(words, x_min=605, x_max=760, y_min=72, y_max=96),
    }

    first_four: dict[str, dict[str, object]] = {}
    for play_in_game_id, lines in first_four_clusters.items():
        if len(lines) != 2:
            raise ValueError(f"Expected 2 lines for {play_in_game_id}, found {len(lines)}")
        team_1 = _parse_team_entry(lines[0])
        team_2 = _parse_team_entry(lines[1])
        feed = FIRST_FOUR_FEEDS[play_in_game_id]
        first_four[play_in_game_id] = {
            "play_in_game_id": play_in_game_id,
            "team_1": team_1["team"],
            "team_2": team_2["team"],
            "seed": int(team_1["seed"]),
            "record_1": team_1["record"],
            "record_2": team_2["record"],
            "region": feed["region"],
            "feeds_main_bracket_slot": f"{feed['region']} {feed['seed']}",
            "placeholder": feed["placeholder"],
        }

    region_specs = {
        "East": {"x_min": 55, "x_max": 160, "y_min": 108, "y_max": 325},
        "West": {"x_min": 700, "x_max": 785, "y_min": 108, "y_max": 325},
        "South": {"x_min": 55, "x_max": 160, "y_min": 332, "y_max": 550},
        "Midwest": {"x_min": 700, "x_max": 785, "y_min": 332, "y_max": 550},
    }

    regions: dict[str, list[dict[str, object]]] = {}
    main_slots_rows: list[dict[str, object]] = []
    all_team_names: list[str] = []
    placeholder_to_game = {
        feed["placeholder"]: play_in_game_id for play_in_game_id, feed in FIRST_FOUR_FEEDS.items()
    }

    for region, bounds in region_specs.items():
        lines = _group_lines(words, **bounds)
        if len(lines) != 16:
            raise ValueError(f"Expected 16 lines for {region}, found {len(lines)}")

        slots: list[dict[str, object]] = []
        for slot_index, (expected_seed, line) in enumerate(zip(R64_SEED_ORDER, lines), start=1):
            parsed = _parse_team_entry(line)
            if int(parsed["seed"]) != expected_seed:
                raise ValueError(
                    f"Seed mismatch in {region} slot {slot_index}: expected {expected_seed}, got {parsed['seed']}"
                )

            play_in_game_id = None
            team_name = parsed["team"]
            record = parsed["record"]
            if parsed["play_in_placeholder"]:
                play_in_game_id = placeholder_to_game[parsed["play_in_placeholder"]]
                team_name = f"Winner {play_in_game_id}"
                record = None
            else:
                all_team_names.append(str(team_name))

            slot = {
                "slot_index": slot_index,
                "seed": expected_seed,
                "team": team_name,
                "record": record,
                "play_in_game_id": play_in_game_id,
            }
            slots.append(slot)
            main_slots_rows.append(
                {
                    "region": region,
                    "slot_index": slot_index,
                    "seed": expected_seed,
                    "slot_label": f"{region} {expected_seed}",
                    "team": team_name,
                    "record": record or "",
                    "play_in_game_id": play_in_game_id or "",
                    "opening_game_index": ((slot_index - 1) // 2) + 1,
                }
            )
        regions[region] = slots

    for game in first_four.values():
        all_team_names.extend([str(game["team_1"]), str(game["team_2"])])

    if len(all_team_names) != 68:
        raise ValueError(f"Expected 68 teams, found {len(all_team_names)}")

    bracket = {
        "metadata": {
            "parsed_at": now_iso(),
            "source_path": str(pdf_path),
            "team_count": len(all_team_names),
            "first_four_count": len(first_four),
            "main_bracket_game_count": 63,
            "final_four_pairings": [
                {"semifinal_game_id": "G61", "regions": ["East", "South"]},
                {"semifinal_game_id": "G62", "regions": ["West", "Midwest"]},
            ],
        },
        "regions": regions,
        "first_four": first_four,
    }

    write_json(BRACKET_JSON_PATH, bracket)

    with FIRST_FOUR_SLOTS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "play_in_game_id",
                "seed",
                "team_1",
                "record_1",
                "team_2",
                "record_2",
                "region",
                "feeds_main_bracket_slot",
                "placeholder",
            ],
        )
        writer.writeheader()
        for play_in_game_id in ["FF_MW16", "FF_W11", "FF_S16", "FF_MW11"]:
            writer.writerow(first_four[play_in_game_id])

    with MAIN_BRACKET_SLOTS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "region",
                "slot_index",
                "seed",
                "slot_label",
                "team",
                "record",
                "play_in_game_id",
                "opening_game_index",
            ],
        )
        writer.writeheader()
        writer.writerows(main_slots_rows)

    log("Parsed official bracket structure into bracket_68.json, first_four_slots.csv, and main_bracket_slots.csv")
    return bracket
