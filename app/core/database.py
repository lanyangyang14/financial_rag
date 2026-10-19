# app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.db_models import Base
from app.core.config import settings

# 🌟 从配置读取，兼容宿主机直连和容器内服务名
POSTGRES_URL = settings.POSTGRES_URL
# SQLAlchemy 需要指定 psycopg2 驱动
if POSTGRES_URL.startswith("postgresql://"):
    DATABASE_URL = POSTGRES_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    DATABASE_URL = POSTGRES_URL

# 补充连接参数
if "?" in DATABASE_URL:
    DATABASE_URL += "&sslmode=disable&client_encoding=utf8"
else:
    DATABASE_URL += "?sslmode=disable&client_encoding=utf8"

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