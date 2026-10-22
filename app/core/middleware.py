import asyncio
import re
import time
from uuid import uuid4
from fastapi.responses import JSONResponse
from loguru import logger
from app.core.contexts import trace_id as trace_id_var, user_id as user_id_var


class TraceIDMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. 解析或生成 Trace ID
        headers = dict(scope.get("headers", []))
        candidate = headers.get(b"x-trace-id", b"").decode("latin1")
        trace_id = candidate if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else uuid4().hex

        # 2. 注入到 ContextVars
        trace_id_var.set(trace_id)

        # 3. 记录状态
        started = time.monotonic()
        status = 500
        response_started = False
        completed = False
        disconnected = False

        # 拦截发送的响应头，强行塞入 X-Trace-ID
        async def send_wrapper(message):
            nonlocal status, response_started, completed
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                message["headers"] = [
                                         (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-trace-id"
                                     ] + [(b"x-trace-id", trace_id.encode())]

            await send(message)

            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True

        # 拦截接收的请求，检测是否断开
        async def receive_wrapper():
            nonlocal disconnected
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnected = True
            return message

        # 开始记录耗时
        logger.info(f"请求开始 method={scope['method']} path={scope['path']}")

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except asyncio.CancelledError:
            disconnected = True
            raise
        except Exception:
            if disconnected:
                raise
            logger.exception("请求处理异常")
            if not response_started:
                response = JSONResponse(status_code=500, content={"error": "系统内部错误"})
                await response(scope, receive_wrapper, send_wrapper)
        finally:
            duration = round((time.monotonic() - started) * 1000)
            if disconnected:
                logger.warning(f"请求取消 (客户端断开) path={scope['path']} duration={duration}ms")
            elif completed:
                logger.info(f"请求完成 path={scope['path']} status={status} duration={duration}ms")
            else:
                logger.error(f"请求失败 path={scope['path']} duration={duration}ms")

            # 清理上下文
            trace_id_var.set(None)
            user_id_var.set(None)