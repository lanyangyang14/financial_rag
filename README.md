# 📊 智能财报分析助手 (Financial RAG Agent)

这是一个基于大语言模型和 RAG 技术的**企业级财报/研报智能分析系统**。支持复杂文档解析、多模态图表理解、混合检索与精准引用溯源。

## ✨ 核心特性

- **📄 复杂文档解析**：基于 `PyMuPDF` 与 `pdfplumber`，完美提取文本、复杂表格（转 Markdown）与图片。
- **🖼️ 多模态图表理解**：本地集成 `Ollama + LLaVA` 视觉模型，自动提取财报中的图表并生成语义描述，存入知识库。
- **🔍 工业级混合检索**：采用 `Qdrant` 向量数据库，结合 Dense（语义向量）与 Sparse（关键词稀疏向量）进行双路召回，并使用 RRF 算法融合排序。
- **⚡ 异步高并发架构**：基于 `FastAPI` + `Celery` + `Redis`，耗时任务（解析、向量化）全部后台异步处理，接口响应毫秒级。
- **🧠 多轮对话与记忆**：基于 `Redis` 持久化对话历史，结合大模型 `Query Rewrite`（查询改写），精准理解“那毛利呢？”等代词指代。
- **📍 精准引用溯源**：流式返回结果中携带元数据，前端支持点击展开对应页码的原文片段，彻底解决大模型幻觉。

## 🏗️ 系统架构

（建议在这里画一个流程图，或者用文字描述）
1. **接入层**：Streamlit 客户端。
2. **API 层**：FastAPI 接收请求，分发给 Celery。
3. **处理层**：Celery Worker 执行 PDF 解析、多模态图像识别、切片、Ollama 向量化。
4. **存储层**：Qdrant（向量）、Redis（消息队列/记忆）、PostgreSQL（业务数据）。
5. **LLM 层**：DeepSeek（主力生成）、本地 Ollama（Embedding / 视觉）。

## 🚀 快速启动

### 1. 环境准备
- 安装 [Docker Desktop](https://www.docker.com/) 并启动。
- 安装 [Ollama](https://ollama.com/) 并拉取模型：
  ```bash
  ollama pull nomic-embed-text
  ollama pull llava
  
#启动依赖服务（docker）
docker-compose up -d

#启动后端（本地）
python -m venv venv
# Windows 激活: venv\Scripts\activate
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env # 填入你的 DEEPSEEK_API_KEY

# 启动 FastAPI
uvicorn app.main:app --reload --port 8001

# 启动 Celery Worker (新终端)
celery -A app.tasks.celery_app.celery_app worker --loglevel=info -P solo -Q celery,graph_queue

#启动前端UI
streamlit run app_ui.py

🛠️ 技术栈
框架: FastAPI, Streamlit, Celery

LLM: DeepSeek API, Ollama (nomic-embed-text / llava)

数据库: Qdrant (向量), Redis (缓存/队列), PostgreSQL

文档解析: PyMuPDF, pdfplumber

启动简单环境    .\start.bat
启动完整环境 docker compose up -d postgres redis qdrant elasticsearch neo4j reranker-service backend celery_worker frontend

查找端口冲突：netstat -ano | findstr :5601
查找进程冲突：tasklist | findstr <那个PID>

更新表以及迁移:alembic revision --autogenerate -m "add all new tables for platform"
alembic upgrade head

查看docker报错日志：docker compose logs -f frontend
docker compose logs --tail 50 frontend