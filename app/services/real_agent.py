import json
from typing import TypedDict, Annotated, Sequence, Literal
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from app.core.config import settings
from app.services.agent_tools import financial_tools


# ================= 1. 定义复杂的状态机（共享黑板） =================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    research_data: str  # 🌟 共享黑板：存放执行者查到的原始数据
    feedback: str  # 🌟 共享黑板：存放审查者的修改意见
    iterations: int  # 防止死循环
    next_actor: str  # 决定下一个谁上场


# ================= 2. 初始化带工具的大模型 =================
# 只有 Executor 拥有工具权限，主管和审查者只有大脑
base_llm = ChatOpenAI(model="deepseek-chat", api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL,
                      temperature=0)
llm_with_tools = base_llm.bind_tools(financial_tools)


# ================= 3. 核心节点定义 =================

def supervisor_node(state: AgentState):
    """👑 主管节点：统筹全局，决定何时结束，并带有防死循环熔断"""
    print("👑 [Supervisor 正在统筹全局...]")

    # 🌟 核心修复 1：最大迭代次数限制（强制熔断）
    iterations = state.get("iterations", 0)
    if iterations >= 5:
        print(f"🚨 [触发熔断] 迭代次数达到 {iterations}，Agent 陷入死循环！强制终止。")
        # 既然查不到，给用户一个体面的兜底回答
        fallback_answer = "抱歉，经过多次检索和核实，当前的财报库中未能找到足够的信息来准确回答您的问题。请尝试提供更精确的财务指标或检查文档是否已成功上传入库。"
        return {
            "messages": [AIMessage(content=fallback_answer)],
            "next_actor": "END"
        }

    messages = state["messages"]

    # 🌟 核心修复 2：判断是否已经 PASS
    if not state.get("feedback"):
        return {"next_actor": "executor"}

    if "PASS" in state.get("feedback", ""):
        print("✅ [Supervisor 收到 PASS 批准，准备输出]")
        return {"next_actor": "END"}
    else:
        print(f"⚠️ [Supervisor 收到 Critic 修改建议，打回给 Executor (当前迭代: {iterations})]")
        return {"next_actor": "executor"}
def executor_node(state: AgentState):
    """🛠️ 执行者节点：调工具，干活"""
    print("🛠️ [Executor 正在查阅财报并提取数据...]")
    messages = state["messages"]

    sys_prompt = SystemMessage(content="""你是一个底层财务数据提取员。请根据用户的需求或审查者的反馈，使用你的工具（查向量/查关键词）获取最准确的数据。
你只需输出你查到的核心数据和引用的页码，不要做多余的分析。""")

    response = llm_with_tools.invoke([sys_prompt] + list(messages))

    # 把查到的核心数据存入共享黑板
    return {
        "messages": [response],
        "research_data": response.content,
        "next_actor": "critic",
        "iterations": state.get("iterations", 0) + 1
    }


def critic_node(state: AgentState):
    """🧐 审查者节点：结构化的冲突仲裁"""
    print("🧐 [Critic 正在对数据做合规与准确性审查...]")
    research_data = state.get("research_data", "")
    user_query = state["messages"][0].content

    prompt = f"""你是极其严苛的首席财务审查员。
用户的问题是：{user_query}
执行者查到的数据是：{research_data}

请审查该数据是否准确回答了问题、是否包含页码。
你必须输出纯 JSON 格式（不要 Markdown 标记）：
{{
    "result": "PASS" 或 "REJECT",
    "reason": "如果打回，说明缺了什么数据；如果通过，说明理由",
    "final_answer": "如果 PASS，请直接写出给用户的最终格式化回答（含引用页码）"
}}
"""
    response = base_llm.invoke([SystemMessage(content=prompt)])

    # 解析审查结果
    try:
        res_json = json.loads(response.content)
        result = res_json.get("result")
        reason = res_json.get("reason")
        final_answer = res_json.get("final_answer", "")
    except:
        # 兜底：如果大模型不按 JSON 输出
        result = "PASS"
        reason = "解析失败，默认通过"
        final_answer = research_data

    print(f"   └─ 裁决结果: {result} | 理由: {reason}")

    # 如果通过，把最终回答塞进 messages；如果打回，把反馈存入黑板
    messages = []
    if result == "PASS":
        messages.append(AIMessage(content=final_answer))

    return {
        "messages": messages,
        "feedback": f"{result}: {reason}",
        "next_actor": "supervisor"
    }


# ================= 4. 构建图网络 =================
def route_supervisor(state: AgentState) -> Literal["executor", "__end__"]:
    if state.get("next_actor") == "END":
        return "__end__"
    return "executor"


def route_executor(state: AgentState) -> Literal["tools", "critic"]:
    # 如果执行者决定调用工具，去 tools 节点；否则直接去审查者
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return "critic"


workflow = StateGraph(AgentState)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("executor", executor_node)
workflow.add_node("critic", critic_node)
workflow.add_node("tools", ToolNode(financial_tools))  # 🌟 真正执行工具的地方

workflow.set_entry_point("supervisor")

workflow.add_conditional_edges("supervisor", route_supervisor, {"executor": "executor", "__end__": END})
workflow.add_conditional_edges("executor", route_executor, {"tools": "tools", "critic": "critic"})
workflow.add_edge("tools", "executor")  # 工具执行完，把结果还给执行者
workflow.add_edge("critic", "supervisor")  # 审查完，交还主管决定生死

multi_agent_app = workflow.compile()