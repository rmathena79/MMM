from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from .common import canonicalize_team_name


@dataclass
class MatchResult:
    source_name: str
    matched_name: str
    score: float
    matched_index: int


def match_name(name: str, candidates: list[str], min_score: float = 88.0) -> MatchResult | None:
    query = canonicalize_team_name(name)
    canonical_candidates = [canonicalize_team_name(candidate) for candidate in candidates]
    matched = process.extractOne(query, canonical_candidates, scorer=fuzz.WRatio)
    if not matched or matched[1] < min_score:
        return None
    idx = canonical_candidates.index(matched[0])
    return MatchResult(source_name=name, matched_name=candidates[idx], score=float(matched[1]), matched_index=idx)
