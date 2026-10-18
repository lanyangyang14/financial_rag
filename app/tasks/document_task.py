import os
import asyncio
from app.tasks.celery_app import celery_app
from app.services.pdf_parser import FinancialPDFParser
from app.services.chunker import ParentChildChunker
from app.services.vector_store import vector_store


@celery_app.task(name="process_pdf_async")
def process_pdf_async(file_path: str, document_id: str):
    """
    后台异步任务：解析 PDF -> 切片 -> 向量化入库
    注意：Celery 是同步的，但我们的入库方法是异步的，需要用 asyncio.run 包起来
    """
    print(f"[Celery] 开始处理文档: {document_id}，路径: {file_path}")
    try:
        # 1. 解析
        parser = FinancialPDFParser(file_path)
        pages = parser.extract_text_with_metadata()
        parser.close()

        # 2. 切片
        chunker = ParentChildChunker(child_chunk_size=300)
        chunks = chunker.split(pages)

        # 3. 向量化入库 (包装异步调用)
        async def _ingest():
            await vector_store.insert_chunks(chunks, document_id=document_id)

        # 运行异步函数
        asyncio.run(_ingest())

        print(f"[Celery] 文档处理完成: {document_id}")
        return {"status": "success", "chunks": len(chunks)}
    except Exception as e:
        print(f"[Celery] 处理失败: {e}")
        return {"status": "error", "message": str(e)}