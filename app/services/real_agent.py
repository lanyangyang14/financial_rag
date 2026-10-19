import os
from typing import TypedDict, Annotated, Sequence, Literal
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from app.core.config import settings
from app.services.agent_tools import financial_tools


# 1. 升级状态：加入“迭代次数”和“上一次调用的工具”
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    iterations: int  # 🌟 记录思考循环的次数
    last_tool: str  # 🌟 记录上一次调用的工具名


# 2. 初始化大模型并绑定工具
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_BASE_URL,
    temperature=0
).bind_tools(financial_tools)


# 3. 核心思考节点
def agent_reasoning_node(state: AgentState):
    print(f"🧠 [Agent 思考中... 当前迭代: {state.get('iterations', 0)}]")
    messages = state["messages"]
    response = llm.invoke(messages)

    # 累加迭代次数
    current_iter = state.get("iterations", 0) + 1
    return {"messages": [response], "iterations": current_iter}


# 4. 升级路由判断节点：加入防御和熔断机制
def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    messages = state["messages"]
    last_message = messages[-1]
    iterations = state.get("iterations", 0)

    # 🚨 熔断机制 1：最大迭代次数限制（默认 5 次，防止恶意消耗）
    if iterations >= 5:
        print("🚨 [触发熔断] 达到最大迭代次数，强制结束！")
        fallback_msg = AIMessage(
            content="抱歉，我尝试了多次检索，但未能从当前财报中获取足够的信息。为了避免给您错误的数据，我停止了搜索。请尝试换个问法或提供更具体的指标名称。")
        return "__end__"

    # 判断是否要调用工具
    if last_message.tool_calls:
        current_tool = last_message.tool_calls[0]['name']
        current_args = str(last_message.tool_calls[0]['args'])

        # 🚨 熔断机制 2：连续重复调用检测
        # 如果上一次调用的工具和参数完全一样（说明它原地踏步了）
        if state.get("last_tool") == f"{current_tool}_{current_args}":
            print(f"🚨 [触发熔断] 检测到重复调用工具 {current_tool}，强制结束！")
            return "__end__"

        # 记录本次调用的指纹，传给下一轮
        state["last_tool"] = f"{current_tool}_{current_args}"
        print(f"🛠️ [Agent 决定行动]: 调用 {current_tool}")
        return "tools"

    print("✅ [Agent 思考完毕，准备输出最终回答]")
    return "__end__"


# 5. 构建图
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_reasoning_node)
workflow.add_node("tools", ToolNode(financial_tools))

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "__end__": END})
workflow.add_edge("tools", "agent")

# 编译应用
real_agent_app = workflow.compile()