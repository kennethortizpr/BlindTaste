# backend/models.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class GrapeStandard(Base):  
    __tablename__ = 'grape_standard'
    id_pk = Column(Integer, primary_key=True)
    grape_name = Column(String, nullable=False)
    wine_type = Column(String, nullable=False) 
    avg_alcohol = Column(Float, nullable=False)
    avg_acidity = Column(Float, nullable=False)
    avg_body = Column(Float, nullable=False)
    food_pairings = Column(String, nullable=False)
    description = Column(String)
    __table_args__ = (
        UniqueConstraint('grape_name', 'wine_type', name='uq_grape_type'),
    )

class Log(Base):
    __tablename__ = 'log'
    id_pk = Column(Integer, primary_key=True)
    timestamp = Column(String, nullable=False)
    input_mode = Column(String, nullable=False)
    user_input = Column(String, nullable=False)

class RecommendationResult(Base):
    __tablename__ = 'recommendation_result'
    log_id_pk_fk1 = Column(Integer, ForeignKey('log.id_pk'), primary_key=True)
    grape_id_pk_fk2 = Column(Integer, ForeignKey('grape_standard.id_pk'), primary_key=True)
    similarity_percentage = Column(Float)
    rank_order = Column(Integer)
    
