"""Scoring tool wrappers for optional agent integration."""

from __future__ import annotations

from ..scoring import score_candidate
from ..schemas import Candidate


def tool_score_candidate(candidate: Candidate) -> dict[str, object]:
    return score_candidate(candidate).to_dict()
