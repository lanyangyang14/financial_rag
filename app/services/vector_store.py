import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    SparseVectorParams, SparseVector,
    Prefetch, FusionQuery, Fusion
)
from openai import AsyncOpenAI
from app.core.config import settings
from qdrant_client.models import Document, SparseVector


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
        """初始化包含 Dense 和 Sparse 双向量的集合（如果存在则不操作）"""
        if not self.qdrant.collection_exists(self.collection_name):
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": VectorParams(size=self.vector_size, distance=Distance.COSINE)
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams()
                }
            )
            print(f"✅ 已创建混合检索 Collection: {self.collection_name}")
        else:
            print(f"ℹ️ Collection {self.collection_name} 已存在。")
    async def get_embedding(self, text: str) -> list[float]:
        response = await self.embed_client.embeddings.create(
            input=[text], model=self.embed_model
        )
        return response.data[0].embedding

    def _get_sparse_vector(self, text: str) -> SparseVector:
        """
        简易版稀疏向量生成器：提取文本中的字符并统计词频。
        生产环境中这里通常用 BM25 算法或专门的 Sparse 模型（如 BGE-M3）
        """
        # 简单按字符分割，统计频率（适合中文）
        words = [char for char in text if not char.isspace()]
        word_counts = {}
        for w in words:
            word_counts[w] = word_counts.get(w, 0) + 1

        indices = [hash(k) % 1000000 for k in word_counts.keys()]  # 模拟索引
        values = [float(v) for v in word_counts.values()]
        return SparseVector(indices=indices, values=values)

    async def insert_chunks(self, chunks: list[dict], document_id: str):
        points = []
        for i, chunk in enumerate(chunks):
            child_text = chunk["child_content"]

            # 1. 生成 Dense 向量
            dense_vector = await self.get_embedding(child_text)
            # 2. 生成 Sparse 向量
            sparse_vector = self._get_sparse_vector(child_text)

            payload = {
                "child_content": child_text,
                "parent_content": chunk["parent_content"],
                "page": chunk["metadata"]["page"],
                "source": chunk["metadata"]["source"],
                "document_id": document_id
            }

            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}_{chunk['metadata']['page']}_{i}"))

            points.append(
                PointStruct(
                    id=point_id,
                    vector={
                        # 强制转换为标准向量格式，指定名字
                        "dense": dense_vector,
                        "sparse": SparseVector(
                            indices=sparse_vector.indices,
                            values=sparse_vector.values
                        )
                    },
                    payload=payload
                )
            )

        if points:
            self.qdrant.upsert(collection_name=self.collection_name, points=points)
            print(f"🚀 成功存入 {len(points)} 个混合向量切片！")

    async def search(self, query: str, top_k: int = 3) -> list[dict]:
        """使用 RRF 融合的混合检索"""
        query_dense = await self.get_embedding(query)
        query_sparse = self._get_sparse_vector(query)

        # 🌟 核心：混合检索 + RRF 融合
        response = self.qdrant.query_points(
            collection_name=self.collection_name,
            prefetch=[
                Prefetch(query=query_dense, using="dense", limit=10),  # 稠密检索拿前10
                Prefetch(query=query_sparse, using="sparse", limit=10)  # 稀疏检索拿前10
            ],
            query=FusionQuery(fusion=Fusion.RRF),  # 使用倒数排名融合
            limit=top_k
        )

        results = []
        for hit in response.points:
            results.append({
                "score": hit.score,
                "page": hit.payload.get("page"),
                "parent_content": hit.payload.get("parent_content"),
                "source": hit.payload.get("source")
            })
        return results


vector_store = VectorStoreManager()