import streamlit as st

st.title("🔍 探索")
st.markdown("欢迎使用 **Financial Agent** —— 你的智能财务分析工作台。")

col1, col2, col3 = st.columns(3)
with col1:
    with st.container(border=True):
        st.markdown("### 💬 会话")
        st.caption("选择模型后直接提问，支持流式回答与原文溯源。")
with col2:
    with st.container(border=True):
        st.markdown("### 📚 知识库")
        st.caption("上传财报 PDF，系统会自动切分并写入检索库。")
with col3:
    with st.container(border=True):
        st.markdown("### 📊 数据看板")
        st.caption("查看模型调用趋势与平台使用情况。")

st.divider()
st.info("提示：先在「模型」页确认模型配置可用，再前往「会话」页开始提问。")
