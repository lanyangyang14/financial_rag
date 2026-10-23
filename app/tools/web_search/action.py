import os
from langchain_core.tools import tool
from tavily import TavilyClient


@tool
def search_web(query: str) -> str:
    """当用户询问实时新闻、外部事件、或者是当前日期之后的信息时，使用此工具进行互联网搜索。"""
    api_key = os.getenv("TAVILY_API_KEY", "tvly-你的真实API_KEY")
    if not api_key or api_key.startswith("tvly-你的"):
        return "搜索失败：请先在 .env 中配置真实的 TAVILY_API_KEY。"

    try:
        client = TavilyClient(api_key=api_key)
        # 执行搜索并限制返回 3 条结果
        response = client.search(query=query, search_depth="basic", max_results=3)

        # 组装成清晰的结构返回给大模型
        results = response.get("results", [])
        if not results:
            return "未搜索到相关结果。"

        formatted_results = []
        for idx, res in enumerate(results):
            formatted_results.append(f"来源[{idx + 1}] {res['title']}:\n{res['content']}")

        return "\n\n".join(formatted_results)
    except Exception as e:
        return f"搜索发生错误: {str(e)}"