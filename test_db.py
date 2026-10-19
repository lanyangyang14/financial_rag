from app.core.database import SessionLocal
from sqlalchemy import text
from app.models.db_models import DocumentRecord, ChatHistory
from sqlalchemy import select


def test_conn():
    print("尝试连接 PG 数据库...")
    db = SessionLocal()
    try:
        # 1. 测试连接
        result = db.execute(text("SELECT version();"))
        version = result.scalar()
        print(f"✅ 连接成功！数据库版本: {version}")

        # 2. 查看建的表
        result = db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public';"))
        tables = result.scalars().all()
        print(f"📊 当前存在的表: {tables}")

        # 3. 如果表建好了，查一下刚才的记录（如果没有记录会返回空）
        if 'documents' in tables:
            docs = db.execute(select(DocumentRecord)).scalars().all()
            print(f"📄 文档记录数: {len(docs)}")

    except Exception as e:
        print(f"❌ 连接失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    test_conn()