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
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        url = f"http://127.0.0.1:8001/api/v1/rag/chat?query={prompt}&session_id={st.session_state.session_id}"

        try:
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        text = chunk.decode("utf-8")
                        full_response += text

                        # 如果包含元数据标记，先不显示元数据部分
                        display_text = full_response.split("<<<SOURCES_METADATA>>>")[0]
                        message_placeholder.markdown(display_text + "▌")

            # 流式结束，解析元数据
            pure_answer = full_response
            sources_data = []

            if "<<<SOURCES_METADATA>>>" in full_response:
                parts = full_response.split("<<<SOURCES_METADATA>>>")
                pure_answer = parts[0].strip()
                meta_str = parts[1].replace("<<<END_METADATA>>>", "")
                try:
                    meta_json = json.loads(meta_str)
                    sources_data = meta_json.get("sources", [])
                except:
                    pass

            # 渲染最终纯文本回答
            message_placeholder.markdown(pure_answer)

            # 🌟 渲染引用来源折叠面板
            if sources_data:
                st.markdown("---")
                st.markdown("📚 **本条回答的原文溯源：**")
                for idx, source in enumerate(sources_data):
                    with st.expander(f"📍 第 {source['page']} 页 原文片段"):
                        st.info(source['content'])

            st.session_state.messages.append({"role": "assistant", "content": pure_answer})

        except Exception as e:
            st.error(f"请求失败: {e}")