# app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.db_models import Base

# 🌟 终极形态：加上 ?sslmode=disable
DATABASE_URL = "postgresql+psycopg2://admin:adminpassword@127.0.0.1:5434/financial_rag?sslmode=disable&client_encoding=utf8"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)