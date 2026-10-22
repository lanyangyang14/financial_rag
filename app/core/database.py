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
    settings.POSTGRES_URL,
    pool_size=10,          # 平时保持 10 个常驻连接
    max_overflow=20,       # 高峰期最多再额外借 20 个（总共 30 个）
    pool_timeout=30,       # 借不到连接最多等 30 秒（超时直接抛错，保护数据库）
    pool_pre_ping=True,    # 每次拿连接前 ping 一下，防止拿到断开的死连接
    pool_recycle=1800      # 连接存活 30 分钟后强制回收（防止被 PG 强行断开）
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