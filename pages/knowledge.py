import streamlit as st

st.title("📚 知识库")
st.markdown("管理已上传的财报文档与检索切片。")
st.info("文档上传接口已就绪：POST /api/v1/document/upload 。上传后系统会自动解析并写入 Qdrant / Elasticsearch / Neo4j。")
