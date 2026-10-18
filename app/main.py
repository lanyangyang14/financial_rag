import os
import shutil
import uuid
from fastapi import FastAPI, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from celery.result import AsyncResult  # 👈 修正：引入 Celery 的 AsyncResult

from app.core.config import settings
from app.services.llm_client import get_llm_client
from app.services.rag_chain import rag_chain
from app.tasks.celery_app import celery_app
from app.tasks.document_task import process_pdf_async

# 👈 修正：彻底删掉 from app_ui import task_id

app = FastAPI(title=settings.PROJECT_NAME)

@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} API"}

@app.get("/api/v1/chat/stream")
async def chat_stream_endpoint(query: str, provider: str = "deepseek"):
    llm = get_llm_client(provider)
    return StreamingResponse(llm.chat_stream(query), media_type="text/event-stream")

@app.get("/api/v1/rag/chat")
async def rag_chat_endpoint(
    query: str = Query(..., description="用户关于财报的问题"),
    session_id: str = Query("default_session", description="会话ID，用于区分不同用户的记忆")
):
    return StreamingResponse(
        rag_chain.generate_answer(query, session_id),
        media_type="text/event-stream"
    )

@app.post("/api/v1/document/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    uploaded_results = []
    upload_dir = "data/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    for file in files:
        document_id = str(uuid.uuid4())
        file_path = os.path.join(upload_dir, f"{document_id}_{file.filename}")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 触发 Celery 任务，并拿到返回的 task 对象
        task = process_pdf_async.delay(file_path, document_id)

        uploaded_results.append({
            "filename": file.filename,
            "document_id": document_id,
            "task_id": task.id,  # 👈 修正：这里必须取 task.id，而不是 task_id 函数
            "status": "已提交后台处理"
        })

    return {
        "message": f"成功接收 {len(files)} 个文件，正在后台解析入库。",
        "data": uploaded_results
    }

@app.get("/api/v1/document/task_status/{task_id}")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    task_status = getattr(task_result, "status", "PENDING")

    response = {
        "task_id": task_id,
        "status": task_status
    }

    # 🌟 如果 Celery 正在汇报进度，把详细信息吐给前端
    if task_status == "PROGRESS":
        response["progress"] = task_result.info
    elif task_status == "SUCCESS":
        response["result"] = task_result.result
    elif task_status == "FAILURE":
        response["error"] = str(task_result.info)

    return response