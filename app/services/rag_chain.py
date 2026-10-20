import json
import os
import re
from typing import AsyncGenerator

# 🌟 适配本地 Langfuse v2 服务端：observe/langfuse_context 在 langfuse.decorators 下
# （v2 没有 get_client，那是 v3+ 的 API，装了 v2 SDK 会 ImportError）
from langfuse.decorators import observe, langfuse_context
from langfuse import Langfuse

from app.services.reranker import reranker_service
from app.services.vector_store import vector_store
from app.services.es_search import ESSearchService
from app.services.graph_service import graph_service
from app.services.fusion import reciprocal_rank_fusion
from app.services.llm_client import get_llm_client
from app.services.memory import chat_memory

# 初始化 Langfuse（密钥你可以在 Langfuse 网页端获取并替换）
langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-1234567890"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-1234567890"),
    host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
)

# 提前设置 HuggingFace 镜像，避免模型下载超时
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


class RAGChain:
    def __init__(self):
        self.llm = get_llm_client("deepseek")

    async def rewrite_query(self, query: str, history_text: str) -> str:
        """多轮对话查询改写"""
        if not history_text:
            return query
        prompt = f"""你是一个查询改写助手。请根据历史对话，将用户的最新提问改写为一个不需要上下文也能看懂的完整问题。
如果提问已经很完整，直接返回原句。只输出改写后的句子，不要任何解释。

{history_text}
最新提问：{query}
改写后："""
        try:
            response = await self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return query

    # 🌟 核心修复：装饰器下面不能有空行，必须紧贴函数
    @observe(name="RAG_Answer_Generator")
    async def generate_answer(self, query: str, session_id: str,user_id:str) -> AsyncGenerator[str, None]:
        # 🌟 v2 写法：往当前 trace 上挂 metadata
        # 🌟 v2 写法：langfuse_context 挂 metadata 到当前 trace
        langfuse_context.update_current_trace(metadata={"session_id": session_id, "user_id": user_id})

        # 1. 获取历史与查询改写
        history_text = await chat_memory.get_history_text(session_id, user_id)
        rewritten_query = await self.rewrite_query(query, history_text)
        if rewritten_query != query:
            print(f"🔄 查询改写: [{query}] -> [{rewritten_query}]")

        print("--- 🚀 开始三路检索 ---")

        # 第一路
        vector_docs = await vector_store.search(rewritten_query,user_id,top_k=5)
        print(f"📡 [Qdrant] 向量检索找到 {len(vector_docs)} 条相关片段")

        # 第二路
        es_service = ESSearchService()
        es_docs = await es_service.search(rewritten_query,user_id,top_k=5)
        print(f"🔍 [Elasticsearch] 关键词检索找到 {len(es_docs)} 条相关片段")

        # 第三路
        graph_context = ""
        try:
            graph_context = graph_service.graph_search(rewritten_query)
            print(f"🕸️ [Neo4j] 图谱检索找到 {len(graph_context)} 个字符的上下文")
        except Exception as e:
            print(f"⚠️ 图谱检索跳过: {e}")

        print("--- 🧬 开始 RRF 融合 ---")

        # 如果包含 3 个以上数字，或者长度很短，判定为精确查询
        is_precision_query = len(re.findall(r'\d+', rewritten_query)) >= 3 or len(rewritten_query) < 10

        if is_precision_query:
            print("⚖️ 识别为精确查询，提高 Elasticsearch 权重")
            weights = [0.5, 1.5]  # ES 权重大
        else:
            print("⚖️ 识别为语义查询，提高 Qdrant 权重")
            weights = [1.5, 0.5]  # Qdrant 权重大

        # 5. RRF 融合（传入动态权重）
        fused_docs = reciprocal_rank_fusion([vector_docs, es_docs], weights=weights)
        # 截取 RRF 融合后的前 10 名，交给 Reranker 重新打分
        candidates = fused_docs[:10]
        print(f"🔄 准备重排的候选集大小: {len(candidates)}")

        # 🌟 核心：调用本地模型重排，直接取前 3 名
        top_docs = reranker_service.rerank(query=rewritten_query, docs=candidates, top_k=3)

        # 6. 组装上下文与溯源数据
        context_str = ""
        sources_data = []

        for doc in top_docs:
            page = doc.get('page', '未知')
            content = doc.get('parent_content', '')
            context_str += f"【第 {page} 页内容】\n{content}\n\n"

            # 去重溯源信息
            if not any(s['page'] == page for s in sources_data):
                sources_data.append({
                    "page": page,
                    "content": content.strip()[:500] + "..."
                })

        if graph_context:
            context_str += f"【知识图谱关联信息】\n{graph_context}\n\n"

        # 7. 终极 Prompt 组装
        prompt = f"""你是一个极其专业的财务分析师。请严格根据提供的财报片段和图谱信息回答用户问题。
注意：
1. 如果片段中找不到答案，直接说“根据现有财报片段，无法回答该问题”。
2. 绝不要编造数据。
3. 必须在回答的结尾标注数据来源的页码（如：[第6页]）。

【财报及图谱信息】：
{context_str}

【历史对话】：
{history_text}

【用户问题】：
{query}
"""

        # 8. 流式输出
        full_answer = ""
        async for chunk in self.llm.chat_stream(prompt):
            full_answer += chunk
            yield chunk

        # 9. 推送溯源元数据给前端
        meta_packet = json.dumps({"sources": sources_data}, ensure_ascii=False)
        yield f"\n\n<<<SOURCES_METADATA>>>{meta_packet}<<<END_METADATA>>>"

        # 10. 存入记忆 (Redis 和 SQLite/PG)
        await chat_memory.add_message(user_id,session_id, "user", query)
        await chat_memory.add_message(user_id,session_id, "assistant", full_answer)


rag_chain = RAGChain()