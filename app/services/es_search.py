import os

from elasticsearch import AsyncElasticsearch
from typing import List, Dict, Any


class ESSearchService:
    def __init__(self):
        es_url = os.getenv("ES_URL", "http://127.0.0.1:9200")
        self.client = AsyncElasticsearch(es_url)
        self.index_name = "financial_chunks"

    async def init_index(self):
        """初始化 ES 索引结构"""
        try:
            # 尝试创建，如果不存在就创建
            await self.client.indices.create(
                index=self.index_name,
                mappings={
                    "properties": {
                        "content": {"type": "text"},
                        "page": {"type": "integer"},
                        "document_id": {"type": "keyword"},
                        "parent_content": {"type": "text"},
                        "user_id": {"type": "keyword"}
                    }
                }
            )
            print(f"✅ 已创建 Elasticsearch 索引: {self.index_name}")
        except Exception as e:
            # 如果报错是因为索引已经存在，那就忽略它
            if "resource_already_exists_exception" in str(e):
                print(f"ℹ️ Elasticsearch 索引 {self.index_name} 已存在，跳过创建。")
            else:
                print(f"⚠️ 创建 ES 索引时出错: {e}")

    async def index_chunks(self, chunks: List[Dict[str, Any]], document_id: str,user_id:str,chunk_type:str="text"):
        """将切片批量写入 ES"""
        operations = []
        for i, chunk in enumerate(chunks):
            # ES 的 bulk API 需要交替传入操作类型和数据
            operations.append({"index": {"_index": self.index_name}})
            operations.append({
                "content": chunk["child_content"],
                "page": chunk["metadata"]["page"],
                "document_id": document_id,
                "parent_content": chunk["parent_content"],
                "user_id":user_id,
                "chunk_type":chunk_type
            })

        if operations:
            await self.client.bulk(operations=operations)
            # 强制刷新，让数据立刻可查
            await self.client.indices.refresh(index=self.index_name)
            print(f"🚀 成功存入 {len(chunks)} 个切片到 Elasticsearch！")

    async def search(self, query: str, user_id:str,top_k: int = 5) -> List[Dict[str, Any]]:
        """全文检索：精确匹配关键词"""
        from elasticsearch import NotFoundError
        try:
            res = await self.client.search(
                index=self.index_name,
                query={
                    "bool": {
                        "must": [
                            {"match": {"content": query}}
                        ],
                        "filter": [  # 🌟 ES 的过滤逻辑
                            {"term": {"user_id": user_id}}
                        ]
                    }
                },
                size=top_k
            )
        except NotFoundError:
            # 索引还没建（还没上传过文档），返回空结果，不影响其他检索路径
            print(f"ℹ️ ES 索引 {self.index_name} 不存在（尚未上传文档），跳过关键词检索")
            return []

        results = []
        for hit in res["hits"]["hits"]:
            results.append({
                "score": hit["_score"],
                "page": hit["_source"]["page"],
                "parent_content": hit["_source"]["parent_content"],
                "document_id": hit["_source"]["document_id"]
            })
        return results


# 全局实例
#es_service = ESSearchService()