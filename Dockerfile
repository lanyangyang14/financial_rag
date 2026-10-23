FROM python:3.11-slim

WORKDIR /app

# 🌟 核心：把 Debian 的官方源替换为清华源，实现秒级下载
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources || \
    sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list

RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 🌟 直接安装所有轻量级依赖（没有任何巨无霸了）
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

ENV HF_HOME=/app/models
ENV HF_ENDPOINT=https://hf-mirror.com

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]