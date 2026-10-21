import re


class QueryRouter:
    def __init__(self):
        pass

    def route(self, query: str) -> str:
        """
        判断用户意图，返回路由类型：
        - 'direct': 闲聊，直接回答
        - 'macro_summary':概括
        - 'keyword': 精确数字/专有名词，走 ES
        - 'semantic': 概念语义，走向量
        - 'hybrid': 复杂问题，三路并发
        """
        q = query.strip()

        # 1. 闲聊或极度简单的问题（字数很少且没有业务词）
        if len(q) < 5 or any(w in q for w in ["你好", "你是谁", "谢谢"]):
            return "direct"
        macro_words = ["总结", "概括", "整体情况", "宏观", "核心要点", "全貌", "归纳"]
        if any(w in q for w in macro_words):
            return "macro_summary"

        # 2. 包含明显数字、年份、财务指标的，走精确匹配 (ES)
        # 比如问 "2024年收入", "172,446" 等
        has_number = bool(re.search(r'\d+', q))
        money_words = ["收入", "利润", "股息", "毛利", "资产", "负债", "现金流"]

        if has_number and any(w in q for w in money_words):
            return "keyword"

        # 3. 包含明显的逻辑关系词，走图谱或混合
        relation_words = ["对比", "为什么", "原因", "关系", "子公司", "上下游", "影响"]
        if any(w in q for w in relation_words):
            return "hybrid"

        # 4. 其他长句默认走向量语义检索
        return "semantic"


router = QueryRouter()