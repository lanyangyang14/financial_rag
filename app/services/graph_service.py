import os
from app.core.config import settings as app_settings  # 👈 必须放在 os.environ 之前

# 🌟 核心：在引入任何 openai 相关模块前，强行塞入假 Key 和环境变量
os.environ["OPENAI_API_KEY"] = "ollama"
os.environ["OPENAI_BASE_URL"] = f"{app_settings.OLLAMA_BASE_URL}/v1"

from llama_index.core import PropertyGraphIndex, Settings, Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.llms.openai_like import OpenAILike
from llama_index.embeddings.openai import OpenAIEmbedding
class GraphService:
    def __init__(self):
        self.graph_store = Neo4jPropertyGraphStore(
            username=app_settings.NEO4J_USER,
            password=app_settings.NEO4J_PASSWORD,
            url=app_settings.NEO4J_URL,
        )

        self.llm = OpenAILike(
            model="deepseek-chat",
            api_base=app_settings.DEEPSEEK_BASE_URL,
            api_key=app_settings.DEEPSEEK_API_KEY,
            is_chat_model=True,
            temperature=0.1,
            timeout=60
        )

        # 配置本地的 Ollama 作为 Embedding
        self.embed_model = OpenAIEmbedding(
            model_name="nomic-embed-text",
            api_base=f"{app_settings.OLLAMA_BASE_URL}/v1",
            api_key="ollama",
            dimensions=768
        )

        self.splitter = SentenceSplitter(chunk_size=500, chunk_overlap=50)

        Settings.llm = self.llm
        Settings.embed_model = self.embed_model
        Settings.node_parser = self.splitter

    def extract_and_store(self, text_content: str):
        print("🕸️ [GraphRAG] 开始抽取实体关系，这可能会消耗一些时间...")
        try:
            # 去掉了 embed_model="local"
            index = PropertyGraphIndex.from_documents(
                [Document(text=text_content)],
                property_graph_store=self.graph_store,
                llm=self.llm,
                embed_model=self.embed_model,  # 👈 显式传入
                show_progress=True,
            )
            print("✅ [GraphRAG] 实体关系抽取并存入 Neo4j 完成！")
            return True
        except Exception as e:
            print(f"❌ [GraphRAG] 抽取失败: {e}")
            return False

    def graph_search(self, query: str) -> str:
        """从 Neo4j 中检索相关的图谱上下文"""
        try:
            # 从已有的图谱库加载索引
            index = PropertyGraphIndex.from_existing(
                property_graph_store=self.graph_store,
                llm=self.llm,
                embed_model=self.embed_model
            )
            # 使用图谱检索器
            retriever = index.as_retriever(include_text=True)
            nodes = retriever.retrieve(query)

            # 拼接成文本
            context = ""
            for node in nodes:
                context += f"{node.text}\n"
            return context
        except Exception as e:
            print(f"⚠️ 图谱检索失败: {e}")
            return ""

graph_service = GraphService()