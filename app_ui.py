import streamlit as st
import requests
import json
import time
import os  # 👈 新增：用于读取环境变量

# ================= 页面配置与初始化 =================
st.set_page_config(page_title="智能财报分析助手", page_icon="📊", layout="wide")
st.title("📊 智能财报分析助手 (RAG)")

# 🌟 核心：动态获取 API 地址（默认本地开发，Docker 里会读取环境变量）
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001")

if "session_id" not in st.session_state:
    st.session_state.session_id = "user_001"
if "messages" not in st.session_state:
    st.session_state.messages = []
# 🌟 新增：用于保存后台任务状态的变量
if "task_id" not in st.session_state:
    st.session_state.task_id = None
if "task_status" not in st.session_state:
    st.session_state.task_status = None

# ================= 侧边栏：文件上传 =================
with st.sidebar:
    st.header("📁 知识库管理")

    # 只有在没有正在进行的任务时，才允许上传新文件
    if st.session_state.task_status not in ["PENDING", "STARTED", "PROGRESS"]:
        uploaded_file = st.file_uploader("上传财报 PDF", type=["pdf"])

        if st.button("上传并解析") and uploaded_file is not None:
            files = {"files": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            with st.spinner("正在上传至服务器..."):
                # 🌟 修改：使用动态地址
                response = requests.post(f"{API_BASE_URL}/api/v1/document/upload", files=files)

            if response.status_code == 200:
                data = response.json()["data"][0]
                st.session_state.task_id = data["task_id"]
                st.session_state.task_status = "PENDING"
                st.rerun()  # 触发页面刷新，进入解析状态
            else:
                st.error("上传失败")

    # 🌟 核心：如果存在任务ID，就开始渲染进度条
    if st.session_state.task_id:
        status_placeholder = st.empty()
        progress_bar = st.progress(0)

        # 每次页面刷新，向后端问一次最新状态
        # 🌟 修改：使用动态地址
        res = requests.get(f"{API_BASE_URL}/api/v1/document/task_status/{st.session_state.task_id}").json()
        status = res.get("status")
        st.session_state.task_status = status

        if status in ["PENDING", "STARTED"]:
            status_placeholder.info("⚙️ 正在初始化后台任务...")
            progress_bar.progress(10)
            time.sleep(1)
            st.rerun()  # 🌟 每秒重绘自己，实现动画效果

        elif status == "PROGRESS":
            prog = res.get("progress", {})
            curr = prog.get("current", 0)
            total = prog.get("total", 1)
            msg = prog.get("msg", "处理中")

            percent = int((curr / total) * 100) if total > 0 else 0
            progress_bar.progress(percent)
            status_placeholder.info(f"⚙️ {msg} ({curr}/{total})")
            time.sleep(1)
            st.rerun()  # 🌟 持续刷新

        elif status == "SUCCESS":
            progress_bar.progress(100)
            status_placeholder.success("✅ 解析并入库完成！")
            # 清理状态，允许上传新文件
            st.session_state.task_id = None
            st.session_state.task_status = None

        elif status == "FAILURE":
            status_placeholder.error(f"❌ 解析失败: {res.get('error')}")
            st.session_state.task_id = None
            st.session_state.task_status = None

    st.divider()
    if st.button("🗑️ 清空对话记忆"):
        st.session_state.messages = []
        st.rerun()

# ================= 主界面：聊天区域 =================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("请问关于财报的问题（例如：公司建议派发多少股息？）"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        # 🌟 修改：使用动态地址
        url = f"{API_BASE_URL}/api/v1/rag/chat?query={prompt}&session_id={st.session_state.session_id}"

        try:
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        text = chunk.decode("utf-8")
                        full_response += text
                        display_text = full_response.split("<<<SOURCES_METADATA>>>")[0]
                        message_placeholder.markdown(display_text + "▌", unsafe_allow_html=True)

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

            message_placeholder.markdown(pure_answer, unsafe_allow_html=True)

            if sources_data:
                st.markdown("---")
                st.markdown("📚 **本条回答的原文溯源：**")
                for idx, source in enumerate(sources_data):
                    with st.expander(f"📍 第 {source['page']} 页 原文片段"):
                        st.info(source['content'])

            st.session_state.messages.append({"role": "assistant", "content": pure_answer})

        except Exception as e:
            st.error(f"请求失败: {e}")