from __future__ import annotations

import re
from typing import Iterable


MANUAL_ALIASES = {
    "connecticut": "UConn",
    "uconn": "UConn",
    "saint johns": "St. John's",
    "st johns": "St. John's",
    "saint marys": "Saint Mary's",
    "saint marys college": "Saint Mary's",
    "st marys": "Saint Mary's",
    "saint louis": "Saint Louis",
    "iowa state": "Iowa St.",
    "long island university": "Long Island",
    "liu brooklyn": "Long Island",
    "liu": "Long Island",
    "mcneese state": "McNeese",
    "mcneese st": "McNeese",
    "michigan state": "Michigan St.",
    "michigan st": "Michigan St.",
    "ohio state": "Ohio St.",
    "north dakota state": "North Dakota St.",
    "wright state": "Wright St.",
    "tennessee state": "Tennessee St.",
    "north carolina state": "NC State",
    "nc state": "NC State",
    "n c state": "NC State",
    "miami": "Miami (FL)",
    "miami ohio": "Miami (Ohio)",
    "miami oh": "Miami (Ohio)",
    "miami fl": "Miami (FL)",
    "miami florida": "Miami (FL)",
    "kennesaw state": "Kennesaw St.",
    "pennsylvania": "Penn",
    "prairie view am": "Prairie View A&M",
    "prairie view a and m": "Prairie View A&M",
    "prairie view": "Prairie View A&M",
    "texas am": "Texas A&M",
    "queens": "Queens (N.C.)",
    "queens nc": "Queens (N.C.)",
    "queens n c": "Queens (N.C.)",
    "queens university": "Queens (N.C.)",
    "california baptist": "Cal Baptist",
    "south florida": "South Florida",
    "usf": "South Florida",
    "utah state": "Utah St.",
}


def normalize_name(name: str) -> str:
    cleaned = name.strip().lower()
    cleaned = cleaned.replace("&amp;", " and ")
    cleaned = cleaned.replace("&", " and ")
    cleaned = cleaned.replace("’", "'")
    cleaned = cleaned.replace("'", "")
    cleaned = cleaned.replace(".", " ")
    cleaned = cleaned.replace("(", " ")
    cleaned = cleaned.replace(")", " ")
    cleaned = cleaned.replace("/", " ")
    cleaned = cleaned.replace("-", " ")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def build_official_index(official_names: Iterable[str]) -> dict[str, str]:
    index = {}
    for name in official_names:
        index[normalize_name(name)] = name
    return index


def clean_bart_team_name(raw_name: str) -> str:
    cleaned = raw_name.encode("ascii", "ignore").decode()
    cleaned = re.sub(r"\s+\d+\s*seed,.*$", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def canonicalize_team_name(raw_name: str, official_names: Iterable[str]) -> str:
    official_index = build_official_index(official_names)
    normalized = normalize_name(raw_name)
    if normalized in official_index:
        return official_index[normalized]
    if normalized in MANUAL_ALIASES:
        return MANUAL_ALIASES[normalized]
    raise KeyError(f"Unmatched team name: {raw_name}")
