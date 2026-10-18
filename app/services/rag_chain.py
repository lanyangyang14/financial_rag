from app.services.vector_store import vector_store
from app.services.llm_client import get_llm_client
from typing import AsyncGenerator


class RAGChain:
    def __init__(self):
        self.llm = get_llm_client("deepseek")  # 使用 DeepSeek 做主力生成

    async def generate_answer(self, query: str) -> AsyncGenerator[str, None]:
        """检索并流式生成回答"""

        # 1. 检索
        retrieved_docs = await vector_store.search(query, top_k=3)

        if not retrieved_docs:
            yield "在财报库中没有找到相关内容。"
            return

        # 2. 组装上下文（把父块拼起来，带上页码）
        context_str = ""
        for i, doc in enumerate(retrieved_docs):
            context_str += f"【第 {doc['page']} 页内容】\n{doc['parent_content']}\n\n"

        # 3. 构造 Prompt
        prompt = f"""你是一个专业的财报分析师。请根据以下提供的财报信息，准确回答用户的问题。
如果信息中找不到答案，请直接说“根据提供的财报片段，无法回答该问题”，绝不要编造数据。
在回答时，请尽量在句末标注数据来源的页码（例如：[第3页]）。

【财报信息】：
{context_str}

【用户问题】：
{query}
"""

        # 4. 流式输出
        async for chunk in self.llm.chat_stream(prompt):
            yield chunk


# 全局实例
rag_chain = RAGChain()