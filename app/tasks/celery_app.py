from celery import Celery
from app.core.config import settings

# 创建 Celery 实例，使用 Redis 作为 Broker（消息队列）
celery_app = Celery(
    "financial_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.document_task", "app.tasks.db_flush_task"],  # 注册新文件
)

# 基础配置
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    # 🌟 核心新增：开启 Redis 优先级支持
    broker_transport_options={
        'priority_steps': list(range(10)), # 支持 0-9 的优先级（0 最高）
        'queue_order_strategy': 'priority',
    },
    # 让任务默认走优先级队列
    task_default_queue='default',
    beat_schedule={
        'flush-memory-every-second': {
            'task': 'flush_memory_queue',
            'schedule': 1.0,  # 每 1 秒执行一次
        },
    },
)

