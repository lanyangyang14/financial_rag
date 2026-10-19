import os
import shutil
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from celery.result import AsyncResult  # 👈 修正：引入 Celery 的 AsyncResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.llm_client import get_llm_client
from app.services.rag_chain import rag_chain
from app.tasks.celery_app import celery_app
from app.tasks.document_task import process_pdf_async
from app.core.database import init_db, get_db
from app.models.db_models import DocumentRecord
# 👈 修正：彻底删掉 from app_ui import task_id

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行的代码（替代 startup）
    init_db()
    print("✅ 数据库表初始化完成！")
    yield
    # 关闭时执行的代码（替代 shutdown，如果有的话）
    pass

# 👈 必须把 lifespan 传给 FastAPI，否则 init_db() 永远不会执行
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

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
async def upload_documents(files: list[UploadFile] = File(...), db: AsyncSession = Depends(get_db)): # 👈 注入数据库
    uploaded_results = []
    upload_dir = "data/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    for file in files:
        document_id = str(uuid.uuid4())
        file_path = os.path.join(upload_dir, f"{document_id}_{file.filename}")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 🌟 关键修改：把文件记录存入 PostgreSQL
        new_doc = DocumentRecord(
            id=document_id,
            filename=file.filename,
            user_id="user_001" # 暂时写死，后续可以接用户登录体系
        )
        db.add(new_doc)
        db.commit() # 提交到 PG

        task = process_pdf_async.delay(file_path, document_id)

        uploaded_results.append({
            "filename": file.filename,
            "document_id": document_id,
            "task_id": task.id,
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