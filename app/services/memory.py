import json
import redis.asyncio as aioredis
from app.core.config import settings
from app.models.db_models import ChatHistory
from app.core.database import SessionLocal

class ChatMemory:
    def __init__(self):
        self.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        self.max_history = 10

    async def add_message(self, session_id: str, role: str, content: str):
        # 1. 存入 Redis
        key = f"chat_history:{session_id}"
        message = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        await self.redis.rpush(key, message)
        await self.redis.ltrim(key, -self.max_history, -1)
        await self.redis.expire(key, 86400)

        # 🌟 2. 永久存入 PostgreSQL (同步操作)
        db = SessionLocal()
        try:
            db.add(ChatHistory(session_id=session_id, role=role, content=content))
            db.commit()
        finally:
            db.close()  # 必须关闭连接

    async def get_history(self, session_id: str) -> list[dict]:
        # 我们依然从 Redis 读，因为快
        key = f"chat_history:{session_id}"
        history = await self.redis.lrange(key, 0, -1)
        return [json.loads(msg) for msg in history]

    async def get_history_text(self, session_id: str) -> str:
        history = await self.get_history(session_id)
        if not history: return ""
        text = "以下是之前的对话历史：\n"
        for msg in history:
            role_name = "用户" if msg["role"] == "user" else "助手"
            text += f"{role_name}: {msg['content']}\n"
        return text

chat_memory = ChatMemory()