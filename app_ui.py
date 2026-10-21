import streamlit as st
import requests
import json
import time
import os

# ================= 页面配置与初始化 =================
st.set_page_config(page_title="智能财报分析助手", page_icon="📊", layout="wide")
st.title("📊 智能财报分析助手 (RAG)")

# 🌟 动态获取后端 API 地址（兼容本地和 Docker 环境）
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001")

# ================= 核心：JWT 登录拦截 =================
if "token" not in st.session_state:
    st.session_state.token = None

if st.session_state.token is None:
    st.subheader("🔐 请先登录系统")
    col1, col2 = st.columns(2)
    with col1:
        username = st.text_input("用户名 (例如: admin)")
    with col2:
        password = st.text_input("密码 (例如: 123456)", type="password")

    if st.button("登录", type="primary"):
        login_url = f"{API_BASE_URL}/api/v1/auth/login?username={username}&password={password}"
        try:
            res = requests.post(login_url)
            if res.status_code == 200:
                st.session_state.token = res.json()["access_token"]
                st.success("登录成功！正在进入系统...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ 账号或密码错误，请重试")
        except Exception as e:
            st.error(f"连接后端失败: {e}")
    st.stop()  # 🌟 核心：如果没有登录，直接停止渲染后面的所有内容

# ================= 登录成功后的主界面 =================
# 如果登录成功，把 Token 放到 Header 里，供后续所有请求使用
headers = {"Authorization": f"Bearer {st.session_state.token}"}

if "session_id" not in st.session_state:
    st.session_state.session_id = "user_001"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "task_id" not in st.session_state:
    st.session_state.task_id = None
if "task_status" not in st.session_state:
    st.session_state.task_status = None

# ================= 侧边栏：文件上传 =================
with st.sidebar:
    st.header("📁 知识库管理")
    st.caption(f"当前登录凭证: {st.session_state.token[:15]}...")

    if st.session_state.task_status not in ["PENDING", "STARTED", "PROGRESS"]:
        uploaded_file = st.file_uploader("上传财报 PDF", type=["pdf"])

        if st.button("上传并解析") and uploaded_file is not None:
            files = {"files": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            with st.spinner("正在上传至服务器..."):
                # 🌟 上传时带上 Token
                response = requests.post(f"{API_BASE_URL}/api/v1/document/upload", files=files, headers=headers)

            if response.status_code == 200:
                data = response.json()["data"][0]
                st.session_state.task_id = data["task_id"]
                st.session_state.task_status = "PENDING"
                st.rerun()
            elif response.status_code == 401:
                st.error("登录已过期，请刷新页面重新登录")
            else:
                st.error(f"上传失败: {response.text}")

    # 进度条渲染逻辑
    if st.session_state.task_id:
        status_placeholder = st.empty()
        progress_bar = st.progress(0)

        try:
            # 🌟 轮询时带上 Token
            res = requests.get(f"{API_BASE_URL}/api/v1/document/task_status/{st.session_state.task_id}",
                               headers=headers).json()
            status = res.get("status")
            st.session_state.task_status = status

            if status in ["PENDING", "STARTED"]:
                status_placeholder.info("⚙️ 正在初始化后台任务...")
                progress_bar.progress(10)
                time.sleep(1)
                st.rerun()
            elif status == "PROGRESS":
                prog = res.get("progress", {})
                curr = prog.get("current", 0)
                total = prog.get("total", 1)
                msg = prog.get("msg", "处理中")
                percent = int((curr / total) * 100) if total > 0 else 0
                progress_bar.progress(percent)
                status_placeholder.info(f"⚙️ {msg} ({curr}/{total})")
                time.sleep(1)
                st.rerun()
            elif status == "SUCCESS":
                progress_bar.progress(100)
                status_placeholder.success("✅ 解析并入库完成！")
                st.session_state.task_id = None
                st.session_state.task_status = None
            elif status == "FAILURE":
                status_placeholder.error(f"❌ 解析失败: {res.get('error')}")
                st.session_state.task_id = None
                st.session_state.task_status = None
        except Exception:
            st.error("获取任务进度失败")

    st.divider()
    if st.button("🗑️ 清空对话记忆"):
        st.session_state.messages = []
        st.rerun()
    if st.button("🚪 退出登录"):
        st.session_state.token = None
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

        url = f"{API_BASE_URL}/api/v1/rag/chat?query={prompt}&session_id={st.session_state.session_id}"

        try:
            # 🌟 聊天时带上 Token
            with requests.get(url, headers=headers, stream=True) as response:
                if response.status_code == 401:
                    st.error("⚠️ 登录已过期，请刷新页面重新登录。")
                    st.session_state.token = None
                    st.stop()

                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        text = chunk.decode("utf-8")
                        full_response += text
                        display_text = full_response.split("<<<SOURCES_METADATA>>>")[0]
                        message_placeholder.markdown(display_text + "▌")

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

            message_placeholder.markdown(pure_answer)

            # 渲染引用来源折叠面板
            if sources_data:
                st.markdown("---")
                st.markdown("📚 **本条回答的原文溯源：**")
                for idx, source in enumerate(sources_data):
                    with st.expander(f"📍 第 {source['page']} 页 原文片段"):
                        st.info(source['content'])

            st.session_state.messages.append({"role": "assistant", "content": pure_answer})

        except Exception as e:
            st.error(f"请求失败: {e}")