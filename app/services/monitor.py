import os
# 🌟 适配 Langfuse v2：LangChain 回调处理器在 langfuse.callback 下
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

# 🌟 修复 2：动态获取 Docker 内部地址
# 如果在 Docker 里，用 http://langfuse-server:3000；如果在本地，用 http://localhost:3000
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

# 初始化 Langfuse 客户端
langfuse = Langfuse(
    public_key="pk-lf-7165d8d5-3028-4cbe-9b7d-d6814cace07c",
    secret_key="sk-lf-62ca472d-73c2-4502-b7c2-6bd53e5c8598",
    host=LANGFUSE_HOST
)

def get_langfuse_handler():
    """返回 Langfuse 的 Callback 处理器"""
    # 🌟 修复 3：v3 版本获取 handler 的写法变了
    return CallbackHandler()