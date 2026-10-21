import httpx
import os


class RerankerService:
    def __init__(self):
        # 在 Docker 内部调用容器名 reranker-service，在本地测试调用 localhost:8080
        self.api_url = os.getenv("RERANKER_URL", "http://localhost:8080/rerank")

    def rerank(self, query: str, docs: list[dict], top_k: int = 3) -> list[dict]:
        if not docs:
            return []

        texts = [doc.get("parent_content", "") for doc in docs]

        # 构造 TEI 要求的请求体
        payload = {
            "query": query,
            "texts": texts,
            "raw_scores": False,  # 返回 0-1 的归一化分数
            "truncate": True
        }

        try:
            # 同步请求（因为 LangGraph/Celery 任务里可以直接用）
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.api_url, json=payload)
                response.raise_for_status()
                results = response.json()

            # 解析结果并重排
            scored_docs = []
            for idx, item in enumerate(results):
                doc = docs[item["index"]]
                doc["rerank_score"] = item["score"]
                scored_docs.append(doc)

            sorted_docs = sorted(scored_docs, key=lambda x: x["rerank_score"], reverse=True)
            print(f"🎯 分布式 Rerank 完成，最高分: {sorted_docs[0]['rerank_score']:.4f}")
            return sorted_docs[:top_k]

        except Exception as e:
            # 🌟 企业级容错：如果重排服务挂了，直接返回原始顺序的前 top_k 个
            print(f"⚠️ Rerank 服务调用失败，降级为直接返回: {e}")
            return docs[:top_k]


# 全局实例
reranker_service = RerankerService()