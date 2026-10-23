import streamlit as st
import requests
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001")

st.title("🛠️ 工具")
st.markdown("管理内置工具与自定义能力")
st.caption("连接搜索、文档处理与业务工具，让 AI 完成更多任务")

# 搜索和创建按钮
col1, col2 = st.columns([3, 1])
with col1:
    search_query = st.text_input("搜索工具", placeholder="搜索工具名称、功能或描述...", label_visibility="collapsed")
with col2:
    if st.button("➕ 创建工具", type="primary", use_container_width=True):
        st.info("创建工具功能开发中...")

st.divider()

# 从后端拉取真实数据
headers = {"Authorization": f"Bearer {st.session_state.get('token', '')}"}

try:
    res = requests.get(f"{API_BASE_URL}/api/v1/tools", headers=headers)
    if res.status_code == 200:
        tools_data = res.json()

        # 过滤搜索
        if search_query:
            tools_data = [t for t in tools_data if
                          search_query.lower() in t["name"].lower() or search_query.lower() in t["description"].lower()]

        if not tools_data:
            st.info("暂无可用工具。")
        else:
            # 3列布局渲染
            cols = st.columns(3)
            for idx, tool in enumerate(tools_data):
                with cols[idx % 3]:
                    with st.container(border=True):
                        st.markdown(f"""
                            <div style='display: flex; align-items: flex-start; gap: 12px; margin-bottom: 20px;'>
                                <div style='background-color: #f1f5f9; padding: 12px; border-radius: 8px; font-size: 24px;'>
                                    {tool.get('icon', '🛠️')}
                                </div>
                                <div>
                                    <div style='display: flex; align-items: center; gap: 8px;'>
                                        <h4 style='margin: 0; font-size: 16px;'>{tool['name']}</h4>
                                        <span style='background-color: #e0f2fe; color: #0284c7; font-size: 12px; padding: 2px 8px; border-radius: 12px;'>{tool.get('tag', '通用')}</span>
                                    </div>
                                    <p style='margin: 4px 0 0 0; font-size: 13px; color: #64748b; height: 40px; overflow: hidden;'>{tool['description']}</p>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

                        # 操作栏
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.button("👁️ 查看", key=f"view_{tool['name']}", use_container_width=True)
                        with col_b:
                            st.button("✏️ 编辑", key=f"edit_{tool['name']}", use_container_width=True)
    elif res.status_code == 401:
        st.error("登录过期，请刷新页面重新登录。")
    else:
        st.error(f"获取工具列表失败: {res.text}")
except Exception as e:
    st.error(f"无法连接后端: {e}")