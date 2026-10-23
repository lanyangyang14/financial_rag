import streamlit as st
import requests
import os
import json

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001")
headers = {"Authorization": f"Bearer {st.session_state.get('token', '')}"}

# 1. 动态拉取对话模型列表
try:
    res = requests.get(f"{API_BASE_URL}/api/v1/models", headers=headers)
    chat_models = [m["model_name"] for m in res.json() if m["model_type"] == "对话模型"]
    if not chat_models:
        chat_models = ["deepseek-chat"] # 兜底
except:
    chat_models = ["deepseek-chat"]

# 2. 顶部选择器
st.sidebar.markdown("### ⚙️ 模型设置")
selected_model = st.sidebar.selectbox("当前对话模型", chat_models)

# ================= 主界面：聊天区域 =================
# 🌟 核心修复：确保 session_state 被初始化
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = "user_001"

# 先渲染历史记录
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 接收用户输入
if prompt := st.chat_input("请问关于财报的问题（例如：公司建议派发多少股息？）"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        # 🌟 用 params 传参，requests 会自动做 URL 编码，避免中文/特殊字符把请求拼坏
        url = f"{API_BASE_URL}/api/v1/rag/chat"
        params = {
            "query": prompt,
            "session_id": st.session_state.session_id,
            "model_name": selected_model
        }

        try:
            # 带上 Token 请求
            with requests.get(url, params=params, headers=headers, stream=True) as response:
                if response.status_code == 401:
                    st.error("⚠️ 登录已过期，请刷新页面重新登录。")
                    st.session_state.token = None
                    st.stop()

                response.raise_for_status()

                # 流式读取（打字机效果）
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        text = chunk.decode("utf-8")
                        full_response += text

                        # 过滤掉尾部的元数据标记，只展示正文
                        display_text = full_response.split("<<<SOURCES_METADATA>>>")[0]
                        message_placeholder.markdown(display_text + "▌")

            # 流式结束，解析溯源元数据
            pure_answer = full_response
            sources_data = []
            if "<<<SOURCES_METADATA>>>" in full_response:
                parts = full_response.split("<<<SOURCES_METADATA>>>")
                pure_answer = parts[0].strip()
                meta_str = parts[1].replace("<<<END_METADATA>>>", "")
                try:
                    sources_data = json.loads(meta_str).get("sources", [])
                except:
                    pass

            # 渲染最终纯文本回答
            message_placeholder.markdown(pure_answer)

            # 渲染底部的“原文溯源”折叠面板
            if sources_data:
                st.markdown("---")
                st.markdown("📚 **本条回答的原文溯源：**")
                for idx, source in enumerate(sources_data):
                    with st.expander(f"📍 第 {source['page']} 页 原文片段"):
                        st.info(source['content'])

            # 保存到会话记忆
            st.session_state.messages.append({"role": "assistant", "content": pure_answer})

        except Exception as e:
            st.error(f"请求失败: {e}")