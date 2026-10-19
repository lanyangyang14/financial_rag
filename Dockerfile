FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 1) 先装 CPU 版 torch，彻底避免拉 nvidia-cudnn-cu13 / nvidia-nccl-cu13 等 2GB+ 的 CUDA 大包
#    本项目只用 sentence-transformers 做 BGE-Reranker 推理，DeepSeek 是外部 API，不需要 GPU
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu --retries 10 --timeout 600 --default-timeout=600

# 2) 再装其余依赖；torch 已满足，pip 不会重拉 CUDA 版
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --retries 10 --timeout 120

COPY . .

# 🌟 核心：让模型下载到 /app/models 目录下
ENV HF_HOME=/app/models
ENV HF_ENDPOINT=https://hf-mirror.com

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]