import streamlit as st

st.title("🧠 智能体")
st.markdown("构建你的专属 AI 助手")
st.caption("通过自然语言、知识和工具，创建能够执行特定任务的智能体")

# 使用 Tab 切换
tab1, tab2, tab3 = st.tabs(["全部", "我的", "内置"])

with tab1:
    # 模仿卡片布局：两行三列
    col1, col2, col3 = st.columns(3)

    with col1:
        with st.container(border=True):
            st.markdown("### 🔍 深度搜索助手")
            st.caption("围绕复杂问题检索资料，整理观点与参考来源。")
            st.markdown("`DeepSeek V4` | `温度 0.7`")
            st.button("开始对话", use_container_width=True, key="agent1")

    with col2:
        with st.container(border=True):
            st.markdown("### 📄 文档助手")
            st.caption("快速阅读长文档，提炼重点并生成结构化内容。")
            st.markdown("`GPT-4` | `温度 0.1`")
            st.button("开始对话", use_container_width=True, key="agent2")

    with col3:
        with st.container(border=True):
            st.markdown("### 🌤️ 天气助手")
            st.caption("查询城市天气，结合行程给出贴心出行建议。")
            st.markdown("`Qwen` | `联网开启`")
            st.button("开始对话", use_container_width=True, key="agent3")