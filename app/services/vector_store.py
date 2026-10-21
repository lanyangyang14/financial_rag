import uuid
from qdrant_client import QdrantClient
from openai import AsyncOpenAI
from app.core.config import settings
from qdrant_client.models import Filter, FieldCondition, MatchValue, Distance, VectorParams, PointStruct

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
        """初始化纯 Dense 向量集合"""
        # 如果存在旧的混合集合，先删掉（为了干净）
        if self.qdrant.collection_exists(self.collection_name):
            self.qdrant.delete_collection(self.collection_name)

        self.qdrant.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE)
        )
        print(f"✅ 已创建 Qdrant Collection: {self.collection_name}")

    async def get_embedding(self, text: str) -> list[float]:
        response = await self.embed_client.embeddings.create(
            input=[text], model=self.embed_model
        )
        return response.data[0].embedding

    async def insert_chunks(self, chunks: list[dict], document_id: str,user_id:str,chunk_type:str="text"):
        points = []
        for i, chunk in enumerate(chunks):
            child_text = chunk["child_content"]
            dense_vector = await self.get_embedding(child_text)

            payload = {
                "child_content": child_text,
                "parent_content": chunk["parent_content"],
                "page": chunk["metadata"]["page"],
                "source": chunk["metadata"]["source"],
                "document_id": document_id,
                "user_id":user_id,
                "chunk_type":chunk_type
            }

            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}_{chunk['metadata']['page']}_{i}"))

            points.append(
                PointStruct(
                    id=point_id,
                    vector=dense_vector,
                    payload=payload
                )
            )

        if points:
            self.qdrant.upsert(collection_name=self.collection_name, points=points)
            print(f"🚀 成功存入 {len(points)} 个向量切片到 Qdrant！")

    async def search(self, query: str, user_id: str, top_k: int = 5, chunk_type: str = None) -> list[dict]:
        """基础 Dense 检索（支持按用户和类型过滤）"""
        query_vector = await self.get_embedding(query)

        # 1. 构造必选过滤条件：必须属于该用户
        must_conditions = [
            FieldCondition(
                key="user_id",
                match=MatchValue(value=user_id)
            )
        ]

        # 2. 如果传了 chunk_type（比如 "summary"），就追加过滤条件
        if chunk_type:
            must_conditions.append(
                FieldCondition(
                    key="chunk_type",
                    match=MatchValue(value=chunk_type)
                )
            )

        # 3. 统一发起一次检索
        search_result = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=Filter(must=must_conditions),  # 👈 把组装好的条件传进去
            limit=top_k
        )

        # 4. 解析结果
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