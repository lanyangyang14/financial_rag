import os
import asyncio

from app.services.vision_service import vision_service
from app.tasks.celery_app import celery_app
from app.services.pdf_parser import FinancialPDFParser
from app.services.chunker import ParentChildChunker
from app.services.vector_store import vector_store
from app.services.graph_service import graph_service

@celery_app.task(name="process_pdf_async", bind=True)  # 👈 1. 加上 bind=True
def process_pdf_async(self, file_path: str, document_id: str,user_id:str):  # 👈 2. 第一个参数变成 self
    print(f"[Celery] 开始处理文档: {document_id}，路径: {file_path}")
    try:
        # 1. 解析
        self.update_state(state='PROGRESS', meta={'current': 1, 'total': 3, 'msg': '正在解析 PDF...'})
        parser = FinancialPDFParser(file_path)
        pages = parser.extract_text_with_metadata()
        parser.close()

        # 2. 识别图片
        total_images = sum(len(p["metadata"].get("image_paths", [])) for p in pages)
        processed_images = 0
        # 遍历每一页，处理图片（公式与表格）
        for page in pages:
            image_paths = page["metadata"].get("image_paths", [])
            if image_paths:
                print(f"  -> 正在解析第 {page['page_number']} 页的 {len(image_paths)} 张图片/表格/公式...")
                image_descriptions = ""
                for img_path in image_paths:
                    # 🌟 核心修改：调用专门解析公式和表格的方法，并设为 True
                    desc = vision_service.parse_complex_pdf_image(img_path, is_formula_or_table=True)
                    if desc:
                        # 用特殊的标记包裹，方便大模型识别这是公式/表格
                        image_descriptions += f"\n\n【解析出的复杂图表/公式】\n{desc}\n\n"

                # 把解析出来的 LaTeX 和 Markdown 表格追加到当前页的文本中
                page["content"] += image_descriptions

                processed_images += 1
                # 🌟 每次处理完一张图，更新一次进度！
                self.update_state(
                    state='PROGRESS',
                    meta={'current': processed_images, 'total': total_images,
                          'msg': f'正在识别第{page["page_number"]}页图片'}
                )

        # 3. 切片
        self.update_state(state='PROGRESS', meta={'current': 2, 'total': 3, 'msg': '正在切片...'})
        chunker = ParentChildChunker(child_chunk_size=300)
        chunks = chunker.split(pages)

        # 4. 向量化入库
        self.update_state(state='PROGRESS', meta={'current': 3, 'total': 3, 'msg': '正在存入向量库...'})

        async def _ingest():
            # 🌟 关键：在事件循环内部导入和实例化，避免连接池复用引起的 Event loop closed
            from app.services.vector_store import VectorStoreManager
            from app.services.es_search import ESSearchService

            v_store = VectorStoreManager()
            es_store = ESSearchService()

            if not v_store.qdrant.collection_exists(v_store.collection_name):
                v_store.init_collection()

            await es_store.init_index()

            await v_store.insert_chunks(chunks, document_id=document_id,user_id=user_id)
            await es_store.index_chunks(chunks, document_id=document_id,user_id=user_id)

        asyncio.run(_ingest())
        # 4. 抽取知识图谱 (为了测试速度，我们只拿第一页的前 1000 个字去抽)
        print("🕸️ 准备启动 GraphRAG 抽取任务...")
        test_text = pages[0]["content"][:1000] if pages else ""
        if test_text:
            graph_service.extract_and_store(test_text)

        print(f"[Celery] 文档处理及图谱抽取完成: {document_id}")

        print(f"[Celery] 文档处理完成: {document_id}")
        return {"status": "success", "chunks": len(chunks)}
    except Exception as e:
        print(f"[Celery] 处理失败: {e}")
        return {"status": "error", "message": str(e)}