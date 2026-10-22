import os
import shutil
import uuid
import time
from contextlib import asynccontextmanager

from app.core.logging_config import setup_logging
from app.core.middleware import TraceIDMiddleware
from app.core.contexts import set_user_id_context
from loguru import logger
from fastapi import FastAPI, Query, UploadFile, File, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from celery.result import AsyncResult
from langchain_core.messages import HumanMessage
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from app.core.contexts import trace_id
from app.services.real_agent import multi_agent_app
from app.services.llm_client import get_llm_client
from app.services.rag_chain import rag_chain
from app.tasks.celery_app import celery_app
from app.tasks.document_task import process_doc_async
from app.core.database import init_db, get_db
from app.models.db_models import DocumentRecord, User
# 🌟 清理：删掉了旧的 create_access_token, get_current_user
from app.core.security import get_password_hash, verify_password
from app.auth.auth_jwt import AuthJWT, redis_client
from app.auth.dependencies import get_current_user_dep, get_authjwt
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    print("✅ 数据库表初始化完成！")
    yield


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(TraceIDMiddleware) # 🌟 挂载追踪中间件
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} API"}


# ================= 认证模块 =================
@app.post("/api/v1/auth/register")
async def register(username: str, password: str, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    hashed_pwd = get_password_hash(password)
    new_user = User(username=username, hashed_password=hashed_pwd)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "注册成功", "user_id": new_user.id}


@app.post("/api/v1/auth/login")
async def login(
        username: str,
        password: str,
        db: Session = Depends(get_db),
        auth: AuthJWT = Depends(get_authjwt)  # 🌟 修复：必须注入 auth 引擎
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 🌟 使用全新的企业级 AuthJWT 签发双 Token
    access_token = auth.create_access_token(subject=user.username)
    refresh_token = auth.create_refresh_token(subject=user.username)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@app.post("/api/v1/auth/refresh")
async def refresh_token(refresh_token: str, auth: AuthJWT = Depends(get_authjwt)):
    try:
        payload = auth._verified_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="必须提供 Refresh Token")

        new_access_token = auth.create_access_token(subject=payload.get("sub"))
        return {"access_token": new_access_token, "token_type": "bearer"}
    except Exception:
        raise HTTPException(status_code=401, detail="刷新凭证无效或已过期")


@app.post("/api/v1/auth/logout")
async def logout(auth: AuthJWT = Depends(get_authjwt)):
    try:
        auth.jwt_required()
        payload = auth.get_raw_jwt()
        jti = payload.get("jti")
        exp = payload.get("exp")

        ttl = exp - int(time.time())
        if ttl > 0:
            redis_client.setex(f"blacklist:{jti}", ttl, "revoked")

        return {"message": "登出成功，凭证已失效"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


# ================= 对话与检索模块 =================
@app.get("/api/v1/chat/stream")
async def chat_stream_endpoint(query: str, provider: str = "deepseek"):
    llm = get_llm_client(provider)
    return StreamingResponse(llm.chat_stream(query), media_type="text/event-stream")


@app.get("/api/v1/rag/chat")
@limiter.limit("5/minute")
async def rag_chat_endpoint(
        request: Request,
        query: str = Query(..., description="用户关于财报的问题"),
        session_id: str = Query("default_session", description="会话ID"),
        user_id: str = Depends(get_current_user_dep)
):
    client_ip = request.client.host if request.client else "unknown"
    print(f"📡 收到请求 - IP: {client_ip}, 用户: {user_id}, 问题: {query}")
    return StreamingResponse(
        rag_chain.generate_answer(query, session_id, user_id),
        media_type="text/event-stream"
    )


# ================= 文档管理模块 =================
@app.post("/api/v1/document/upload")
@limiter.limit("3/minute")
async def upload_documents(
        request: Request,
        user_id: str = Depends(get_current_user_dep),
        files: list[UploadFile] = File(...),
        db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else "unknown"
    print(f"📁 收到文件上传请求 - IP: {client_ip}, 用户: {user_id}, 文件数: {len(files)}")

    uploaded_results = []
    upload_dir = "data/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    allowed_extensions = [".pdf", ".docx", ".xlsx", ".pptx", ".md", ".txt", ".jpg", ".jpeg", ".png"]

    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")
        current_trace_id = trace_id.get()

        task = process_doc_async.apply_async(
            args=[file_path, document_id, user_id],
            kwargs={"trace_id": current_trace_id},  # 🌟 传给 Celery
            priority=task_priority
        )
        document_id = str(uuid.uuid4())
        file_path = os.path.join(upload_dir, f"{document_id}_{file.filename}")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        new_doc = DocumentRecord(
            id=document_id,
            filename=file.filename,
            user_id=user_id
        )
        db.add(new_doc)
        db.commit()

        is_vip = "vip" in user_id.lower()
        task_priority = 0 if is_vip else 5

        task = process_doc_async.apply_async(
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

    response = {"task_id": task_id, "status": task_status}

    if task_status == "PROGRESS":
        response["progress"] = task_result.info
    elif task_status == "SUCCESS":
        response["result"] = task_result.result
    elif task_status == "FAILURE":
        response["error"] = str(task_result.info)

    return response


# ================= Agent 模块 =================
@app.get("/api/v1/agent/chat")
@limiter.limit("5/minute")
async def agent_chat_endpoint(
        request: Request,
        query: str,
        user_id: str = Depends(get_current_user_dep)
):
    """基于 ReAct 状态机的智能体对话接口（流式展示思考过程）"""

    client_ip = request.client.host if request.client else "unknown"
    print(f"🤖 [Agent 请求] IP: {client_ip}, 用户: {user_id}, 问题: {query}")

    async def event_generator():
        # 传入 user_id 供 Agent 工具使用
        inputs = {
            "messages": [HumanMessage(content=query)],
            "user_id": user_id
        }

        async for event in multi_agent_app.astream(inputs):
            for node_name, state_data in event.items():
                if "messages" in state_data:
                    for msg in state_data["messages"]:
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            yield f"🔍 思考中：准备调用 {msg.tool_calls[0]['name']} 查询数据...\n"
                        elif msg.type == "tool":
                            yield f"📊 数据返回：{str(msg.content)[:100]}...\n"
                        elif msg.content:
                            yield msg.content + "\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")