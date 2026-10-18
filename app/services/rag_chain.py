import json

from app.services.vector_store import vector_store
from app.services.llm_client import get_llm_client
from app.services.memory import chat_memory
from typing import AsyncGenerator


class RAGChain:
    def __init__(self):
        self.llm = get_llm_client("deepseek")

    async def rewrite_query(self, query: str, history_text: str) -> str:
        """查询改写：如果用户用了代词，结合历史改写为完整的独立问题"""
        if not history_text:
            return query

        prompt = f"""你是一个查询改写助手。请根据历史对话，将用户的最新提问改写为一个不需要上下文也能看懂的完整问题。
如果最新提问已经很完整，直接返回原句。只输出改写后的句子，不要任何解释。

{history_text}

最新提问：{query}
改写后："""
        # 这里为了速度，我们直接用普通的生成，不用流式
        # 临时用一下底层接口
        response = await self.llm.client.chat.completions.create(
            model=self.llm.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        rewritten = response.choices[0].message.content.strip()
        print(f"🔄 查询改写: [{query}] -> [{rewritten}]")
        return rewritten

    async def generate_answer(self, query: str, session_id: str) -> AsyncGenerator[str, None]:
        history_text = await chat_memory.get_history_text(session_id)
        rewritten_query = await self.rewrite_query(query, history_text)

        retrieved_docs = await vector_store.search(rewritten_query, top_k=3)

        if not retrieved_docs:
            yield "在财报库中没有找到相关内容。"
            return

        context_str = ""
        sources_data = []  # 👈 用于收集引用元数据

        for i, doc in enumerate(retrieved_docs):
            context_str += f"【第 {doc['page']} 页内容】\n{doc['parent_content']}\n\n"
            # 收集元数据，去重（防止同一页被多次召回）
            if not any(s['page'] == doc['page'] for s in sources_data):
                sources_data.append({
                    "page": doc["page"],
                    "content": doc["parent_content"].strip()[:500] + "..."  # 截取前500字展示
                })

        prompt = f"""你是一个极其专业的财务分析师。请严格根据提供的财报片段回答用户问题。
    注意：
    1. 如果片段中找不到答案，直接说“根据现有财报片段，无法回答该问题”。
    2. 不要自己编造数字。
    3. 必须在回答的结尾标注数据来源的页码（如：[第{retrieved_docs[0]['page']}页]）。

    【财报信息】：
    {context_str}

    【历史对话】：
    {history_text}

    【用户问题】：
    {query}
    """

        full_answer = ""
        async for chunk in self.llm.chat_stream(prompt):
            full_answer += chunk
            yield chunk

        # 🌟 核心：流式输出结束后，发送一段特殊标记的元数据
        # 前端通过识别这个标记，来渲染底部的“参考来源”面板
        meta_packet = json.dumps({"sources": sources_data}, ensure_ascii=False)
        yield f"\n\n<<<SOURCES_METADATA>>>{meta_packet}<<<END_METADATA>>>"

        # 存入 Redis 时，去掉元数据部分，只存纯文本回答
        await chat_memory.add_message(session_id, "user", query)
        await chat_memory.add_message(session_id, "assistant", full_answer)

rag_chain = RAGChain()