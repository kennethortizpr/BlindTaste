# BlindTaste — Project Context

> This file captures all design decisions, schemas, and conventions for the BlindTaste project.  
> Keep it up to date as new decisions are made. Claude Code reads this on session start.

---

## 1. Project Overview

**BlindTaste** is a web-based wine recommendation engine developed as a Computer Science thesis project.

**Core concept:** given some characteristics of a wine (from its label) or a desired flavor profile, the system returns the **top 5 grape varieties** whose aggregated profile best matches the input.

**Two input modes:**
1. **Label Input** — user enters what they read on a wine's label to find *similar but different* grape varieties.
2. **Flavor Profile Input** — user describes the taste profile they want, regardless of any specific wine.

---

## 2. Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend language | Python | Rich data/ML ecosystem, fast prototyping |
| Database | SQLite | Small catalog (~309 rows), serverless, portable, read-heavy workload |
| ORM | SQLAlchemy | Portability (can migrate DB later), cleaner models, safer than raw SQL |
| Data manipulation | pandas | Used for Excel reading and aggregation |
| ML / similarity | Python `math` (stdlib) | Euclidean distance + Min-Max normalization; no external ML lib needed at this data scale |
| HTTP API | Flask + flask-cors | Lightweight REST API; CORS enabled for the static frontend |
| Frontend | HTML + CSS + vanilla JS | Static template; forms wired to API via `fetch()` |

**Why not deep learning:** dataset is small (~309 centroids, 3-5 numeric dimensions). Neural models would be overkill, prone to overfitting, non-interpretable, and provide no benefit over well-implemented k-NN. Content-based filtering with distance metrics is the literature-standard approach for this data size and structure.

---

## 3. Data Source

**Original dataset:** `XWines_Full_100K_wines.csv` — 100,646 wines with attributes including grape varieties, ABV, body, acidity, type, country, region, winery, food pairings.

**Curated dataset:** `data/BlindTaste_Varietal_Wines.xlsx`
- **Sheet "Varietal Wines"** — 72,496 rows, 19 columns.  Only `Varietal/100%` wines (single-grape wines) to avoid ambiguity of blends.
- **Sheet "Grape Summary"** — 576 rows, per-grape aggregate stats (for manual inspection, not consumed by the populate script).

**Why only varietals:**
- Blend ordering is unreliable (~32% of blends are alphabetically sorted, meaning the first listed grape is NOT necessarily the dominant one).
- Using only varietals gives unambiguous per-grape attribution.
- 72K varietal wines is more than enough data volume.
- Academically defensible: "we filtered out blends to avoid attribution bias in centroid computation."

**Excel column conventions (snake_case):** `Wine_ID, Wine_Name, Type, Elaborate, Grape, Food_Pairings, ABV, Body, Body_Numeric, Acidity, Acidity_Numeric, Code, Country, Region_ID, Region_Name, Winery_ID, Winery_Name, Website, Vintages`.

---

## 4. Numeric Mappings

To enable centroid computation and distance metrics, categorical attributes were mapped to ordinal scales:

**Body** (1–5 scale):
| Label | Value |
|-------|-------|
| Very light-bodied | 1 |
| Light-bodied | 2 |
| Medium-bodied | 3 |
| Full-bodied | 4 |
| Very full-bodied | 5 |

**Acidity** (1–3 scale):
| Label | Value |
|-------|-------|
| Low | 1 |
| Medium | 2 |
| High | 3 |

**ABV** is already numeric (range ~8% to ~16% typically).

---

## 5. Database Schema

**Location:** `data/blindtaste.db` (SQLite)  
**Models file:** `backend/models.py`

### 5.1 `grape_standard`

The "standardized grape" table — the centroid representation used for recommendations.

| Column | Type | Notes |
|--------|------|-------|
| `id_pk` | Integer, PK | Auto-increment surrogate key |
| `grape_name` | String, NOT NULL | e.g., "Chardonnay", "Malbec" |
| `wine_type` | String, NOT NULL | Red, White, Rosé, Sparkling, Dessert, Dessert Port |
| `avg_alcohol` | Float, NOT NULL | Mean ABV across all wines of this (grape, type) combo |
| `avg_acidity` | Float, NOT NULL | Mean of numeric acidity (1–3 scale) |
| `avg_body` | Float, NOT NULL | Mean of numeric body (1–5 scale) |
| `food_pairings` | String, NOT NULL | Comma-separated, alphabetically sorted, unique pairings |
| `description` | String | Auto-generated descriptive sentence |

**Constraint:** `UniqueConstraint('grape_name', 'wine_type', name='uq_grape_type')` — enforces that each grape-type combination is a single logical entry.

**Population rules:**
- One row per unique `(grape, wine_type)` combination.
- Minimum threshold: **≥50 wines per combination** to create a row (964 combinations below threshold were skipped).
- Current population: **144 rows** — each centroid is backed by at least 50 wines.
- **Why 50:** groups below this are almost exclusively highly obscure, regionally rare grape varieties that are practically unobtainable for most consumers. A threshold of 50 balances variety in recommendations against statistical reliability, ensuring every recommended grape is reasonably findable.

**Why separate by wine_type:** a Chardonnay White (avg body 3.84) is sensorially different from a Chardonnay Sparkling (avg body 2.93). Merging them would produce a centroid that represents neither.

### 5.2 `log`

Every user recommendation request.

| Column | Type | Notes |
|--------|------|-------|
| `id_pk` | Integer, PK | |
| `timestamp` | String, NOT NULL | When the request was made |
| `input_mode` | String, NOT NULL | "label" or "flavor_profile" |
| `user_input` | String, NOT NULL | Serialized input (JSON string) |

### 5.3 `recommendation_result`

Links logs to the top-5 grape recommendations returned.

| Column | Type | Notes |
|--------|------|-------|
| `log_id_pk_fk1` | FK → log.id_pk, PK | Composite PK part 1 |
| `grape_id_pk_fk2` | FK → grape_standard.id_pk, PK | Composite PK part 2 |
| `similarity_percentage` | Float | How similar this grape was to the input |
| `rank_order` | Integer | 1 = best match, 2, 3 |

### 5.4 `REFERENCE_DATASET` (imaginary)

Shown in the ER diagram but **not implemented as a table**. The full wine dataset lives only in `data/BlindTaste_Varietal_Wines.xlsx` and is read once during population. Keeping 72K rows in the DB would bloat it unnecessarily since the app only queries `grape_standard` at runtime.

---

## 6. Food Pairings — Design Decision

**Approach:** Option A — pairings stored as a single comma-separated string in `grape_standard.food_pairings`.

**Filtering:** SQL `LIKE '%PairingName%'` at query time.

**Why not a junction table:** simpler for this scale; 61 unique pairings, no substring collisions verified (no pairing is a substring of another).

**What pairings are stored:** ALL unique pairings that appear in any wine of that (grape, type) group — no frequency threshold applied.

---

## 7. Populate Script Logic

**File:** `backend/populate_db.py`

**Flow:**
1. Load `data/BlindTaste_Varietal_Wines.xlsx` (sheet "Varietal Wines").
2. Normalize wine type names: `"Dessert/Port"` → `"Dessert Port"` (via `TYPE_NAMES` dict before grouping).
3. Parse `Food_Pairings` cells from Python list literal strings.
4. Wipe existing rows in `grape_standard` (idempotent).
5. Group by `(Grape, Type)`; skip groups with <200 wines.
6. For each surviving group, compute:
   - `avg_alcohol` = mean(ABV), rounded to 2 decimals
   - `avg_body` = mean(Body_Numeric)
   - `avg_acidity` = mean(Acidity_Numeric)
   - `food_pairings` = sorted union of all unique pairings
   - `description` = auto-generated sentence (see §8)
7. Insert into `grape_standard` via SQLAlchemy session.

---

## 8. Auto-generated Descriptions

The `description` field is generated at populate time using threshold-based labels:

**Body labels** (from `avg_body`):
- `< 1.5` → "very light-bodied"
- `< 2.5` → "light-bodied"
- `< 3.5` → "medium-bodied"
- `< 4.5` → "full-bodied"
- `≥ 4.5` → "very full-bodied"

**Acidity labels** (from `avg_acidity`):
- `< 1.67` → "low acidity"
- `< 2.33` → "medium acidity"
- `≥ 2.33` → "high acidity"

**Alcohol labels** (from `avg_alcohol`):
- `< 11` → "low alcohol content"
- `< 13` → "moderate alcohol content"
- `< 14` → "medium-high alcohol content"
- `≥ 14` → "high alcohol content"

**Template:** `"{grape} ({wine_type}) — A {body_label} wine with {acidity_label} and {alcohol_label} (~{avg_alcohol:.1f}% ABV)."`

**Examples:**
- "Malbec (Red) — A very full-bodied wine with high acidity and medium-high alcohol content (~13.9% ABV)."
- "Riesling (White) — A light-bodied wine with high acidity and moderate alcohol content (~11.9% ABV)."

---

## 9. Recommendation Algorithm — Design Decisions

> Status: **implemented** in `backend/recommender.py`.

### 9.1 Label Input

**Purpose:** user enters attributes read on a wine label; system returns top 5 *different* grapes with similar profile.

**Input fields:**
| Field | Role | Required |
|-------|------|----------|
| Wine Type | Pre-filter (categorical) | Yes |
| Alcohol % | Numeric feature | Yes |
| Main Grape | Exclusion (the input grape is removed from candidates) | Yes |
| Acidity | Numeric feature | **Optional** |
| Body | Numeric feature | **Optional** |

**Exclusion rule:** exclude only the exact `(grape_name, wine_type)` combination — NOT all entries with that grape name. Example: if user has a Chardonnay White, a Chardonnay Sparkling can still be recommended.

**Removed fields:** `Country` (not useful; `grape_standard` has no country dimension).

### 9.2 Flavor Profile Input

**Purpose:** user describes a desired taste profile (no specific wine in mind); system returns top 5 matching grapes.

**Input fields:**
| Field | Role | Required |
|-------|------|----------|
| Wine Type | Pre-filter (categorical) | **Optional** |
| Desired Body | Numeric feature | **Optional** |
| Desired Acidity | Numeric feature | **Optional** |
| Desired ABV | Numeric feature | **Optional** |
| Food Pairing | Filter (SQL LIKE on `food_pairings`) | **Optional** |

**Validation rule:** at least one field must be provided (enforced by the API layer).

**No exclusion grape** — the user is not describing a specific wine, so no variety is excluded.

**Filter-only queries:** if only `wine_type` and/or `food_pairing` are provided (no numeric features), the filtered candidate pool is returned ordered by grape name, with `similarity_percentage = null`.

### 9.3 Cross-cutting technical decisions

All finalized and implemented:

- **Optional features handling:** variable dimensions — distance computed only over the features the user provided. No defaults substituted.
- **Normalization:** Min-Max scaling using fixed theoretical bounds (not data-driven), so normalization is stable across queries regardless of DB content.
  - `avg_alcohol`: [8.0, 16.0]
  - `avg_acidity`: [1.0, 3.0]
  - `avg_body`: [1.0, 5.0]
- **Weights:** all equal (each normalized dimension contributes equally).
- **Distance metric:** Euclidean.
- **Distance → similarity %:** `similarity = max(0, (1 - d / sqrt(n)) * 100)`, where `n` = number of active features. `sqrt(n)` is the theoretical max Euclidean distance when every dimension is in [0, 1] after normalization. Result is rounded to 1 decimal place.

---

## 10. Frontend Status

**Location:** `frontend/`

**Template:** Custom HTML5/CSS3 template. Each page has a full-viewport animated intro section (title fades/scrolls away, revealing the nav), a centered navbar, and a white content card.

**Pages:**
- `about.html` — landing/intro page with project description and hero image
- `label_input.html` — Label Input form, fully wired to `POST /api/recommend/label`
- `flavor_input.html` — Flavor Profile Input form, fully wired to `POST /api/recommend/flavor`
- `results.html` — Results page, reads from `localStorage`, renders top-5 cards
- `logs.html` — Admin page, fetches `GET /api/logs`, renders full request history as a table

**Form behavior:**
- Dropdowns (Wine Type, Main Grape, Food Pairing) are populated dynamically from the API on page load.
- Main Grape list refreshes whenever Wine Type changes (`/api/grapes?wine_type=`).
- Food Pairing list refreshes whenever Wine Type changes (`/api/food-pairings?wine_type=`); shows all pairings when no type is selected.
- Body blank option reads "— Any Body —"; Acidity blank option reads "— Any Acidity —".
- Alcohol % input has a fixed `width: 5rem` inline style (template default was too narrow to show placeholder).
- On submit, results are stored in `localStorage` (`bt_results`, `bt_input_mode`, `bt_input`) and the user is redirected to `results.html`.

**Styling overrides** (inline `<style>` block on each page, does not touch `main.css`):
- Base font: `13pt` (down from `16pt`)
- Nav: `2.75rem` height, `54rem` max-width, tabs centered
- Content card: `54rem` max-width, reduced padding
- Intro: `100vh` (required for scroll trigger), title centered vertically at `4rem`
- `logs.html` uses `72rem` max-width (wider to accommodate the table)

**Images directory layout** (`frontend/images/`):
- `backgrounds/` — `bg.jpg`, `overlay.png`, `pic02.jpg`–`pic09.jpg` (parallax/background images used by `main.css`)
- `extra/` — `pic01.jpg` (wine glass pouring photo shown in `about.html`)
- `grapes/` — per-grape images (57 files, mixed naming conventions); use TBD

**Tech:** static HTML/CSS/vanilla JS, no build step. Template JS suite kept intact (required for intro animation and nav behavior).

---

## 11. Project Structure

```
TESINA/
├── backend/
│   ├── models.py          # SQLAlchemy models (GrapeStandard, Log, RecommendationResult)
│   ├── create_db.py       # Creates empty tables (DB path: data/blindtaste.db)
│   ├── populate_db.py     # Populates grape_standard from Excel (idempotent)
│   ├── recommender.py     # Core recommendation algorithm (recommend_label, recommend_flavor)
│   └── api.py             # Flask REST API (5 endpoints, logs every request to DB)
├── data/
│   ├── BlindTaste_Varietal_Wines.xlsx   # Curated wine dataset
│   └── blindtaste.db                   # Generated SQLite database
├── frontend/
│   ├── about.html         # Landing page
│   ├── label_input.html   # Label Input form (wired to API)
│   ├── flavor_input.html  # Flavor Profile Input form (wired to API)
│   ├── results.html       # Results page (reads localStorage, renders top-5 cards)
│   ├── logs.html          # Admin logs page (fetches /api/logs)
│   ├── assets/            # CSS, JS, fonts
│   └── images/
│       ├── backgrounds/   # bg.jpg, overlay.png, pic02-pic09.jpg
│       ├── extra/         # pic01.jpg (wine glass photo)
│       └── grapes/        # per-grape variety images (57 files)
├── venv/                  # Python virtual environment (local)
└── CONTEXT.md             # This file
```

---

## 12. Setup & Run

```bash
# Activate venv (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install dependencies (one-time)
pip install sqlalchemy pandas openpyxl flask flask-cors

# Create empty tables (uses absolute path internally — can be run from anywhere)
python backend/create_db.py

# Populate grape_standard (re-runnable, idempotent)
python backend/populate_db.py

# Start the API (runs on http://localhost:5000)
cd backend
python api.py
```

**Note:** the frontend is served separately (e.g. VS Code Live Server on port 5500). The API must be running on port 5000 for the forms to load dropdowns and submit recommendations.

---

## 13. Open Questions / Next Steps

1. ~~Finalize Flavor Profile Input fields.~~ ✓ Done (§9.2)
2. ~~Confirm cross-cutting algorithm decisions (§9.3).~~ ✓ Done
3. ~~Implement the recommendation algorithm.~~ ✓ Done (`backend/recommender.py`)
4. ~~Build an HTTP API (Flask) to expose the recommender to the frontend.~~ ✓ Done (`backend/api.py`)
5. ~~Rework the frontend forms to match the finalized input schema.~~ ✓ Done (`label_input.html`, `flavor_input.html`)
6. ~~Build a results page (`frontend/results.html`).~~ ✓ Done
7. ~~Wire `Log` and `RecommendationResult` persistence into the API flow.~~ ✓ Done (every request logged in `api.py`)
8. ~~Build admin logs page.~~ ✓ Done (`logs.html`)
9. Decide how to use grape images in `images/grapes/` (e.g. show on results cards).

---

*Last updated: 2026-05-09 (session 2)*
