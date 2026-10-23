import streamlit as st
import pandas as pd
import requests
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001")
headers = {"Authorization": f"Bearer {st.session_state.get('token', '')}"}

st.title("📦 模型")
st.markdown("管理你的 AI 模型服务")
st.caption("连接大语言模型与向量模型，统一管理模型服务与接口配置")

# 添加模型的表单
with st.expander("➕ 添加新模型", expanded=False):
    with st.form("add_model_form"):
        col1, col2 = st.columns(2)
        m_name = col1.text_input("模型标识 (如 deepseek-chat, gpt-4o)")
        m_provider = col2.text_input("服务商 (如 DeepSeek, OpenAI)")
        m_type = col1.selectbox("模型类型", ["对话模型", "向量模型"])
        m_url = col2.text_input("接口地址", "https://api.deepseek.com")
        m_key = st.text_input("API Key", type="password")

        if st.form_submit_button("提交保存"):
            res = requests.post(f"{API_BASE_URL}/api/v1/models", headers=headers, json={
                "model_name": m_name, "provider": m_provider,
                "model_type": m_type, "base_url": m_url, "api_key": m_key
            })
            if res.status_code == 200:
                st.success("添加成功！请刷新页面。")
                st.rerun()
            else:
                st.error(f"添加失败: {res.text}")

# 列表展示逻辑 (保留你之前的 Tab 渲染逻辑即可)