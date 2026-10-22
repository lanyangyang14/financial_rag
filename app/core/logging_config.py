import sys
import os
import logging
from loguru import logger
from app.core.contexts import trace_id, user_id

class InterceptHandler(logging.Handler):
    """拦截标准 logging 并转发给 Loguru"""
    def emit(self, record: logging.LogRecord):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

def setup_logging():
    """初始化企业级日志"""
    # 1. 移除默认的 handler
    logger.remove()

    # 2. 定义输出格式（包含 trace_id 和 user_id）
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<yellow>trace_id={extra[trace_id]}</yellow> | "
        "<magenta>user={extra[user_id]}</magenta> | "
        "<level>{message}</level>"
    )

    # 3. 控制台输出
    logger.add(
        sys.stdout,
        format=log_format,
        level="INFO",
        filter=lambda record: _inject_context(record)
    )

    # 4. 文件输出（按天轮转，保留 7 天）
    os.makedirs("logs", exist_ok=True)
    logger.add(
        "logs/app.log",
        format=log_format,
        level="INFO",
        rotation="20 MB",
        retention="7 days",
        encoding="utf-8",
        filter=lambda record: _inject_context(record)
    )

    # 5. 接管 Uvicorn 和 FastAPI 的标准日志
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for _log in ["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"]:
        _logger = logging.getLogger(_log)
        _logger.handlers = [InterceptHandler()]

def _inject_context(record):
    """往日志记录里注入 trace_id 和 user_id"""
    record["extra"]["trace_id"] = trace_id.get() or "-"
    record["extra"]["user_id"] = user_id.get() or "-"
    return True