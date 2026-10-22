import json
from functools import wraps
from langchain_core.tools import tool
from app.core.database import SessionLocal
from app.models.db_models import AgentExperience
from app.services.vector_store import vector_store
from app.services.es_search import ESSearchService
from app.services.graph_service import graph_service

# ================= 1. 先定义装饰器 =================
def record_experience(tool_func):
    """🌟 程序性记忆装饰器：自动记录工具报错"""
    @wraps(tool_func)
    async def wrapper(*args, **kwargs):
        try:
            # 正常执行工具
            return await tool_func(*args, **kwargs)
        except Exception as e:
            error_str = str(e)
            print(f"⚠️ [程序性记忆] 捕获到工具 {tool_func.__name__} 报错: {error_str}")

            # 写入 PostgreSQL 错题本
            db = SessionLocal()
            try:
                exp = AgentExperience(
                    tool_name=tool_func.__name__,
                    input_args=json.dumps(kwargs, ensure_ascii=False),
                    error_message=error_str,
                    fix_strategy="系统暂未自动修复，请检查输入参数"
                )
                db.add(exp)
                db.commit()
            except Exception as db_err:
                print(f"写入错题本失败: {db_err}")
            finally:
                db.close()

            # 把原始错误抛给 LangGraph，让它触发熔断或重试
            raise e
    return wrapper

# ================= 2. 再定义工具并使用装饰器 =================

@tool
async def search_financial_vectors(query: str, user_id: str = "user_001") -> str:
    """当用户询问财报中的具体概念、业务描述、战略规划时，使用此工具进行语义检索。"""
    docs = await vector_store.search(query, user_id=user_id, top_k=3)
    return "\n".join([d["parent_content"] for d in docs])

@tool
@record_experience  # 🌟 穿上装甲
async def search_financial_keywords(query: str, user_id: str = "user_001") -> str: # 🌟 补上了默认参数
    """当用户询问具体的财务数字（如收入、利润、股息率）或特定年份时，使用此工具进行精确匹配。"""
    es = ESSearchService()
    docs = await es.search(query, user_id=user_id, top_k=3)
    return "\n".join([d["parent_content"] for d in docs])

@tool
def calculate_math(expression: str) -> str:
    """当需要进行数学计算（如计算增长率、汇率换算）时，使用此工具。输入必须是纯数学表达式，如 '4.5 * 0.91'。"""
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"

# ================= 3. 打包工具 =================
financial_tools = [search_financial_vectors, search_financial_keywords, calculate_math]