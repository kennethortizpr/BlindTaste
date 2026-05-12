# BlindTaste

> A content-based wine recommendation engine — built as a Computer Science thesis project.

**Live demo:** [blindtaste — GitHub Pages](https://kennethortiz20.github.io/blindtaste) &nbsp;|&nbsp; **API:** [blindtaste.onrender.com](https://blindtaste.onrender.com)

---

## What It Does

BlindTaste returns the top 5 grape varieties whose sensory profile best matches a given input. It operates in two modes:

| Mode | Description |
|------|-------------|
| **Label Input** | Enter details from a wine label (type, grape, ABV, optional body & acidity) — the engine finds similar-but-*different* varieties |
| **Flavor Profile** | Describe the taste you want (body, acidity, ABV, food pairing) with no specific wine in mind |

---

## Algorithm

BlindTaste uses **content-based filtering** with Euclidean distance:

1. Every grape variety in the database is stored as a **centroid** — the mean ABV, body, and acidity computed across all wines of that variety and type.
2. The user's input is **Min-Max normalized** to [0, 1] using fixed theoretical bounds (ABV: 8–16, body: 1–5, acidity: 1–3).
3. **Euclidean distance** is computed between the input vector and each centroid — only over the dimensions the user actually provided (variable-dimensional, no defaults substituted).
4. Distance is converted to a **similarity percentage**:

```
similarity = max(0, (1 - d / √n) × 100)
```

where `n` is the number of active features and `√n` is the theoretical maximum distance in a unit hypercube.

5. The top 5 closest centroids are returned, ranked by similarity.

No external ML libraries are used — the algorithm is implemented with Python's standard `math` library.

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend language | Python 3 | |
| Web framework | Flask + flask-cors | Lightweight REST API |
| ORM / Database | SQLAlchemy + SQLite | 144-row centroid catalog |
| Data processing | pandas, openpyxl | Excel ingestion at populate time |
| Algorithm | `math` stdlib | Euclidean distance + Min-Max normalization |
| Production server | gunicorn | WSGI server on Render |
| Frontend | HTML5, CSS3, Vanilla JS | Static, no build step |
| Frontend hosting | GitHub Pages | Free, HTTPS |
| Backend hosting | Render (Free tier) | Free, HTTPS, cold-start ~30s |

---

## Dataset

Built on a curated subset of the [XWines](https://github.com/rogerioxavier/X-Wines) dataset (100K wines):

- **72,496 varietal wines** kept — blends excluded to avoid ambiguous grape attribution (~32% of blends are alphabetically sorted, meaning the first grape is not necessarily dominant)
- Groups with **fewer than 50 wines** filtered out — these correspond to highly obscure, regionally rare varieties that are practically unobtainable
- **144 grape–type combinations** remain across Red, White, Rosé, Sparkling, Dessert, and Dessert Port categories

---

## Project Structure

```
TESINA/
├── backend/
│   ├── models.py          # SQLAlchemy models (GrapeStandard, Log, RecommendationResult)
│   ├── create_db.py       # Creates empty tables (DB path: data/blindtaste.db)
│   ├── populate_db.py     # Populates grape_standard from Excel (idempotent)
│   ├── recommender.py     # Core recommendation algorithm (recommend_label, recommend_flavor)
│   └── api.py             # Flask REST API (7 endpoints incl. /api/docs, logs every request to DB)
├── data/
│   ├── BlindTaste_Varietal_Wines.xlsx   # Curated wine dataset
│   └── blindtaste.db                   # SQLite database (committed to repo)
├── frontend/
│   ├── about.html         # Landing page
│   ├── label_input.html   # Label Input form
│   ├── flavor_input.html  # Flavor Profile Input form 
│   ├── results.html       # Results page (reads localStorage, renders top-5 cards)
│   ├── logs.html          # Logs page
│   ├── assets/            # CSS, JS, fonts
│   └── images/
│       ├── backgrounds/   
│       ├── extra/        
│       └── grapes/        # per-grape variety images 
└── index.html             # Root redirect → frontend/about.html (for GitHub Pages)
```

---

## Setup & Run

```powershell
# 1. Activate virtual environment (Windows)
.\venv\Scripts\Activate.ps1

# 2. Install dependencies (one-time)
pip install sqlalchemy pandas openpyxl flask flask-cors gunicorn

# 3. Create empty tables
python backend/create_db.py

# 4. Populate grape_standard from dataset
python backend/populate_db.py

# 5. Start the API (http://localhost:5000)
cd backend
python api.py
```

Serve the `frontend/` folder separately (e.g. VS Code Live Server on port 5500). The API must be running on port 5000 for dropdowns and submissions to work.

---

## API Reference

Full documentation available at [`GET /api/docs`](https://blindtaste.onrender.com/api/docs).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/recommend/label` | Top 5 grapes for a wine label |
| `POST` | `/api/recommend/flavor` | Top 5 grapes for a flavor profile |
| `GET` | `/api/wine-types` | All distinct wine types |
| `GET` | `/api/grapes?wine_type=` | Grape names, optionally filtered by type |
| `GET` | `/api/food-pairings?wine_type=` | Food pairings, optionally filtered by type |
| `GET` | `/api/logs?limit=` | Recent recommendation logs |
| `GET` | `/api/docs` | This documentation as JSON |

---

*BlindTaste — Computer Science Thesis, 2026*
