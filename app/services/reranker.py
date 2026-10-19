# app/services/reranker.py
from sentence_transformers import CrossEncoder


class RerankerService:
    def __init__(self):
        print("⏳ 正在加载 BGE-Reranker 模型，首次运行会下载...")
        # 使用智源的 BGE 重排模型
        self.model = CrossEncoder('BAAI/bge-reranker-base')
        print("✅ Reranker 模型加载完成！")

    def rerank(self, query: str, docs: list[dict], top_k: int = 3) -> list[dict]:
        """对召回的结果进行精准重排"""
        if not docs:
            return []

        # 构造 (query, text) 的配对
        pairs = [[query, doc.get("parent_content", "")] for doc in docs]

        # 模型打分
        scores = self.model.predict(pairs)

        # 将分数附加到文档上并排序
        for i, doc in enumerate(docs):
            doc["rerank_score"] = float(scores[i])

        sorted_docs = sorted(docs, key=lambda x: x["rerank_score"], reverse=True)

        print(f"🎯 Rerank 重排完成，最高分: {sorted_docs[0]['rerank_score']:.4f}")
        return sorted_docs[:top_k]


# 全局实例（延迟加载，避免启动太慢）
reranker_service = RerankerService()