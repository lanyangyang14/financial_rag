import json
import redis.asyncio as aioredis
import asyncio
import tiktoken
from datetime import datetime

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.db_models import ChatHistory, SessionSummary, UserProfile, AgentExperience
from app.services.llm_client import get_llm_client


class CognitiveMemory:
    def __init__(self):
        self.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        self.max_working_memory = 6  # 工作记忆：最近 6 条对话
        # 🌟 引入 Token 计算器
        self.enc = tiktoken.get_encoding("cl100k_base")
        self.max_token_threshold = 2000  # 超过 2000 Token 触发摘要

    def get_procedural_experience(self, user_query: str) -> str:
        """检索程序性记忆：从错题本中提取教训"""
        db = SessionLocal()
        try:
            logs = db.query(AgentExperience).order_by(AgentExperience.created_at.desc()).limit(3).all()
            if not logs:
                return ""
            exp_text = "【过往工具调用踩坑经验】\n"
            for log in logs:
                exp_text += f"- 调用 {log.tool_name} 时传入 {log.input_args} 会导致报错。错误信息: {log.error_message}。请避免使用相同参数。\n"
            return exp_text
        finally:
            db.close()

    async def add_message(self, user_id: str, session_id: str, role: str, content: str):
        """将对话写入情景记忆（Redis + PG）"""
        key = f"chat_history:{user_id}:{session_id}"
        message = json.dumps({"role": role, "content": content}, ensure_ascii=False)

        # 1. 写 Redis（情景记忆-短时）
        await self.redis.rpush(key, message)
        await self.redis.ltrim(key, -self.max_working_memory, -1)
        await self.redis.expire(key, 86400)

        # 2. 核心改造：不再同步写 PG，而是推入 Redis 的异步写队列（削峰）
        queue_data = {
            "user_id": user_id,
            "session_id": session_id,
            "role": role,
            "content": content
        }
        await self.redis.rpush("memory_write_queue", json.dumps(queue_data, ensure_ascii=False))
        print(f"📥 [削峰队列] 消息已推入 Redis 队列，等待后台异步落库")

        # 3. 动态 Token 预算：计算当前近期对话总长度，触发摘要
        try:
            recent_msgs = await self.redis.lrange(key, 0, -1)
            recent_text = "\n".join([json.loads(m)["content"] for m in recent_msgs])
            token_count = len(self.enc.encode(recent_text))

            if token_count > self.max_token_threshold:
                print(f"⏳ [Context 管理] 触发中期记忆压缩 (当前 {token_count} tokens)...")
                import threading
                # 启动异步线程处理摘要，不阻塞主流程
                threading.Thread(target=self._generate_summary_sync, args=(user_id, session_id)).start()
        except Exception as e:
            print(f"⚠️ Token 计算或摘要触发失败: {e}")

        # 4. 如果用户发言，触发画像提取与向量化（按需召回）
        if role == "user" and len(content) > 5:
            # 4.1 异步提取画像
            asyncio.create_task(self._extract_semantic_memory(user_id, content))

            # 4.2 存入向量库，供日后“按需召回”
            try:
                from app.services.vector_store import vector_store
                history_chunk = [{
                    "child_content": content,
                    "parent_content": content,
                    "metadata": {
                        "page": 0,
                        "source": "chat_history",
                        "user_id": user_id,
                        "session_id": session_id
                    }
                }]
                await vector_store.insert_chunks(history_chunk, document_id=f"history_{session_id}", user_id=user_id,
                                                 chunk_type="history")
                print(f"📝 [按需召回库] 已将用户历史存入向量库")
            except Exception as e:
                print(f"⚠️ 存入历史向量库失败: {e}")

    def _generate_summary_sync(self, user_id: str, session_id: str):
        """同步生成历史摘要（运行在子线程中）"""
        print(f"⏳ [Context 管理] 正在生成摘要...")
        db = SessionLocal()
        try:
            # 取该会话所有的历史（包括刚刚异步落库的）
            histories = db.query(ChatHistory).filter(
                ChatHistory.user_id == user_id,
                ChatHistory.session_id == session_id
            ).order_by(ChatHistory.created_at.asc()).all()

            if not histories: return
            history_text = "\n".join([f"{h.role}: {h.content}" for h in histories])

            llm = get_llm_client("deepseek")
            resp = asyncio.run(llm.client.chat.completions.create(
                model=llm.model,
                messages=[{"role": "user",
                           "content": f"请将以下财务对话历史压缩成一段极其精炼的摘要，保留用户的身份信息、关注的核心指标和关键结论：\n\n{history_text}"}],
                temperature=0.1
            ))
            summary = resp.choices[0].message.content.strip()

            existing = db.query(SessionSummary).filter(SessionSummary.session_id == session_id).first()
            if existing:
                existing.summary_text = summary
            else:
                db.add(SessionSummary(user_id=user_id, session_id=session_id, summary_text=summary))
            db.commit()
            print(f"✅ [Context 管理] 摘要更新成功: {summary[:50]}...")
        except Exception as e:
            print(f"❌ [Context 管理] 摘要生成失败: {e}")
        finally:
            db.close()

    async def _extract_semantic_memory(self, user_id: str, content: str):
        """从用户的话中提取长期事实，存入 PG（带时序冲突解决）"""
        if len(content) < 10: return

        llm = get_llm_client("deepseek")
        prompt = f"""请从用户的话中提取关于用户的长期事实，输出严格的 JSON 格式：{{"职业": "...", "关注领域": "..."}}。如果没有事实，输出 {{}}。
用户说：{content}"""

        try:
            res = await llm.client.chat.completions.create(
                model=llm.model, messages=[{"role": "user", "content": prompt}], temperature=0.1
            )
            facts = json.loads(res.choices[0].message.content.strip())

            db = SessionLocal()
            try:
                for key, val in facts.items():
                    existing = db.query(UserProfile).filter(
                        UserProfile.user_id == user_id,
                        UserProfile.fact_key == key
                    ).first()

                    if existing:
                        # 🌟 解决冲突：如果值变了，直接覆盖并更新时间
                        if existing.fact_value != val:
                            print(f"🔄 [语义记忆更新] 用户 {user_id} 的 {key} 从 '{existing.fact_value}' 变更为 '{val}'")
                            existing.fact_value = val
                            existing.updated_at = datetime.utcnow()
                    else:
                        db.add(UserProfile(user_id=user_id, fact_key=key, fact_value=val))
                db.commit()
            finally:
                db.close()
            if facts:
                print(f"🧠 [语义记忆] 提取成功: {facts}")
        except Exception as e:
            print(f"⚠️ [语义记忆] 提取失败: {e}")

    async def get_memory_context(self, user_id: str, session_id: str) -> dict:
        """按照图 3 的漏斗，逐层拉取上下文"""
        memory_data = {"profile": "", "summary": "", "working": ""}

        # 1. 尝试获取缓存
        cache_key = f"memory_cache:{user_id}:{session_id}"
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        db = SessionLocal()
        try:
            # 2. 获取长期画像
            profiles = db.query(UserProfile).filter(UserProfile.user_id == user_id).all()
            if profiles:
                profile_str = "【用户最新画像】\n"
                for p in profiles:
                    # 🌟 加上更新时间，帮助大模型判断时效性
                    update_time = p.updated_at.strftime('%Y-%m-%d') if p.updated_at else "未知"
                    profile_str += f"- {p.fact_key}: {p.fact_value} (更新于: {update_time})\n"
                memory_data["profile"] = profile_str

            # 3. 获取中期摘要
            summary = db.query(SessionSummary).filter(SessionSummary.session_id == session_id).first()
            if summary:
                memory_data["summary"] = f"【历史摘要】\n{summary.summary_text}\n"
        finally:
            db.close()

        # 4. 获取短期 Redis
        key = f"chat_history:{user_id}:{session_id}"
        short_term = await self.redis.lrange(key, 0, -1)
        if short_term:
            working_str = "【近期对话】\n"
            for msg_str in short_term:
                msg = json.loads(msg_str)
                role_name = "用户" if msg["role"] == "user" else "助手"
                working_str += f"{role_name}: {msg['content']}\n"
            memory_data["working"] = working_str

        # 5. 写回缓存
        await self.redis.setex(cache_key, 300, json.dumps(memory_data, ensure_ascii=False))
        return memory_data


cognitive_memory = CognitiveMemory()