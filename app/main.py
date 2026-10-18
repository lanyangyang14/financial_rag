import os
import shutil
import uuid

from fastapi import FastAPI, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from app.core.config import settings
from app.services.llm_client import get_llm_client
from app.services.rag_chain import rag_chain # 👈 引入 RAG 链
from app.tasks.document_task import process_pdf_async

app = FastAPI(title=settings.PROJECT_NAME)

@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} API"}

# 原有的测试接口（保留）
@app.get("/api/v1/chat/stream")
async def chat_stream_endpoint(query: str, provider: str = "deepseek"):
    llm = get_llm_client(provider)
    return StreamingResponse(llm.chat_stream(query), media_type="text/event-stream")

# 🌟 新增的 RAG 问答接口
@app.get("/api/v1/rag/chat")
async def rag_chat_endpoint(
    query: str = Query(..., description="用户关于财报的问题"),
    session_id: str = Query("default_session", description="会话ID，用于区分不同用户的记忆") # 👈 新增
):
    """基于财报知识库的流式问答接口（带多轮记忆）"""
    return StreamingResponse(
        rag_chain.generate_answer(query, session_id),
        media_type="text/event-stream"
    )


@app.post("/api/v1/document/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    """
    接收用户上传的财报 PDF，保存到本地，并丢给 Celery 异步处理
    """
    uploaded_results = []
    upload_dir = "data/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    for file in files:
        # 生成唯一的文档 ID
        document_id = str(uuid.uuid4())
        file_path = os.path.join(upload_dir, f"{document_id}_{file.filename}")

        # 保存文件到本地
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 触发 Celery 异步任务 (.delay 是 Celery 的核心异步调用)
        process_pdf_async.delay(file_path, document_id)

        uploaded_results.append({
            "filename": file.filename,
            "document_id": document_id,
            "status": "已提交后台处理"
        })

    return {
        "message": f"成功接收 {len(files)} 个文件，正在后台解析入库。",
        "data": uploaded_results
    }