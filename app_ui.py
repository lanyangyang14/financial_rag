import streamlit as st
import os
import requests
import json
import time

# ================= 页面基础配置 =================
st.set_page_config(
    page_title="Financial Agent Chat",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)
# 多页面导航统一由 st.navigation() 接管（不能传空列表，Streamlit 会直接报错）
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001")

# ================= 定义多页面路由 =================
# 🌟 必须在登录判断之前调用 st.navigation，否则未登录时 st.stop() 会让本次运行跳过它，
# Streamlit 就会回退到 pages/ 目录自动生成的英文导航
page_explore = st.Page("pages/explore.py", title="探索", icon="🔍")
page_chat = st.Page("pages/chat.py", title="会话", icon="💬")
page_agents = st.Page("pages/agent.py", title="智能体", icon="🧠")
page_mcp = st.Page("pages/mcp.py", title="MCP", icon="🔗")
page_models = st.Page("pages/models.py", title="模型", icon="📦")
page_knowledge = st.Page("pages/knowledge.py", title="知识库", icon="📚")
page_dashboard = st.Page("pages/dashboard.py", title="数据看板", icon="📊")
page_tools = st.Page("pages/tools.py", title="工具", icon="🛠️")

pg = st.navigation({
    "工作台": [page_explore, page_chat],
    "AI 能力": [page_agents, page_mcp, page_models],
    "知识与数据": [page_knowledge, page_dashboard],
    "效率工具": [page_tools]
})

# ================= 全局登录状态检查 =================
if "token" not in st.session_state:
    st.session_state.token = None

if st.session_state.token is None:
    st.markdown("<h2 style='text-align: center; margin-top: 100px;'>🔐 欢迎来到 Financial Agent</h2>",
                unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        # 🌟 用 st.form 一次性提交所有字段，避免点击按钮时输入框的值还没同步过去
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", use_container_width=True, type="primary")

        if submitted:
            try:
                # 用 params 传参，requests 负责 URL 编码
                res = requests.post(f"{API_BASE_URL}/api/v1/auth/login",
                                    params={"username": username, "password": password})
                if res.status_code == 200:
                    data = res.json()
                    st.session_state.token = data["access_token"]
                    st.session_state.refresh_token = data["refresh_token"]
                    st.rerun()
                else:
                    st.error("❌ 账号或密码错误")
            except Exception as e:
                st.error(f"连接后端失败: {e}")
    st.stop()  # 没登录成功，停止渲染后面的导航

# ================= 侧边栏：Logo 与 导航 (还原设计图) =================
with st.sidebar:
    # 1. 顶部 Logo 区（我把这里改得更像商业软件了）
    st.markdown("""
        <div style='display: flex; align-items: center; margin-bottom: 20px; padding: 10px;'>
            <div style='width: 40px; height: 40px; background: linear-gradient(135deg, #3b82f6, #06b6d4); border-radius: 12px; display: flex; justify-content: center; align-items: center; color: white; font-size: 24px; margin-right: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);'>
                🤖
            </div>
            <div>
                <h2 style='margin: 0; font-size: 20px; color: #1e293b; font-weight: 700;'>Financial Agent</h2>
                <p style='margin: 0; font-size: 12px; color: #64748b;'>AI 生产力平台</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    st.divider()

pg.run()