from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.db_models import ChatHistory
import redis
import json
from app.core.config import settings

# 用同步 Redis 客户端
sync_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)


@celery_app.task(name="flush_memory_queue")
def flush_memory_queue():
    """定时任务：从 Redis 队列批量拉取数据，批量插入 PG"""
    # 一次最多捞 100 条
    items = sync_redis.lrange("memory_write_queue", 0, 99)
    if not items:
        return "队列为空"

    db = SessionLocal()
    try:
        records = []
        for item_str in items:
            data = json.loads(item_str)
            records.append(ChatHistory(
                user_id=data["user_id"],
                session_id=data["session_id"],
                role=data["role"],
                content=data["content"]
            ))

        # 🌟 核心：Bulk Insert（批量插入），只产生一次 SQL 交互
        db.bulk_save_objects(records)
        db.commit()

        # 清除已经入库的 Redis 数据
        sync_redis.ltrim("memory_write_queue", len(items), -1)
        print(f"✅ [批量落库] 成功将 {len(records)} 条对话写入 PostgreSQL")
        return f"成功处理 {len(records)} 条"
    except Exception as e:
        db.rollback()
        print(f"❌ [批量落库] 失败: {e}")
        return f"失败: {e}"
    finally:
        db.close()