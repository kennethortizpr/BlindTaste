# backend/create_db.py
from pathlib import Path
from sqlalchemy import create_engine
from models import Base

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR.parent / 'data' / 'blindtaste.db'

engine = create_engine(f'sqlite:///{DB_PATH}', echo=True)
Base.metadata.create_all(engine)

print("New database tables created successfully!")