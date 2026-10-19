import json
from app.services.llm_client import get_llm_client


class RAGEvaluator:
    def __init__(self):
        self.llm = get_llm_client("deepseek")

    async def evaluate_single(self, question: str, answer: str, contexts: list[str], ground_truth: str) -> dict:
        """让 DeepSeek 充当裁判，对单条数据进行打分"""
        context_str = "\n\n".join(contexts)

        prompt = f"""你是一个严苛的 AI 评估专家。请根据以下信息，对 AI 助手的回答进行打分。
每一项打分范围是 0 到 10 分（0为最差，10为完美）。

【用户问题】：
{question}

【标准答案 (Ground Truth)】：
{ground_truth}

【系统检索到的上下文】：
{context_str}

【AI 助手的回答】：
{answer}

请严格评估以下三个指标：
1. 忠实度 (Faithfulness)：AI 的回答是否完全基于上下文？有没有捏造上下文中不存在的事实？（如果有幻觉，打 0-3 分）
2. 答案相关性 (Answer Relevance)：AI 的回答是否直接切中了用户的问题？（答非所问打 0-3 分）
3. 上下文精确度 (Context Precision)：检索到的上下文是否包含了回答该问题所需的信息？（如果完全没有相关信息，打 0-3 分）

你必须只返回一个 JSON 格式的结果，不要包含任何其他废话：
{{
    "faithfulness": <分数>,
    "answer_relevancy": <分数>,
    "context_precision": <分数>,
    "reason": "<简短的评估理由>"
}}
"""
        try:
            # 调用大模型
            response = await self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}  # 强制返回 JSON
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"❌ 评测单条数据失败: {e}")
            return {"faithfulness": 0, "answer_relevancy": 0, "context_precision": 0, "reason": "解析失败"}

    async def run_evaluation(self, test_dataset: list[dict]):
        """执行整套评测并计算平均分"""
        print("⏳ 正在使用 DeepSeek 裁判进行系统体检...\n")

        total_faith = 0
        total_relev = 0
        total_prec = 0
        count = len(test_dataset)

        for idx, item in enumerate(test_dataset):
            print(f"正在评估用例 {idx + 1}/{count}: {item['question']}")
            result = await self.evaluate_single(
                question=item["question"],
                answer=item["answer"],
                contexts=item["contexts"],
                ground_truth=item["ground_truth"]
            )

            print(f"  └─ 理由: {result.get('reason', '无')}")
            total_faith += result.get("faithfulness", 0)
            total_relev += result.get("answer_relevancy", 0)
            total_prec += result.get("context_precision", 0)

        print("\n" + "=" * 40)
        print("📊 RAG 系统体检报告 (满分 10 分)")
        print("=" * 40)
        print(f"🎯 平均忠实度 (有没有瞎编): {total_faith / count:.2f} / 10")
        print(f"🎯 平均答案相关性 (有没有答非所问): {total_relev / count:.2f} / 10")
        print(f"🎯 平均上下文精确度 (搜的准不准): {total_prec / count:.2f} / 10")
        print("=" * 40 + "\n")


evaluator = RAGEvaluator()