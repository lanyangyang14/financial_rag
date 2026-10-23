import streamlit as st

st.title("📊 数据看板")
st.markdown("了解你的 AI 使用与效率")
st.caption("查看调用趋势、模型用量与最近活动，掌握平台使用情况")

# 用四列展示核心数据（模拟设计图）
col1, col2, col3, col4 = st.columns(4)
col1.metric("模型调用", "700 次", "+12%")
col2.metric("活跃智能体", "9 个", "新增 2 个")
col3.metric("工具调用", "-", "暂无统计")
col4.metric("Token 用量", "1,754,895", "+8%")

st.divider()

# 模拟图表展示区
st.subheader("调用活跃趋势 (近7天)")
# 这里以后会接入真实的 Echarts 或 st.line_chart
import pandas as pd
import numpy as np
chart_data = pd.DataFrame(np.random.randn(7, 1), columns=["调用量"])
st.line_chart(chart_data)