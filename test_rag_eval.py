import asyncio
from app.services.evaluator import evaluator
from app.services.rag_chain import rag_chain


async def main():
    # 1. 准备黄金测试集（问题 + 人工核对过的标准答案）
    golden_dataset = [
        {
            "question": "公司建议派发多少港元股息？",
            "ground_truth": "公司建议派发截至二零二四年十二月三十一日止年度的末期股息每股4.50港元。"
        },
        {
            "question": "公司2024年的收入是多少？",
            "ground_truth": "根据财报，截至二零二四年十二月三十一日止三个月的收入为人民币172,446百万元。"
        }
    ]

    test_data = []

    print("🚀 正在对当前 RAG 系统进行自动化压测...")
    for item in golden_dataset:
        question = item["question"]
        ground_truth = item["ground_truth"]

        # 调用我们之前的 RAG 系统生成答案，并获取上下文
        # (这里为了测试，我们不流式输出，直接拿最终结果)
        full_response = ""
        contexts = []

        # 模拟获取系统和上下文
        async for chunk in rag_chain.generate_answer(question, session_id="eval_test"):
            full_response += chunk
            # 拦截我们之前埋的元数据，提取上下文
            if "<<<SOURCES_METADATA>>>" in chunk:
                import json
                meta_str = chunk.split("<<<SOURCES_METADATA>>>")[1].replace("<<<END_METADATA>>>", "")
                sources = json.loads(meta_str).get("sources", [])
                contexts = [s["content"] for s in sources]

        # 去掉回答中的元数据标记
        pure_answer = full_response.split("<<<SOURCES_METADATA>>>")[0].strip()

        test_data.append({
            "question": question,
            "answer": pure_answer,
            "contexts": contexts,
            "ground_truth": ground_truth
        })
        print(f"✅ 已生成用例：{question}")

    # 2. 把生成的用例丢给裁判打分
    await evaluator.run_evaluation(test_data)


if __name__ == "__main__":
    asyncio.run(main())