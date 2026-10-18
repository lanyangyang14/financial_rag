import streamlit as st
import requests
import json

# 页面配置
st.set_page_config(page_title="智能财报分析助手", page_icon="📊", layout="wide")
st.title("📊 智能财报分析助手 (RAG)")

# 初始化 Session State（用于保存会话 ID 和聊天记录）
if "session_id" not in st.session_state:
    st.session_state.session_id = "user_001"  # 实际生产中可以动态生成
if "messages" not in st.session_state:
    st.session_state.messages = []

# ================= 侧边栏：文件上传 =================
with st.sidebar:
    st.header("📁 知识库管理")
    uploaded_file = st.file_uploader("上传财报 PDF", type=["pdf"])
    if st.button("上传并解析") and uploaded_file is not None:
        with st.spinner("正在上传至后台，请稍候..."):
            # 调用我们刚才写好的异步上传接口
            files = {"files": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            response = requests.post("http://127.0.0.1:8001/api/v1/document/upload", files=files)

            if response.status_code == 200:
                st.success("上传成功！后台正在疯狂解析入库中...")
            else:
                st.error(f"上传失败: {response.text}")

    st.divider()
    if st.button("🗑️ 清空对话记忆"):
        st.session_state.messages = []
        # 这里可以顺便清空 Redis，为了简便，前端先清空
        st.rerun()

# ================= 主界面：聊天区域 =================
# 渲染历史对话
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 接收用户输入
if prompt := st.chat_input("请问关于财报的问题（例如：公司建议派发多少股息？）"):
    # 1. 显示用户问题
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. 调用后端 SSE 接口并流式渲染
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        # 构造请求 URL
        url = f"http://127.0.0.1:8001/api/v1/rag/chat?query={prompt}&session_id={st.session_state.session_id}"

        try:
            # 使用 stream=True 接收流式响应
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        text = chunk.decode("utf-8")
                        full_response += text
                        # 更新 UI，加上光标效果
                        message_placeholder.markdown(full_response + "▌")

            # 最终显示完整回答
            message_placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception as e:
            st.error(f"请求失败: {e}")
