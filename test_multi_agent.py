import asyncio
from app.services.real_agent import multi_agent_app
from langchain_core.messages import HumanMessage


async def run():
    # 故意问一个非常容易产生幻觉、或者格式极难的问题
    query = "公司2024年外星人研发投入是多少？"
    print(f"👨‍💻 用户提问：{query}\n" + "=" * 50)

    inputs = {"messages": [HumanMessage(content=query)], "iterations": 0}

    async for event in multi_agent_app.astream(inputs):
        pass  # 具体的打印已经在节点里写了


if __name__ == "__main__":
    asyncio.run(run())