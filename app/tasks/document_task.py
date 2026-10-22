import os
import asyncio
from app.tasks.celery_app import celery_app
from app.services.pdf_parser import FinancialPDFParser
from app.services.chunker import ParentChildChunker
from app.services.vision_service import vision_service
from app.services.universal_loader import universal_loader
from app.services.smart_chunker import smart_chunker
from app.core.contexts import set_trace_id_context
from loguru import logger
# 🌟 注意：如果你需要直接解析图片，需要安装 Pillow 并导入
from PIL import Image


@celery_app.task(name="process_doc_async", bind=True)
def process_doc_async(self, file_path: str, document_id: str, user_id: str, trace_id: str = None):
    # 🌟 2. 核心：如果前端传了 trace_id，立刻恢复上下文
    if trace_id:
        set_trace_id_context(trace_id)

    ext = os.path.splitext(file_path)[1].lower()
    # 🌟 3. 用 logger 替代 print，这样日志才会带上 trace_id 和时间戳
    logger.info(f"[Celery] 开始处理文档: {document_id}，格式: {ext}，用户: {user_id}")

    try:
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
        processed_items = 0
        total_items = 1  # 默认值
        full_text_for_graph = ""

        # ================= 🌟 核心路由分发逻辑 =================

        # 分支 1：如果是 PDF，走原有的豪华流式解析（保留表格、公式、视觉）
        if ext == ".pdf":
            parser = FinancialPDFParser(file_path)
            chunker = ParentChildChunker(child_chunk_size=300)
            total_items = parser.total_pages

            # 获取流式数据
            for page in parser.parse_stream():
                processed_items += 1

                # 收集图谱数据（前 5 页）
                if processed_items <= 5:
                    full_text_for_graph += page["content"] + "\n"

                # 视觉模型处理（保留你原来的公式和表格解析）
                image_paths = page["metadata"].get("image_paths", [])
                if image_paths:
                    image_descriptions = ""
                    for img_path in image_paths:
                        desc = vision_service.parse_complex_pdf_image(img_path, is_formula_or_table=True)
                        if desc:
                            image_descriptions += f"\n\n【解析出的复杂图表/公式】\n{desc}\n\n"
                    page["content"] += image_descriptions

                # 切片
                chunks = chunker.split([page])
                batch_chunks.extend(chunks)

                # 批量入库
                if len(batch_chunks) >= BATCH_SIZE or processed_items == total_items:
                    async def _ingest():
                        await v_store.insert_chunks(batch_chunks, document_id=document_id, user_id=user_id)
                        await es_store.index_chunks(batch_chunks, document_id=document_id, user_id=user_id)

                    asyncio.run(_ingest())
                    batch_chunks = []

                # 汇报进度
                self.update_state(
                    state='PROGRESS',
                    meta={'current': processed_items, 'total': total_items,
                          'msg': f'PDF: 已处理第 {processed_items}/{total_items} 页'}
                )
            parser.close()

        # 分支 2：如果是 Word/Excel/PPT/Markdown，走通用加载器和智能切片
        elif ext in [".docx", ".xlsx", ".pptx", ".md", ".txt"]:
            print(f"  -> 使用通用加载器处理 {ext} 文件")
            pages = universal_loader.load(file_path)
            total_items = len(pages)

            # 收集图谱数据
            if pages:
                full_text_for_graph = "\n".join([p["content"] for p in pages[:3]])

            # 智能切片
            chunks = smart_chunker.split(pages, ext)

            # 批量入库
            for i in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[i:i + BATCH_SIZE]

                async def _ingest():
                    await v_store.insert_chunks(batch, document_id=document_id, user_id=user_id)
                    await es_store.index_chunks(batch, document_id=document_id, user_id=user_id)

                asyncio.run(_ingest())
                processed_items = min(i + BATCH_SIZE, len(chunks))
                self.update_state(
                    state='PROGRESS',
                    meta={'current': processed_items, 'total': len(chunks),
                          'msg': f'{ext.upper()}: 已处理 {processed_items}/{len(chunks)} 个切片'}
                )

        # 分支 3：如果直接是图片（JPG/PNG）
        elif ext in [".jpg", ".jpeg", ".png"]:
            print(f"  -> 使用视觉大模型直接解析图片")
            total_items = 1
            self.update_state(state='PROGRESS', meta={'current': 0, 'total': 1, 'msg': '正在调用视觉模型解析图片...'})

            # 假设你的 vision_service 支持直接传图片路径解析
            desc = vision_service.parse_complex_pdf_image(file_path, is_formula_or_table=True)
            content = f"【图片解析内容】\n{desc}"

            full_text_for_graph = content

            # 将整张图片作为一个 chunk
            chunks = [{
                "child_content": content,
                "parent_content": content,
                "metadata": {"source": file_path, "page": 1}
            }]

            async def _ingest_img():
                await v_store.insert_chunks(chunks, document_id=document_id, user_id=user_id)
                await es_store.index_chunks(chunks, document_id=document_id, user_id=user_id)

            asyncio.run(_ingest_img())

            self.update_state(state='PROGRESS', meta={'current': 1, 'total': 1, 'msg': '图片解析完毕'})

        else:
            raise ValueError(f"不支持的文件格式: {ext}")

        # ================= 异步任务：图谱抽取 =================
        if full_text_for_graph.strip():
            print("🕸️ 发送异步图谱抽取任务到队列...")
            extract_graph_async.delay(full_text_for_graph, document_id)

        return {"status": "success", "chunks": len(batch_chunks)}

    except Exception as e:
        print(f"[Celery] 处理失败: {e}")
        return {"status": "error", "message": str(e)}


@celery_app.task(name="extract_graph_async")
def extract_graph_async(text_content: str, document_id: str):
    print(f"🕸️ [图谱异步任务] 开始抽取 {document_id} 的知识图谱...")
    from app.services.graph_service import graph_service
    graph_service.extract_and_store(text_content)
    return {"status": "success"}