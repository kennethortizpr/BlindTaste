# backend/recommender.py
"""
Core recommendation algorithm for BlindTaste.

Two public functions:
  recommend_label  -- Label Input mode (user has a specific wine, wants similar alternatives)
  recommend_flavor -- Flavor Profile mode (user describes desired taste, no specific wine)

Algorithm:
  - Pre-filter candidates by wine_type (Label: required; Flavor: optional).
  - Build a feature vector from the provided inputs only (variable dimensions).
  - Apply Min-Max normalization using fixed domain-scale bounds.
  - Compute Euclidean distance between input and each candidate centroid.
  - Convert distance to similarity %: max(0, (1 - d / max_d) * 100),
    where max_d = actual maximum distance across all candidates in the pool
    (data-relative scale — the worst match scores 0%, best scores 100%).
  - Return top_n results sorted by ascending distance.
"""

import math
from sqlalchemy.orm import Session
from models import GrapeStandard


# Fixed Min-Max bounds per feature, derived from the scale definitions in context.md.
# Using theoretical bounds keeps normalization stable across queries.
FEATURE_BOUNDS: dict[str, tuple[float, float]] = {
    "avg_alcohol": (8.0, 16.0),
    "avg_acidity": (1.0, 3.0),
    "avg_body":    (1.0, 5.0),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(features: dict[str, float]) -> dict[str, float]:
    """Min-Max normalize a feature dict using FEATURE_BOUNDS."""
    result = {}
    for k, v in features.items():
        lo, hi = FEATURE_BOUNDS[k]
        result[k] = (v - lo) / (hi - lo)
    return result


def _euclidean(a: dict[str, float], b: dict[str, float]) -> float:
    """Euclidean distance over the keys present in a (same keys expected in b)."""
    return math.sqrt(sum((a[k] - b[k]) ** 2 for k in a))


def _row_features(row: GrapeStandard, keys: list[str]) -> dict[str, float]:
    return {k: getattr(row, k) for k in keys}


def _format_result(rank: int, row: GrapeStandard, similarity: float | None) -> dict:
    return {
        "rank": rank,
        "id_pk": row.id_pk,
        "grape_name": row.grape_name,
        "wine_type": row.wine_type,
        "avg_alcohol": row.avg_alcohol,
        "avg_acidity": row.avg_acidity,
        "avg_body": row.avg_body,
        "food_pairings": row.food_pairings,
        "description": row.description,
        "similarity_percentage": similarity,
    }


def _score_and_rank(
    candidates: list[GrapeStandard],
    input_features: dict[str, float],
    top_n: int,
) -> list[dict]:
    """Score candidates against input_features and return top_n ranked results."""
    if not candidates:
        return []

    active_keys = list(input_features.keys())
    input_norm = _normalize(input_features)

    # Compute all distances first so we can scale relative to the actual
    # farthest candidate rather than the theoretical worst-case sqrt(n).
    # This spreads scores across the real data range instead of clustering
    # everything near 100% (the theoretical max is never reached in practice).
    raw: list[tuple[float, GrapeStandard]] = []
    for c in candidates:
        cand_norm = _normalize(_row_features(c, active_keys))
        raw.append((_euclidean(input_norm, cand_norm), c))

    max_dist = max(d for d, _ in raw) if raw else 1.0
    if max_dist < 1e-9:
        max_dist = 1.0

    scored: list[tuple[float, float, GrapeStandard]] = []
    for dist, c in raw:
        similarity = max(0.0, (1.0 - dist / max_dist) * 100.0)
        scored.append((dist, similarity, c))

    scored.sort(key=lambda x: x[0])
    return [
        _format_result(i + 1, row, round(sim, 1))
        for i, (_, sim, row) in enumerate(scored[:top_n])
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recommend_label(
    session: Session,
    wine_type: str,
    alcohol: float,
    main_grape: str,
    acidity: float | None = None,
    body: float | None = None,
    top_n: int = 5,
) -> list[dict]:
    """
    Label Input mode.

    Finds top_n grape varieties whose centroid is closest to the given wine
    profile. The exact (main_grape, wine_type) combination is excluded so the
    user always gets *different* suggestions.
    """
    candidates = (
        session.query(GrapeStandard)
        .filter(GrapeStandard.wine_type == wine_type)
        .all()
    )
    # Exclude only the exact (grape_name, wine_type) pair — a Chardonnay Sparkling
    # can still appear when the input is a Chardonnay White.
    candidates = [
        c for c in candidates
        if c.grape_name.lower() != main_grape.lower()
    ]

    input_features: dict[str, float] = {"avg_alcohol": alcohol}
    if acidity is not None:
        input_features["avg_acidity"] = acidity
    if body is not None:
        input_features["avg_body"] = body

    return _score_and_rank(candidates, input_features, top_n)


def recommend_flavor(
    session: Session,
    wine_type: str | None = None,
    alcohol: float | None = None,
    acidity: float | None = None,
    body: float | None = None,
    food_pairing: str | None = None,
    top_n: int = 5,
) -> list[dict]:
    """
    Flavor Profile mode.

    All parameters are optional; at least one must be provided (enforced by the
    caller). Categorical filters (wine_type, food_pairing) narrow the candidate
    pool before distance scoring. Numeric features drive the similarity ranking.
    If no numeric features are given, the filtered pool is returned as-is
    (similarity_percentage = None).
    """
    query = session.query(GrapeStandard)

    if wine_type:
        query = query.filter(GrapeStandard.wine_type == wine_type)
    if food_pairing:
        query = query.filter(GrapeStandard.food_pairings.like(f"%{food_pairing}%"))

    candidates = query.all()

    input_features: dict[str, float] = {}
    if alcohol is not None:
        input_features["avg_alcohol"] = alcohol
    if acidity is not None:
        input_features["avg_acidity"] = acidity
    if body is not None:
        input_features["avg_body"] = body

    if not input_features:
        # Filter-only query: no distance to compute, return first top_n
        return [_format_result(i + 1, c, None) for i, c in enumerate(candidates[:top_n])]

    return _score_and_rank(candidates, input_features, top_n)
