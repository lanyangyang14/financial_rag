import os
import asyncio
from app.tasks.celery_app import celery_app
from app.services.pdf_parser import FinancialPDFParser
from app.services.chunker import ParentChildChunker
from app.services.vector_store import vector_store


@celery_app.task(name="process_pdf_async")
def process_pdf_async(file_path: str, document_id: str):
    print(f"[Celery] 开始处理文档: {document_id}，路径: {file_path}")
    try:
        # 1. 解析
        parser = FinancialPDFParser(file_path)
        pages = parser.extract_text_with_metadata()
        parser.close()

        # 2. 切片
        chunker = ParentChildChunker(child_chunk_size=300)
        chunks = chunker.split(pages)

        # 3. 向量化入库
        async def _ingest():
            # 🌟 核心修改：每次入库前，确保集合存在（如果存在则跳过）
            # 注意：我稍微改了一下 init_collection 的逻辑，防止每次上传都删库，看下面
            if not vector_store.qdrant.collection_exists(vector_store.collection_name):
                vector_store.init_collection()
            else:
                print(f"ℹ️ Collection {vector_store.collection_name} 已存在，直接追加数据。")

            await vector_store.insert_chunks(chunks, document_id=document_id)

        asyncio.run(_ingest())

        print(f"[Celery] 文档处理完成: {document_id}")
        return {"status": "success", "chunks": len(chunks)}
    except Exception as e:
        print(f"[Celery] 处理失败: {e}")
        return {"status": "error", "message": str(e)}