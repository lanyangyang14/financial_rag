import os
import shutil
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, UploadFile, File, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from celery.result import AsyncResult  # 👈 修正：引入 Celery 的 AsyncResult
from langchain_core.messages import HumanMessage
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.services.real_agent import multi_agent_app # 🌟 改成 multi_agent_app
from app.core.config import settings
from app.services.llm_client import get_llm_client
from app.services.rag_chain import rag_chain
from app.tasks.celery_app import celery_app
from app.tasks.document_task import process_pdf_async
from app.core.database import init_db, get_db
from app.models.db_models import DocumentRecord, User
from app.core.security import get_password_hash, verify_password, create_access_token, get_current_user


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

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} API"}


# 1. 🌟 真实注册接口
@app.post("/api/v1/auth/register")
async def register(username: str, password: str, db: Session = Depends(get_db)):
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 密码加密后存入数据库
    hashed_pwd = get_password_hash(password)
    new_user = User(username=username, hashed_password=hashed_pwd)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "注册成功", "user_id": new_user.id}


# 2. 🌟 真实登录接口
@app.post("/api/v1/auth/login")
async def login(username: str, password: str, db: Session = Depends(get_db)):
    # 去数据库找这个用户
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 校验密码
    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 验证通过，颁发 JWT Token
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}
@app.get("/api/v1/chat/stream")
async def chat_stream_endpoint(query: str, provider: str = "deepseek"):
    llm = get_llm_client(provider)
    return StreamingResponse(llm.chat_stream(query), media_type="text/event-stream")

@app.get("/api/v1/rag/chat")
@limiter.limit("5/minute")
async def rag_chat_endpoint(
    request: Request,
    query: str = Query(..., description="用户关于财报的问题"),
    session_id: str = Query("default_session", description="会话ID，用于区分不同用户的记忆"),
    user_id:str=Depends(get_current_user)
):
    client_ip = request.client.host if request.client else "unknown"
    print(f"📡 收到请求 - IP: {client_ip}, 用户: {user_id}, 问题: {query}")
    return StreamingResponse(
        rag_chain.generate_answer(query, session_id,user_id),
        media_type="text/event-stream"
    )

@app.post("/api/v1/document/upload")
@limiter.limit("3/minute")
async def upload_documents(request:Request,user_id:str=Depends(get_current_user),files: list[UploadFile] = File(...), db: AsyncSession = Depends(get_db)): # 👈 注入数据库
    client_ip = request.client.host if request.client else "unknown"
    print(f"📁 收到文件上传请求 - IP: {client_ip}, 文件数: {len(files)}")
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
            user_id=user_id# 暂时写死，后续可以接用户登录体系
        )
        db.add(new_doc)
        await db.commit() # 提交到 PG

        # 模拟 VIP 判定逻辑：假设用户ID包含 "vip" 就是高级用户
        is_vip = "vip" in user_id.lower()

        # 🌟 核心：priority 参数，0-9，数字越小优先级越高
        task_priority = 0 if is_vip else 5

        # 把优先级传给 Celery
        task = process_pdf_async.apply_async(
            args=[file_path, document_id, user_id],
            priority=task_priority
        )
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


@app.get("/api/v1/agent/chat")
async def agent_chat_endpoint(query: str):
    """基于 ReAct 状态机的智能体对话接口（流式展示思考过程）"""

    async def event_generator():
        inputs = {"messages": [HumanMessage(content=query)]}

        # 使用 astream 流式获取智能体的每一步
        async for event in multi_agent_app.astream(inputs):
            for node_name, state_data in event.items():
                if "messages" in state_data:
                    for msg in state_data["messages"]:
                        # 如果大模型在思考并决定调用工具
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            yield f"🔍 思考中：准备调用 {msg.tool_calls[0]['name']} 查询数据...\n"
                        # 如果是工具返回的结果
                        elif msg.type == "tool":
                            yield f"📊 数据返回：{str(msg.content)[:100]}...\n"
                        # 如果是大模型的最终回答
                        elif msg.content:
                            yield msg.content + "\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")