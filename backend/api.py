# backend/api.py
"""
Flask HTTP API for BlindTaste.

Endpoints:
  POST /api/recommend/label   -- Label Input mode
  POST /api/recommend/flavor  -- Flavor Profile mode
  GET  /api/wine-types        -- Distinct wine types (for dropdowns)
  GET  /api/grapes            -- Distinct grape names, optionally filtered by ?wine_type=
  GET  /api/food-pairings     -- All unique food pairings (for dropdowns)

Every recommendation request is persisted to the Log and RecommendationResult tables.
"""

import json
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import GrapeStandard, Log, RecommendationResult
from recommender import recommend_flavor, recommend_label

# ---------------------------------------------------------------------------
# App + DB setup
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR.parent / "data" / "blindtaste.db"

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionFactory = sessionmaker(bind=engine)

app = Flask(__name__)
CORS(app)


def _get_session():
    return SessionFactory()


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _persist_log(session, input_mode: str, user_input: dict, results: list) -> None:
    """Insert a Log row and one RecommendationResult row per returned result."""
    log = Log(
        timestamp=datetime.now().isoformat(),
        input_mode=input_mode,
        user_input=json.dumps(user_input),
    )
    session.add(log)
    session.flush()  # populate log.id_pk before referencing it

    for result in results:
        session.add(RecommendationResult(
            log_id_pk_fk1=log.id_pk,
            grape_id_pk_fk2=result["id_pk"],
            similarity_percentage=result["similarity_percentage"],
            rank_order=result["rank"],
        ))


# ---------------------------------------------------------------------------
# Recommendation endpoints
# ---------------------------------------------------------------------------

@app.route("/api/recommend/label", methods=["POST"])
def recommend_label_endpoint():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    missing = [f for f in ("wine_type", "alcohol", "main_grape") if data.get(f) is None]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        wine_type  = str(data["wine_type"])
        alcohol    = float(data["alcohol"])
        main_grape = str(data["main_grape"])
        acidity    = float(data["acidity"]) if data.get("acidity") is not None else None
        body       = float(data["body"])    if data.get("body")    is not None else None
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    session = _get_session()
    try:
        results = recommend_label(session, wine_type, alcohol, main_grape, acidity, body)
        _persist_log(session, "label", data, results)
        session.commit()
        return jsonify({"results": results})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@app.route("/api/recommend/flavor", methods=["POST"])
def recommend_flavor_endpoint():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    wine_type    = data.get("wine_type")    or None
    food_pairing = data.get("food_pairing") or None

    try:
        alcohol = float(data["alcohol"]) if data.get("alcohol") is not None else None
        acidity = float(data["acidity"]) if data.get("acidity") is not None else None
        body    = float(data["body"])    if data.get("body")    is not None else None
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    if not any([wine_type, alcohol, acidity, body, food_pairing]):
        return jsonify({"error": "At least one field must be provided"}), 400

    session = _get_session()
    try:
        results = recommend_flavor(session, wine_type, alcohol, acidity, body, food_pairing)
        _persist_log(session, "flavor_profile", data, results)
        session.commit()
        return jsonify({"results": results})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Dropdown helper endpoints
# ---------------------------------------------------------------------------

@app.route("/api/wine-types", methods=["GET"])
def wine_types():
    session = _get_session()
    try:
        rows = (
            session.query(GrapeStandard.wine_type)
            .distinct()
            .order_by(GrapeStandard.wine_type)
            .all()
        )
        return jsonify({"wine_types": [r[0] for r in rows]})
    finally:
        session.close()


@app.route("/api/grapes", methods=["GET"])
def grapes():
    """Return distinct grape names. Accepts optional ?wine_type= query param."""
    session = _get_session()
    try:
        query = session.query(GrapeStandard.grape_name).distinct()
        wine_type = request.args.get("wine_type")
        if wine_type:
            query = query.filter(GrapeStandard.wine_type == wine_type)
        rows = query.order_by(GrapeStandard.grape_name).all()
        return jsonify({"grapes": [r[0] for r in rows]})
    finally:
        session.close()


@app.route("/api/food-pairings", methods=["GET"])
def food_pairings():
    """Return unique food pairings. Accepts optional ?wine_type= to filter by type."""
    session = _get_session()
    try:
        query = session.query(GrapeStandard.food_pairings)
        wine_type = request.args.get("wine_type")
        if wine_type:
            query = query.filter(GrapeStandard.wine_type == wine_type)
        rows = query.all()
        pairings: set[str] = set()
        for (fp_str,) in rows:
            for item in fp_str.split(", "):
                if item.strip():
                    pairings.add(item.strip())
        return jsonify({"food_pairings": sorted(pairings)})
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Logs endpoint (admin / debugging)
# ---------------------------------------------------------------------------

@app.route("/api/logs", methods=["GET"])
def logs():
    """
    Return recent recommendation logs with their results joined.
    Accepts optional ?limit= query param (default 50, max 200).
    """
    from sqlalchemy import desc
    limit = min(int(request.args.get("limit", 50)), 200)
    session = _get_session()
    try:
        log_rows = (
            session.query(Log)
            .order_by(desc(Log.id_pk))
            .limit(limit)
            .all()
        )
        result = []
        for log in log_rows:
            recs = (
                session.query(RecommendationResult, GrapeStandard)
                .join(GrapeStandard, RecommendationResult.grape_id_pk_fk2 == GrapeStandard.id_pk)
                .filter(RecommendationResult.log_id_pk_fk1 == log.id_pk)
                .order_by(RecommendationResult.rank_order)
                .all()
            )
            result.append({
                "id":         log.id_pk,
                "timestamp":  log.timestamp,
                "input_mode": log.input_mode,
                "user_input": json.loads(log.user_input),
                "recommendations": [
                    {
                        "rank":                 rr.rank_order,
                        "grape_name":           gs.grape_name,
                        "wine_type":            gs.wine_type,
                        "similarity_percentage": rr.similarity_percentage,
                    }
                    for rr, gs in recs
                ],
            })
        return jsonify({"total": len(result), "logs": result})
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
