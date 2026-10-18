import os
import asyncio

from app.services.vision_service import vision_service
from app.tasks.celery_app import celery_app
from app.services.pdf_parser import FinancialPDFParser
from app.services.chunker import ParentChildChunker
from app.services.vector_store import vector_store


@celery_app.task(name="process_pdf_async", bind=True)  # 👈 1. 加上 bind=True
def process_pdf_async(self, file_path: str, document_id: str):  # 👈 2. 第一个参数变成 self
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

        for page in pages:
            image_paths = page["metadata"].get("image_paths", [])
            for img_path in image_paths:
                desc = vision_service.describe_image(img_path)
                if desc:
                    page["content"] += f"\n【图表描述】{desc}\n"

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
            if not vector_store.qdrant.collection_exists(vector_store.collection_name):
                vector_store.init_collection()
            await vector_store.insert_chunks(chunks, document_id=document_id)

        asyncio.run(_ingest())

        print(f"[Celery] 文档处理完成: {document_id}")
        return {"status": "success", "chunks": len(chunks)}
    except Exception as e:
        print(f"[Celery] 处理失败: {e}")
        return {"status": "error", "message": str(e)}