import os
import asyncio
from app.tasks.celery_app import celery_app
from app.services.pdf_parser import FinancialPDFParser
from app.services.chunker import ParentChildChunker
from app.services.vision_service import vision_service
from app.services.llm_client import get_llm_client  # 🌟 引入大模型客户端用于生成摘要


@celery_app.task(name="process_pdf_async", bind=True)
def process_pdf_async(self, file_path: str, document_id: str, user_id: str):
    print(f"[Celery] 开始流式处理文档: {document_id}，用户: {user_id}")
    try:
        parser = FinancialPDFParser(file_path)
        chunker = ParentChildChunker(child_chunk_size=300)
        total_pages = parser.total_pages

        # 初始化大模型客户端（用于生成摘要）
        llm = get_llm_client("deepseek")

        async def _init_db():
            from app.services.vector_store import VectorStoreManager
            from app.services.es_search import ESSearchService
            v_store = VectorStoreManager()
            es_store = ESSearchService()
            if not v_store.qdrant.collection_exists(v_store.collection_name):
                v_store.init_collection()
            await es_store.init_index()
            return v_store, es_store

        v_store, es_store = asyncio.run(_init_db())

        batch_chunks = []
        BATCH_SIZE = 10
        processed_pages = 0
        full_text_for_graph = ""

        for page in parser.parse_stream():
            processed_pages += 1

            if processed_pages <= 5:
                full_text_for_graph += page["content"] + "\n"

            # 1. 图片视觉解析
            image_paths = page["metadata"].get("image_paths", [])
            if image_paths:
                image_descriptions = ""
                for img_path in image_paths:
                    desc = vision_service.parse_complex_pdf_image(img_path, is_formula_or_table=True)
                    if desc:
                        image_descriptions += f"\n\n【解析出的复杂图表/公式】\n{desc}\n\n"
                page["content"] += image_descriptions

            # 2. 生成页级摘要（宏观信息）
            page_summary_chunk = None
            if page["content"].strip():
                print(f"  -> 正在生成第 {processed_pages} 页的摘要...")
                summary_prompt = f"请用一句话高度概括以下财报内容的核心要点，保留核心数据：\n{page['content']}"

                try:
                    # 在同步的 Celery 任务中安全地调用异步大模型
                    summary_resp = asyncio.run(llm.client.chat.completions.create(
                        model=llm.model,
                        messages=[{"role": "user", "content": summary_prompt}],
                        temperature=0.1
                    ))
                    summary_text = summary_resp.choices[0].message.content.strip()

                    page_summary_chunk = {
                        "child_content": summary_text,
                        "parent_content": summary_text,
                        "metadata": {
                            "page": page["page_number"],
                            "source": page["metadata"]["source"]
                        }
                    }
                    print(f"  ✅ 摘要: {summary_text[:30]}...")
                except Exception as e:
                    print(f"  ⚠️ 摘要生成失败: {e}")

            # 3. 切片并追加到批处理池子
            chunks = chunker.split([page])
            batch_chunks.extend(chunks)

            # 4. 如果池子满了，或者已经是最后一页，触发入库
            if len(batch_chunks) >= BATCH_SIZE or processed_pages == total_pages:
                async def _ingest():
                    # 写入原文切片
                    await v_store.insert_chunks(batch_chunks, document_id=document_id, user_id=user_id,
                                                chunk_type="text")
                    await es_store.index_chunks(batch_chunks, document_id=document_id, user_id=user_id,
                                                chunk_type="text")

                    # 🌟 顺便把这一页的摘要也写入向量库（归类为 summary）
                    if page_summary_chunk:
                        await v_store.insert_chunks([page_summary_chunk], document_id=document_id, user_id=user_id,
                                                    chunk_type="summary")
                        await es_store.index_chunks([page_summary_chunk], document_id=document_id, user_id=user_id,
                                                    chunk_type="summary")

                asyncio.run(_ingest())
                batch_chunks = []  # 清空池子

            # 5. 汇报进度
            self.update_state(
                state='PROGRESS',
                meta={'current': processed_pages, 'total': total_pages,
                      'msg': f'已处理第 {processed_pages}/{total_pages} 页'}
            )

        parser.close()

        # 6. 发送异步图谱抽取任务
        if full_text_for_graph.strip():
            print("🕸️ 发送异步图谱抽取任务到队列...")
            extract_graph_async.delay(full_text_for_graph, document_id)

        return {"status": "success", "pages": total_pages}

    except Exception as e:
        print(f"[Celery] 处理失败: {e}")
        return {"status": "error", "message": str(e)}


@celery_app.task(name="extract_graph_async")
def extract_graph_async(text_content: str, document_id: str):
    print(f"🕸️ [图谱异步任务] 开始抽取 {document_id} 的知识图谱...")
    from app.services.graph_service import graph_service
    graph_service.extract_and_store(text_content)
    return {"status": "success"}