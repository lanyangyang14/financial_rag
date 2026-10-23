import json
import os
import re
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage
from langfuse import observe, propagate_attributes, Langfuse

from app.services.guardrails import guardrails
from app.services.reranker import reranker_service
from app.services.vector_store import vector_store
from app.services.es_search import ESSearchService
from app.services.graph_service import graph_service
from app.services.fusion import reciprocal_rank_fusion
from app.services.memory import cognitive_memory
from app.services.query_router import router
from app.services.context_manager import budget_manager
from app.core.models.manager import ModelManager  # 🌟 引入模型管理器

langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-1234567890"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-1234567890"),
    host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
)


class RAGChain:
    def __init__(self):
        self.es_service = ESSearchService()

    async def rewrite_query(self, llm, query: str, history_text: str) -> str:
        """多轮对话查询改写（传入动态 llm）"""
        if not history_text:
            return query
        prompt = f"""你是一个查询改写助手... {history_text} 最新提问：{query} 改写后："""
        try:
            response = await llm.client.chat.completions.create(
                model=llm.model_name, messages=[{"role": "user", "content": prompt}], temperature=0.1
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return query

    @observe(name="RAG_Answer_Generator")
    async def generate_answer(self, query: str, session_id: str, user_id: str, model_name: str = "deepseek-chat") -> \
    AsyncGenerator[str, None]:
        # 1. 安检
        is_safe, error_msg = await guardrails.check_input(query)
        if not is_safe:
            yield error_msg
            return

        with propagate_attributes(session_id=session_id, user_id=user_id):
            # 🌟 核心：动态从数据库加载用户选中的模型，并带上 user_id 用于记账
            self.llm = ModelManager.get_chat_model_by_db(model_name, user_id=user_id)

            # 2. 获取全方位认知上下文
            memory_ctx = await cognitive_memory.get_memory_context(user_id, session_id)
            procedural_exp = cognitive_memory.get_procedural_experience(query)
            history_recall = ""

            if any(w in query for w in ["刚才", "之前", "我说过", "前面"]):
                recent_history = memory_ctx['working']
                if recent_history.strip():
                    history_recall = "【近期对话参考】\n" + recent_history + "\n\n"
                elif memory_ctx['summary'].strip():
                    pass
                else:
                    recalled_docs = await vector_store.search(query, user_id=user_id, top_k=2, chunk_type="history")
                    if recalled_docs:
                        history_recall = "【历史相关对话召回】\n" + "\n".join(
                            [d["parent_content"] for d in recalled_docs]) + "\n\n"

            # 3. 查询改写
            rewritten_query = await self.rewrite_query(self.llm, query, memory_ctx["working"])

            # 4. 智能路由
            route_type = router.route(rewritten_query)
            vector_docs, es_docs, graph_context, context_str = [], [], "", ""

            if route_type == "direct":
                pass
            elif route_type == "macro_summary":
                vector_docs = await vector_store.search(rewritten_query, user_id=user_id, top_k=5, chunk_type="summary")
            elif route_type == "keyword":
                es_docs = await self.es_service.search(rewritten_query, user_id=user_id, top_k=5)
            elif route_type == "semantic":
                vector_docs = await vector_store.search(rewritten_query, user_id=user_id, top_k=5)
            elif route_type == "hybrid":
                vector_docs = await vector_store.search(rewritten_query, user_id=user_id, top_k=5)
                es_docs = await self.es_service.search(rewritten_query, user_id=user_id, top_k=5)
                try:
                    graph_context = graph_service.graph_search(rewritten_query)
                except Exception:
                    pass

            # 5. 组装候选集与重排
            candidates = []
            if vector_docs and es_docs:
                is_precision_query = len(re.findall(r'\d+', rewritten_query)) >= 3 or len(rewritten_query) < 10
                weights = [0.5, 1.5] if is_precision_query else [1.5, 0.5]
                fused_docs = reciprocal_rank_fusion([vector_docs, es_docs], weights=weights)
                candidates = fused_docs[:10]
            elif vector_docs:
                candidates = vector_docs
            elif es_docs:
                candidates = es_docs

            top_docs = []
            if candidates:
                top_docs = reranker_service.rerank(query=rewritten_query, docs=candidates, top_k=3)

            # 6. 组装上下文与溯源
            sources_data = []
            for doc in top_docs:
                page = doc.get('page', '未知')
                content = doc.get('parent_content', '')
                context_str += f"【第 {page} 页内容】\n{content}\n\n"
                if not any(s['page'] == page for s in sources_data):
                    sources_data.append({"page": page, "content": content.strip()[:500] + "..."})
            if graph_context:
                context_str += f"【知识图谱关联信息】\n{graph_context}\n\n"

            # 🌟 核心修复：必须在这里（context_str 组装完之后）执行 Token 裁剪！
            safe_working, safe_context = budget_manager.build_final_context(
                profile=memory_ctx['profile'], summary=memory_ctx['summary'],
                working=memory_ctx['working'], retrieved_docs=context_str
            )

            # 7. 组装 Prompt
            prompt = f"""你是一个极其专业的财务分析师...
{memory_ctx['profile']}
{memory_ctx['summary']}
{history_recall}
{procedural_exp}

【财报信息】：
{safe_context}

【近期对话】：
{safe_working}

【当前用户问题】：
{query}
"""
            # 8. 流式输出
            full_answer = ""
            # 🌟 动态 llm 流式调用
            async for chunk in self.llm.chat_stream(prompt) if hasattr(self.llm, 'chat_stream') else self.llm._astream(
                    [HumanMessage(content=prompt)]):
                # 处理两种可能的返回格式
                text = chunk if isinstance(chunk, str) else chunk.content
                full_answer += text
                yield text

            safe_answer = guardrails.check_output(full_answer)
            if safe_answer != full_answer:
                yield f"\n\n⚠️ 注意：系统已对敏感隐私信息脱敏。"

            meta_packet = json.dumps({"sources": sources_data}, ensure_ascii=False)
            yield f"\n\n<<<SOURCES_METADATA>>>{meta_packet}<<<END_METADATA>>>"

            await cognitive_memory.add_message(user_id, session_id, "user", query)
            await cognitive_memory.add_message(user_id, session_id, "assistant", full_answer)


rag_chain = RAGChain()