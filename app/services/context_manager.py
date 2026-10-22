import tiktoken


class ContextBudgetManager:
    def __init__(self, max_total_tokens: int = 6000):
        self.max_total_tokens = max_total_tokens
        self.enc = tiktoken.get_encoding("cl100k_base")  # 兼容 GPT/DeepSeek

    def count_tokens(self, text: str) -> int:
        return len(self.enc.encode(text))

    def truncate_text(self, text: str, max_tokens: int) -> str:
        tokens = self.enc.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.enc.decode(tokens[:max_tokens]) + "... [内容过长已截断]"

    def build_final_context(self, profile: str, summary: str, working: str, retrieved_docs: str) -> tuple[str, str]:
        """根据 Token 预算动态裁剪"""
        # 1. 强制保留的部分（画像和摘要通常很短，给 1000 Token 额度）
        reserved = self.count_tokens(profile) + self.count_tokens(summary)

        # 2. 剩下的预算给：近期对话 (40%) + 检索文档 (60%)
        remaining = self.max_total_tokens - reserved

        if remaining < 1000:
            # 如果基础记忆就把额度吃光了，强制裁剪
            remaining = 2000

        working_budget = int(remaining * 0.4)
        doc_budget = int(remaining * 0.6)

        # 3. 执行截断
        safe_working = self.truncate_text(working, working_budget)
        safe_docs = self.truncate_text(retrieved_docs, doc_budget)

        return safe_working, safe_docs


budget_manager = ContextBudgetManager(max_total_tokens=6000)