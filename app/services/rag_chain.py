import json
import os
import re
from typing import AsyncGenerator
from langfuse import observe, get_client, propagate_attributes
from langfuse import Langfuse

from app.services.guardrails import guardrails
from app.services.reranker import reranker_service
from app.services.vector_store import vector_store
from app.services.es_search import ESSearchService
from app.services.graph_service import graph_service
from app.services.fusion import reciprocal_rank_fusion
from app.services.llm_client import get_llm_client
from app.services.memory import chat_memory
from app.services.query_router import router  # 🌟 引入极速路由器

langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-1234567890"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-1234567890"),
    host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
)

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


class RAGChain:
    def __init__(self):
        self.llm = get_llm_client("deepseek")
        self.es_service = ESSearchService()  # 初始化一次，复用实例

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

    @observe(name="RAG_Answer_Generator")
    async def generate_answer(self, query: str, session_id: str, user_id: str) -> AsyncGenerator[str, None]:
        # 🌟 第一关：输入安检
        is_safe, error_msg = await guardrails.check_input(query)
        if not is_safe:
            print(f"🚫 [安全拦截] {error_msg}")
            yield error_msg
            return  # 直接断开，不查数据库，不调大模型

        # 🌟 v4 写法：用 propagate_attributes 设置 session_id 和 user_id

        with propagate_attributes(
                session_id=session_id,
                user_id=user_id
        ):

            # 1. 获取历史与查询改写
            history_text = await chat_memory.get_history_text(session_id, user_id)
            rewritten_query = await self.rewrite_query(query, history_text)
            if rewritten_query != query:
                print(f"🔄 查询改写: [{query}] -> [{rewritten_query}]")

            # ================= 🌟 核心改造：智能路由分发 =================
            route_type = router.route(rewritten_query)
            print(f"🚦 [智能路由] 意图识别: [{route_type}] | 问题: {rewritten_query}")

            vector_docs = []
            es_docs = []
            graph_context = ""
            context_str = ""

            if route_type == "direct":
                print("⚡ 闲聊模式：跳过所有数据库检索")
                # context_str 保持为空，大模型会直接根据自身知识回答
            elif route_type == "macro_summary":
                print("🌍 宏观模式：仅检索全局摘要块")
                # 🌟 强制只检索 chunk_type="summary" 的数据
                vector_docs = await vector_store.search(rewritten_query, user_id=user_id, top_k=5, chunk_type="summary")

            elif route_type == "keyword":
                print("🎯 精确模式：仅查询 Elasticsearch")
                es_docs = await self.es_service.search(rewritten_query, user_id=user_id, top_k=5)

            elif route_type == "semantic":
                print("🧠 语义模式：仅查询 Qdrant")
                vector_docs = await vector_store.search(rewritten_query, user_id=user_id, top_k=5)

            elif route_type == "hybrid":
                print("🕸️ 复杂模式：三路并发检索 (Qdrant + ES + Neo4j)")
                vector_docs = await vector_store.search(rewritten_query, user_id=user_id, top_k=5)
                es_docs = await self.es_service.search(rewritten_query, user_id=user_id, top_k=5)
                try:
                    graph_context = graph_service.graph_search(rewritten_query)
                    print(f"🕸️ [Neo4j] 图谱检索找到 {len(graph_context)} 个字符的上下文")
                except Exception as e:
                    print(f"⚠️ 图谱检索跳过: {e}")

            # ================= 组装候选集与重排 =================
            candidates = []
            if vector_docs and es_docs:
                print("--- 🧬 开始 RRF 融合 ---")
                # 保留之前的动态权重逻辑
                is_precision_query = len(re.findall(r'\d+', rewritten_query)) >= 3 or len(rewritten_query) < 10
                weights = [0.5, 1.5] if is_precision_query else [1.5, 0.5]
                fused_docs = reciprocal_rank_fusion([vector_docs, es_docs], weights=weights)
                candidates = fused_docs[:10]
            elif vector_docs:
                candidates = vector_docs  # 纯语义模式，不需要融合
            elif es_docs:
                candidates = es_docs  # 纯精确模式，不需要融合

            top_docs = []
            if candidates:
                print(f"🔄 准备重排的候选集大小: {len(candidates)}")
                top_docs = reranker_service.rerank(query=rewritten_query, docs=candidates, top_k=3)
            else:
                print("⚠️ 没有检索到任何相关文档")

            # ================= 组装上下文 =================
            sources_data = []
            for doc in top_docs:
                page = doc.get('page', '未知')
                content = doc.get('parent_content', '')
                context_str += f"【第 {page} 页内容】\n{content}\n\n"

                if not any(s['page'] == page for s in sources_data):
                    sources_data.append({
                        "page": page,
                        "content": content.strip()[:500] + "..."
                    })

            if graph_context:
                context_str += f"【知识图谱关联信息】\n{graph_context}\n\n"

            # ================= 7. 终极 Prompt 组装 =================
            prompt = f"""你是一个极其专业的财务分析师。请严格根据提供的财报片段和图谱信息回答用户问题。
注意：
1. 如果片段中找不到答案，直接说“根据现有财报片段，无法回答该问题”。
2. 绝不要编造数据。
3. 必须在回答的结尾标注数据来源的页码（如：[第6页]）。
4. 如果【财报及图谱信息】为空（比如用户在闲聊），请用你自身的知识友好地回答。

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

            # 🌟 修改 2：获取脱敏后的安全回答
            safe_answer = guardrails.check_output(full_answer)
            if safe_answer != full_answer:
                yield f"\n\n⚠️ 注意：系统已对回答中的敏感隐私信息进行脱敏处理。"

            # 9. 推送溯源元数据给前端
            meta_packet = json.dumps({"sources": sources_data}, ensure_ascii=False)
            yield f"\n\n<<<SOURCES_METADATA>>>{meta_packet}<<<END_METADATA>>>"

            # 10. 存入记忆
            await chat_memory.add_message(user_id, session_id, "user", query)
            await chat_memory.add_message(user_id, session_id, "assistant", full_answer)


rag_chain = RAGChain()