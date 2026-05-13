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

**Current status:** **deployed to production**. Frontend on GitHub Pages, backend on Render. See §14.

---

## 2. Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend language | Python | Rich data/ML ecosystem, fast prototyping |
| Database | SQLite | Small catalog (~144 rows), serverless, portable, read-heavy workload |
| ORM | SQLAlchemy | Portability (can migrate DB later), cleaner models, safer than raw SQL |
| Data manipulation | pandas | Used for Excel reading and aggregation |
| ML / similarity | Python `math` (stdlib) | Euclidean distance + Min-Max normalization; no external ML lib needed at this data scale |
| HTTP API | Flask + flask-cors | Lightweight REST API; CORS enabled for the static frontend |
| Production server | gunicorn | WSGI server used by Render in production |
| Frontend | HTML + CSS + vanilla JS | Static template; forms wired to API via `fetch()` |
| Frontend hosting | GitHub Pages | Static hosting, free, HTTPS |
| Backend hosting | Render (Free tier) | Python-friendly PaaS, free, HTTPS |

**Why not deep learning:** dataset is small (~144 centroids, 3 numeric dimensions). Neural models would be overkill, prone to overfitting, non-interpretable, and provide no benefit over well-implemented k-NN. Content-based filtering with distance metrics is the literature-standard approach for this data size and structure.

---

## 3. Data Source

**Original dataset:** `XWines_Full_100K_wines.csv` — 100,646 wines with attributes including grape varieties, ABV, body, acidity, type, country, region, winery, food pairings.

**Curated dataset:** `data/BlindTaste_Varietal_Wines.xlsx`
- **Sheet "Varietal Wines"** — 72,496 rows, 19 columns. Only `Varietal/100%` wines (single-grape wines) to avoid ambiguity of blends.
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

**ABV** is numeric (%) in the dataset. In Flavor Profile Input it is exposed as a 5-level categorical selector that maps to representative midpoint values (see §9.2).

**ABV industry classification:**
| Level | Range | Midpoint sent to API |
|-------|-------|---------------------|
| Very Low | < 10% | 9.0 |
| Low | 10% – 11.9% | 11.0 |
| Medium | 12% – 13.4% | 12.7 |
| High | 13.5% – 14.9% | 14.0 |
| Very High | ≥ 15% | 15.0 |

Note: in Label Input, the user types the exact ABV % read from the label — no discretization.

---

## 5. Database Schema

**Location:** `data/blindtaste.db` (SQLite) — committed to the repo so Render uses it directly on deploy.  
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
| `description` | String | Hand-written descriptive sentence per variety |

**Constraint:** `UniqueConstraint('grape_name', 'wine_type', name='uq_grape_type')` — enforces that each grape-type combination is a single logical entry.

**Population rules:**
- One row per unique `(grape, wine_type)` combination.
- Minimum threshold: **≥50 wines per combination** to create a row (964 combinations below threshold were skipped).
- Current population: **144 rows** — each centroid is backed by at least 50 wines.
- **Why 50:** groups below this are almost exclusively highly obscure, regionally rare grape varieties that are practically unobtainable for most consumers. A threshold of 50 balances variety in recommendations against statistical reliability, ensuring every recommended grape is reasonably findable.

**Why separate by wine_type:** a Chardonnay White (avg body 3.84) is sensorially different from a Chardonnay Sparkling (avg body 2.93). Merging them would produce a centroid that represents neither.

**Descriptions:** hand-written per variety (replaced the auto-generated template). Each covers color hue, renowned regions/countries, main flavor notes (3–5), and a stats line (body, acidity, ABV). Example: *"A deep ruby-garnet wine with violet hues, Malbec is most celebrated in Argentina's Mendoza and in its native Cahors, France. Expect rich notes of blackberry, plum, dark chocolate, and a hint of violet. Full-bodied, medium acidity, ~13.9% ABV."*

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
| `rank_order` | Integer | 1 = best match, up to 5 |

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
5. Group by `(Grape, Type)`; skip groups with <50 wines.
6. For each surviving group, compute:
   - `avg_alcohol` = mean(ABV), rounded to 2 decimals
   - `avg_body` = mean(Body_Numeric)
   - `avg_acidity` = mean(Acidity_Numeric)
   - `food_pairings` = sorted union of all unique pairings
   - `description` = placeholder (overwritten by hand-written descriptions via `load_descriptions.py`)
7. Insert into `grape_standard` via SQLAlchemy session.

---

## 8. Descriptions

**Current state:** hand-written, loaded into DB via `load_descriptions.py` (run once after populate).

**Format per entry:** color hue + renowned regions/countries + flavor notes (3–5) + stats line.  
**Template:** `"A [color] wine, [grape] is [regional context]. Expect [flavor notes]. [Body], [acidity], ~[ABV]% ABV."`

**Auto-generated label thresholds** (used as fallback if hand-written description is missing):

Body: `< 1.5` → very light-bodied · `< 2.5` → light-bodied · `< 3.5` → medium-bodied · `< 4.5` → full-bodied · `≥ 4.5` → very full-bodied

Acidity: `< 1.67` → low · `< 2.33` → medium · `≥ 2.33` → high

Alcohol: `< 11` → low · `< 13` → moderate · `< 14` → medium-high · `≥ 14` → high

---

## 9. Recommendation Algorithm — Design Decisions

> Status: **implemented** in `backend/recommender.py`.

### 9.1 Label Input

**Purpose:** user enters attributes read on a wine label; system returns top 5 *different* grapes with similar profile.

**Input fields:**
| Field | Role | Required |
|-------|------|----------|
| Wine Type | Pre-filter (categorical) | Yes |
| Alcohol % | Numeric feature (exact value from label) | Yes |
| Main Grape | Exclusion — all entries with this grape name are removed | Yes |
| Acidity | Numeric feature (1–3) | **Optional** |
| Body | Numeric feature (1–5) | **Optional** |

**Exclusion rule:** exclude **all entries with the same grape name**, regardless of wine type. This is intentional — the goal is to discover genuinely different varieties, not different expressions of the same grape. If the user inputs a Chardonnay White, no Chardonnay variant (White, Sparkling, or Dessert) will appear in the results.

**Removed fields:** `Country` (not useful; `grape_standard` has no country dimension).

### 9.2 Flavor Profile Input

**Purpose:** user describes a desired taste profile (no specific wine in mind); system returns top 5 matching grapes.

**Input fields:**
| Field | UI Control | Role | Required |
|-------|------------|------|----------|
| Wine Type | Dropdown | Pre-filter (categorical) | **Optional** |
| Desired Body | Dropdown (Very Light → Very Full) | Numeric feature (1–5) | **Optional** |
| Desired Acidity | Dropdown (Low / Medium / High) | Numeric feature (1–3) | **Optional** |
| Desired ABV | Dropdown (5-level selector) | Numeric feature (midpoint float) | **Optional** |
| Food Pairing | Dropdown | Filter (SQL LIKE on `food_pairings`) | **Optional** |

**ABV selector mapping** (frontend sends the midpoint float to the API):
| Label shown to user | Value sent to API |
|--------------------|-------------------|
| Very Low (< 10%) | 9.0 |
| Low (10% – 11.9%) | 11.0 |
| Medium (12% – 13.4%) | 12.7 |
| High (13.5% – 14.9%) | 14.0 |
| Very High (≥ 15%) | 15.0 |

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
- **Distance → similarity %:** `similarity = max(0, (1 - d / max_d) * 100)`, where `max_d` = **actual maximum distance across all candidates in the pool** (data-relative scale). The worst match in the pool scores 0%, the best scores 100%, spreading results naturally across the real data range. Using a theoretical maximum (e.g. `sqrt(n)`) would compress all scores above 90% because real centroids cluster in a narrow region of the feature space. Result is rounded to 1 decimal place.
- **Known limitation:** Min-Max bounds [8, 16] for ABV are appropriate for table wines but Port/Dessert Port centroids (~19–20% ABV) exceed the upper bound. This is acceptable because Port is its own wine_type and the pre-filter prevents cross-type comparisons.

---

## 10. Frontend Status

**Location:** `frontend/`

**Template:** Custom HTML5/CSS3 template. Each page has a full-viewport animated intro section (title fades/scrolls away, revealing the nav), a centered navbar, and a white content card.

**Pages:**
- `about.html` — landing/intro page with project description, hero image, "How It Works" and "The Dataset" sections
- `label_input.html` — Label Input form, fully wired to `POST /api/recommend/label`
- `flavor_input.html` — Flavor Profile Input form, fully wired to `POST /api/recommend/flavor`
- `results.html` — Results page, reads from `localStorage`, renders top-5 cards with grape images
- `logs.html` — Admin page, fetches `GET /api/logs`, renders full request history as a table

**Form behavior:**
- Dropdowns (Wine Type, Main Grape, Food Pairing) are populated dynamically from the API on page load.
- Main Grape list refreshes whenever Wine Type changes (`/api/grapes?wine_type=`).
- Food Pairing list refreshes whenever Wine Type changes (`/api/food-pairings?wine_type=`); shows all pairings when no type is selected.
- Body blank option reads "— Any Body —"; Acidity blank option reads "— Any Acidity —"; ABV blank option reads "— Any ABV —".
- Alcohol % in Label Input: free numeric text input (`width: 5rem`), user types exact value from label.
- Desired ABV in Flavor Profile: 5-level dropdown selector (Very Low → Very High) sending midpoint floats.
- On submit, results are stored in `localStorage` (`bt_results`, `bt_input_mode`, `bt_input`) and the user is redirected to `results.html`.

**API base URL:** all pages reference `const API_BASE` near the top of their page script (`label.js` / `flavor.js` for the form pages; inline for `results.html` and `logs.html`). **In production this points to the Render URL** (see §14). To run the frontend against a local backend, swap to `http://localhost:5000` in `assets/js/label.js` and `assets/js/flavor.js`.

**Styling overrides** (inline `<style>` block on each page, does not touch `main.css` except for the nav and main width rules listed below):
- Base font: `13pt`
- Nav: `2.75rem` height, tabs centered; margin matches `#main` margin per page; `#nav.stuck` → `position: fixed; top: 0; left: 0; right: 0; margin: 0; background: #1e252d; z-index: 10000` with `0.25s` transition
- Content card: uses `margin: 0 Xrem` (no max-width — `main.css` `#nav` and `#main` had their hardcoded `width`/`max-width` removed so margins drive the layout)
- `about.html` margin: `0 5rem`; `label_input.html` / `flavor_input.html` margin: `0 1.5rem`
- `logs.html`: nav `position: fixed`, main `margin-top: 2.75rem` (no intro, `overflow: hidden` on `#wrapper` breaks CSS sticky)
- Intro: `100vh` (required for scroll trigger), title centered vertically at `4rem`
- Dropdowns: `max-width: 22rem` on `label_input.html` and `flavor_input.html`
- Alcohol % input: `width: 5rem`
- Header paragraphs: `max-width: 30rem` on `about.html`; `26rem` on `label_input.html`; `23rem` on `flavor_input.html`
- About hero image: `max-width: 55%; display: block; margin: 0 auto`

**Images directory layout** (`frontend/images/`):
- `backgrounds/` — `bg.jpg`, `overlay.png`, `pic02.jpg`–`pic09.jpg` (parallax/background images used by `main.css`)
- `extra/` — `pic01.jpg` (wine glass pouring photo shown in `about.html`); `icon.jpg` (site favicon, used on all pages)
- `grapes/` — per-grape images, all filenames normalized to **lowercase kebab-case** (e.g. `cabernet-sauvignon.jpg`, `gruner-veltliner.jpg`). Mixed `.jpg`/`.png` extensions. Not all 144 DB varieties have an image; being filled in progressively.

**Grape images on results page:** `results.html` renders a 90×110px image column on each result card.
- `grapeSlug(name)` — JS function: NFD normalize → strip accents → lowercase → replace non-alphanumeric runs with hyphens.
- `SLUG_OVERRIDES` — JS map for edge cases: `"nero d avola" → "nero-davola"` (apostrophe in "Nero d'Avola" would otherwise produce `nero-d-avola`).
- Fallback chain: tries `images/grapes/{slug}.jpg` → on error tries `.png` → if that also fails, hides the `<img>` and shows a "No image available." placeholder div of the same size (gray background).

**Sticky nav** (`frontend/assets/js/nav-sticky.js`): shared script loaded on all three intro pages. Inserts a placeholder `div` before the nav, measures `navTop` on `load` (after stripping any premature stuck class), then on `scroll` toggles `#nav.stuck` when `scrollY >= navTop`. Initializes `navTop = Infinity` to prevent a race condition on page refresh where a browser-restored scroll event fires before `load` and locks the nav stuck permanently.

**Server wakeup banner**: both form pages show a yellow "Waking up the server…" banner after 4 seconds if the API hasn't responded (Render Free cold-start). Cleared as soon as `loadWineTypes` resolves.

**API docs endpoint**: `GET /api/docs` returns structured JSON documentation of all 7 endpoints.

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
│   └── api.py             # Flask REST API (7 endpoints incl. /api/docs, logs every request to DB)
├── data/
│   ├── BlindTaste_Varietal_Wines.xlsx   # Curated wine dataset
│   └── blindtaste.db                   # SQLite database (committed to repo)
├── frontend/
│   ├── about.html         # Landing page
│   ├── label_input.html   # Label Input form
│   ├── flavor_input.html  # Flavor Profile Input form
│   ├── results.html       # Results page (reads localStorage, renders top-5 cards with grape images)
│   ├── logs.html          # Logs page
│   ├── assets/
│   │   ├── css/           # main.css, fontawesome
│   │   ├── js/            # main.js, nav-sticky.js, label.js, flavor.js, util.js, etc.
│   │   ├── sass/          # Source SCSS (not compiled at runtime)
│   │   └── webfonts/      # FontAwesome webfonts
│   └── images/
│       ├── backgrounds/   # bg.jpg, overlay.png, pic02–pic09.jpg
│       ├── extra/         # pic01.jpg (wine glass photo)
│       └── grapes/        # Per-grape images (kebab-case, progressively filled)
├── index.html             # Root redirect → frontend/about.html (for GitHub Pages)
├── Procfile               # Render start command: gunicorn --chdir backend api:app
├── requirements.txt       # flask, flask-cors, sqlalchemy, pandas, openpyxl, gunicorn
├── README.md              # Public project documentation
└── context.md             # This file
```

---

## 12. Setup & Run (Local Development)

```powershell
# Activate venv (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install dependencies (one-time)
pip install -r requirements.txt

# Create empty tables (uses absolute path internally — can be run from anywhere)
python backend/create_db.py

# Populate grape_standard (re-runnable, idempotent)
python backend/populate_db.py

# Start the API (runs on http://localhost:5000)
cd backend
python api.py
```

**Note:** the frontend is served separately (e.g. VS Code Live Server on port 5500) when running locally. The API must be running on port 5000 for the forms to load dropdowns and submit recommendations. **In local development, remember to temporarily swap `API_BASE` in the HTML files from the Render URL back to `http://localhost:5000`.**

---

## 13. Open Questions / Next Steps

1. ~~Finalize Flavor Profile Input fields.~~ ✓
2. ~~Confirm cross-cutting algorithm decisions (§9.3).~~ ✓
3. ~~Implement the recommendation algorithm.~~ ✓ (`backend/recommender.py`)
4. ~~Build an HTTP API (Flask) to expose the recommender to the frontend.~~ ✓ (`backend/api.py`)
5. ~~Rework the frontend forms to match the finalized input schema.~~ ✓ (`label_input.html`, `flavor_input.html`)
6. ~~Build a results page (`frontend/results.html`).~~ ✓
7. ~~Wire `Log` and `RecommendationResult` persistence into the API flow.~~ ✓
8. ~~Build admin logs page.~~ ✓ (`logs.html`)
9. ~~Deploy to production.~~ ✓ (see §14)
10. ~~Decide how to use grape images in `images/grapes/`.~~ ✓ (slug function + fallback chain on `results.html`)
11. ~~Write hand-written descriptions for all 144 grape entries.~~ ✓ (loaded via `load_descriptions.py`)
12. ~~Add ABV level selector (Very Low → Very High) to Flavor Profile Input.~~ ✓ (see §9.2)
13. Fill in remaining grape images in `images/grapes/` — in progress.
14. Write thesis document (introduction, framework, design, implementation, results, conclusions).

---

## 14. Deployment

**Production status:** live as of 2026-05-12.

**Frontend:** GitHub Pages
- Source: `main` branch, `/` (root)
- Root `index.html` redirects to `frontend/about.html`
- URL: `https://kennethortizpr.github.io/blindtaste/`

**Backend:** Render — Free tier Web Service
- Runtime: Python 3
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --chdir backend api:app`
- Instance type: Free
- URL: `https://blindtaste.onrender.com`

**Deployment workflow:**
- `git push` to the `main` branch on GitHub triggers:
  - GitHub Pages rebuild (within ~30 seconds)
  - Render auto-redeploy (within ~3 minutes)

**Key files for deployment:**
- `Procfile` — tells Render how to start the app
- `requirements.txt` — includes `gunicorn` for the production server
- `data/blindtaste.db` — DB file is committed so Render uses it directly without running `populate_db.py` on each cold start
- `index.html` — root redirect for clean URLs on GitHub Pages
- `api.py` end-of-file binds to `0.0.0.0:$PORT` (Render assigns the port via environment variable)

**Caveats of Render Free tier:**
- Server sleeps after 15 min of inactivity. First request after sleep takes ~30s (cold start). Both form pages show a yellow wakeup banner after 4s to communicate this to the user.
- No persistent disk: any data written at runtime (new rows in `log` and `recommendation_result`) survives until the next redeploy, then resets. For thesis demo this is acceptable; `grape_standard` always comes back fresh because the `.db` is in the repo.

**CORS:** `api.py` uses `CORS(app)` (permissive) — required so the GitHub Pages frontend (different origin) can call the Render API.

---

*Last updated: 2026-05-13 (session 7 — favicon added to all pages, Flavor ABV Very High value corrected to 15.0, API_BASE note updated to reference label.js/flavor.js, header paragraph widths corrected per page).*
