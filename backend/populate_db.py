# backend/populate_db.py — Reads the curated XWines Excel file and populates grape_standard with 144 centroids.
import ast
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import GrapeStandard


# --- Config ---

BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR.parent / 'data' / 'BlindTaste_Varietal_Wines.xlsx'
DB_PATH = BASE_DIR.parent / 'data' / 'blindtaste.db'

TYPE_NAMES = {"Dessert/Port": "Dessert Port"}
SHEET_NAME = 'Varietal Wines'
MIN_WINES_PER_GROUP = 50



# --- Label Helpers ---

def parse_pairings(cell):
    try:
        result = ast.literal_eval(cell)
        return result if isinstance(result, list) else []
    except (ValueError, SyntaxError):
        return []


def body_label(avg_body):
    if avg_body < 1.5:
        return "very light-bodied"
    if avg_body < 2.5:
        return "light-bodied"
    if avg_body < 3.5:
        return "medium-bodied"
    if avg_body < 4.5:
        return "full-bodied"
    return "very full-bodied"


def acidity_label(avg_acidity):
    if avg_acidity < 1.67:
        return "low acidity"
    if avg_acidity < 2.33:
        return "medium acidity"
    return "high acidity"


def alcohol_label(avg_alcohol):
    if avg_alcohol < 11:
        return "low alcohol content"
    if avg_alcohol < 13:
        return "moderate alcohol content"
    if avg_alcohol < 14:
        return "medium-high alcohol content"
    return "high alcohol content"


def build_description(grape, wine_type, avg_alcohol, avg_body, avg_acidity):
    return (
        f"{grape} ({wine_type}) — A {body_label(avg_body)} wine with "
        f"{acidity_label(avg_acidity)} and {alcohol_label(avg_alcohol)} "
        f"(~{avg_alcohol:.1f}% ABV)."
    )


# --- Main ---

def main():
    print(f"Reading wines from: {EXCEL_PATH}")
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(f"Excel file not found at {EXCEL_PATH}")

    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
    print(f"  Loaded {len(df)} varietal wines")

    df['Type'] = df['Type'].replace(TYPE_NAMES)
    df['pairings_parsed'] = df['Food_Pairings'].apply(parse_pairings)

    engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Wipe existing rows so re-running produces identical state.
    deleted = session.query(GrapeStandard).delete()
    session.commit()
    if deleted:
        print(f"  Cleared {deleted} existing rows from grape_standard")

    inserted = 0
    skipped = 0

    for (grape, wine_type), group in df.groupby(['Grape', 'Type']):
        n_wines = len(group)

        if n_wines < MIN_WINES_PER_GROUP:
            skipped += 1
            continue

        avg_alcohol = round(group['ABV'].mean(), 2)
        avg_body    = round(group['Body_Numeric'].mean(), 2)
        avg_acidity = round(group['Acidity_Numeric'].mean(), 2)

        unique_pairings = set()
        for plist in group['pairings_parsed']:
            unique_pairings.update(plist)
        food_pairings_str = ', '.join(sorted(unique_pairings))

        description = build_description(
            grape, wine_type, avg_alcohol, avg_body, avg_acidity
        )

        entry = GrapeStandard(
            grape_name=grape,
            wine_type=wine_type,
            avg_alcohol=avg_alcohol,
            avg_acidity=avg_acidity,
            avg_body=avg_body,
            food_pairings=food_pairings_str,
            description=description,
        )
        session.add(entry)
        inserted += 1

    session.commit()
    session.close()

    total_groups = inserted + skipped
    print(f"\nDone.")
    print(f"  Total (grape, type) groups found: {total_groups}")
    print(f"  Inserted into grape_standard:     {inserted}")
    print(f"  Skipped (fewer than {MIN_WINES_PER_GROUP} wines):      {skipped}")

if __name__ == '__main__':
    main()