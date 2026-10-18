from celery import Celery
from app.core.config import settings

# 创建 Celery 实例，使用 Redis 作为 Broker（消息队列）
celery_app = Celery(
    "financial_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.document_task"] # 注册任务文件
)

# 基础配置
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
)