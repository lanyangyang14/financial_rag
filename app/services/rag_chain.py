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
        """带有记忆的流式生成"""

        # 1. 获取历史记忆
        history_text = await chat_memory.get_history_text(session_id)

        # 2. 查询改写
        rewritten_query = await self.rewrite_query(query, history_text)

        # 3. 用改写后的 Query 去检索
        retrieved_docs = await vector_store.search(rewritten_query, top_k=3)

        if not retrieved_docs:
            yield "在财报库中没有找到相关内容。"
            return

        # 4. 组装上下文
        context_str = ""
        for i, doc in enumerate(retrieved_docs):
            context_str += f"【第 {doc['page']} 页内容】\n{doc['parent_content']}\n\n"

        # 5. 构造 Prompt (注意：把历史记忆也放进去，让大模型懂上下文)
        prompt = f"""你是一个专业的财报分析师。请根据以下提供的财报信息，准确回答用户的问题。
如果信息中找不到答案，请直接说“根据提供的财报片段，无法回答该问题”，绝不要编造数据。
在回答时，请尽量在句末标注数据来源的页码（例如：[第3页]）。

{history_text}

【财报信息】：
{context_str}

【用户问题】：
{query}
"""

        # 6. 流式生成并收集完整回答
        full_answer = ""
        async for chunk in self.llm.chat_stream(prompt):
            full_answer += chunk
            yield chunk

        # 7. 对话结束后，把用户问题和AI回答存入 Redis
        await chat_memory.add_message(session_id, "user", query)
        await chat_memory.add_message(session_id, "assistant", full_answer)


rag_chain = RAGChain()