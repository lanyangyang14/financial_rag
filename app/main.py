from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from app.core.config import settings
from app.services.llm_client import get_llm_client
from app.services.rag_chain import rag_chain # 👈 引入 RAG 链

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
async def rag_chat_endpoint(query: str = Query(..., description="用户关于财报的问题")):
    """基于财报知识库的流式问答接口"""
    return StreamingResponse(
        rag_chain.generate_answer(query),
        media_type="text/event-stream"
    )