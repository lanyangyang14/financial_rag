# app/services/fusion.py

def reciprocal_rank_fusion(results_list: list[list[dict]], weights: list[float] = None, k: int = 60) -> list[dict]:
    """
    RRF 算法（支持动态权重）
    :param results_list: 多路检索的结果列表
    :param weights: 每一路的权重，如 [1.0, 0.5] 表示第一路更重要
    :param k: 平滑常数
    """
    if weights is None:
        weights = [1.0] * len(results_list)

    fused_scores = {}
    content_map = {}

    for idx, results in enumerate(results_list):
        weight = weights[idx]
        for rank, doc in enumerate(results):
            doc_id = doc.get("parent_content", "")[:100] + str(doc.get("page"))

            if doc_id not in fused_scores:
                fused_scores[doc_id] = 0
                content_map[doc_id] = doc

            # 🌟 核心修改：在原本的 RRF 分数上乘上这一路的权重
            fused_scores[doc_id] += weight * (1 / (k + rank + 1))

    sorted_docs = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    return [content_map[doc_id] for doc_id, _ in sorted_docs]