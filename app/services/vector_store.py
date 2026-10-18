import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from openai import AsyncOpenAI
from app.core.config import settings


class VectorStoreManager:
    def __init__(self):
        self.qdrant = QdrantClient(url=settings.QDRANT_URL)
        self.embed_client = AsyncOpenAI(
            api_key="ollama",
            base_url=f"{settings.OLLAMA_BASE_URL}/v1"
        )
        self.embed_model = "nomic-embed-text"
        self.collection_name = "financial_reports"
        self.vector_size = 768

    def init_collection(self):
        collections = self.qdrant.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
            print(f"✅ 已创建 Qdrant Collection: {self.collection_name}")
        else:
            print(f"ℹ️ Qdrant Collection 已存在: {self.collection_name}")

    async def get_embedding(self, text: str) -> list[float]:
        response = await self.embed_client.embeddings.create(
            input=[text],
            model=self.embed_model
        )
        return response.data[0].embedding

    async def insert_chunks(self, chunks: list[dict], document_id: str):
        points = []
        for i, chunk in enumerate(chunks):
            child_text = chunk["child_content"]
            vector = await self.get_embedding(child_text)

            payload = {
                "child_content": child_text,
                "parent_content": chunk["parent_content"],
                "page": chunk["metadata"]["page"],
                "source": chunk["metadata"]["source"],
                "document_id": document_id
            }

            # 生成符合 Qdrant 规范的 UUID
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}_{chunk['metadata']['page']}_{i}"))

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload
                )
            )

        if points:
            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=points
            )
            print(f"🚀 成功存入 {len(points)} 个向量切片！")

    async def search(self, query: str, top_k: int = 3) -> list[dict]:
        """根据用户提问检索最相关的切片"""
        # 1. 把用户的提问变成向量
        query_vector = await self.get_embedding(query)

        # 2. 去 Qdrant 里找最相似的 top_k 个
        search_result = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k
        )

        # 3. 提取我们需要的信息
        results = []
        for hit in search_result.points:
            results.append({
                "score": hit.score,
                "page": hit.payload.get("page"),
                "parent_content": hit.payload.get("parent_content"),
                "source": hit.payload.get("source")
            })
        return results

vector_store = VectorStoreManager()