import json
import redis.asyncio as aioredis
from app.core.config import settings


class ChatMemory:
    def __init__(self):
        # 使用异步 Redis 客户端连接
        self.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        self.max_history = 10  # 最多保留最近5轮（10条消息）

    async def add_message(self, session_id: str, role: str, content: str):
        """保存一条消息到 Redis"""
        key = f"chat_history:{session_id}"
        message = json.dumps({"role": role, "content": content}, ensure_ascii=False)

        # 推入列表
        await self.redis.rpush(key, message)
        # 裁剪，只保留最近 N 条，并设置 1 天过期
        await self.redis.ltrim(key, -self.max_history, -1)
        await self.redis.expire(key, 86400)

    async def get_history(self, session_id: str) -> list[dict]:
        """获取历史对话"""
        key = f"chat_history:{session_id}"
        history = await self.redis.lrange(key, 0, -1)
        return [json.loads(msg) for msg in history]

    async def get_history_text(self, session_id: str) -> str:
        """获取拼接成纯文本的历史对话（用于 Prompt）"""
        history = await self.get_history(session_id)
        if not history:
            return ""

        text = "以下是之前的对话历史：\n"
        for msg in history:
            role_name = "用户" if msg["role"] == "user" else "助手"
            text += f"{role_name}: {msg['content']}\n"
        return text


# 全局实例
chat_memory = ChatMemory()