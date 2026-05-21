# backend/recommender.py — Content-based recommendation using Min-Max normalization and Euclidean distance.
import math
from sqlalchemy.orm import Session
from models import GrapeStandard


# Fixed theoretical bounds keep normalization stable regardless of candidate pool size.
FEATURE_BOUNDS: dict[str, tuple[float, float]] = {
    "avg_alcohol": (8.0, 16.0),
    "avg_acidity": (1.0, 3.0),
    "avg_body":    (1.0, 5.0),
}




# --- Helpers ---

def _normalize(features: dict[str, float]) -> dict[str, float]:
    result = {}
    for k, v in features.items():
        lo, hi = FEATURE_BOUNDS[k]
        result[k] = (v - lo) / (hi - lo)
    return result


def _euclidean(a: dict[str, float], b: dict[str, float]) -> float:
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
    if not candidates:
        return []

    active_keys = list(input_features.keys())
    input_norm = _normalize(input_features)

    # Scale by actual max distance — theoretical sqrt(n) clusters all scores near 100%.
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




# --- Label Input ---

def recommend_label(
    session: Session,
    wine_type: str,
    alcohol: float,
    main_grape: str,
    acidity: float | None = None,
    body: float | None = None,
    top_n: int = 5,
) -> list[dict]:
    candidates = (
        session.query(GrapeStandard)
        .filter(GrapeStandard.wine_type == wine_type)
        .all()
    )
    # Exclude all expressions of main_grape so results are always a different variety.
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



# --- Flavor Input ---

def recommend_flavor(
    session: Session,
    wine_type: str | None = None,
    alcohol: float | None = None,
    acidity: float | None = None,
    body: float | None = None,
    food_pairing: str | None = None,
    top_n: int = 5,
) -> list[dict]:
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
        return [_format_result(i + 1, c, None) for i, c in enumerate(candidates[:top_n])]

    return _score_and_rank(candidates, input_features, top_n)
