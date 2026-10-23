import os
import importlib
from app.core.database import SessionLocal
from app.models.db_models import UserTool


class ToolRegistry:
    def __init__(self):
        # 🌟 核心修复：确保这两个变量名在这里被明确定义
        self.built_in_tools = []
        self.built_in_metadata = []

        # 启动时自动扫描 app/tools/ 目录
        self.scan_and_load()

    def scan_and_load(self):
        """扫描 app/tools 目录，动态加载所有插件工具"""
        tools_dir = os.path.join(os.path.dirname(__file__), "..", "tools")
        self.built_in_tools = []
        self.built_in_metadata = []

        if not os.path.exists(tools_dir):
            print(f"⚠️ 工具目录不存在: {tools_dir}")
            return

        for folder_name in os.listdir(tools_dir):
            folder_path = os.path.join(tools_dir, folder_name)
            # 过滤掉 __pycache__ 和非文件夹
            if os.path.isdir(folder_path) and not folder_name.startswith("__"):
                try:
                    # 动态导入模块
                    module = importlib.import_module(f"app.tools.{folder_name}.action")

                    # 遍历模块里所有的 LangChain Tool 对象
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        # 判断是否是 Tool 对象（有 name 和 description 属性）
                        if hasattr(attr, "name") and hasattr(attr, "description") and hasattr(attr, "invoke"):
                            self.built_in_tools.append(attr)

                            # 生成前端需要的元数据
                            self.built_in_metadata.append({
                                "name": attr.name,
                                "description": attr.description,
                                "tag": "财务检索" if "financial" in folder_name else "通用工具",
                                "icon": "🔍" if "search" in attr.name else "🛠️",
                                "status": "active"
                            })
                except Exception as e:
                    print(f"⚠️ 加载工具插件 {folder_name} 失败: {e}")

        print(f"✅ 成功加载 {len(self.built_in_tools)} 个内置工具插件！")

    def get_all_tools(self, user_id: str = None):
        """返回供 LangChain / Agent 使用的工具对象列表"""
        # 基础返回内置工具
        tools = self.built_in_tools.copy()

        # 🌟 进阶：如果你以后想支持数据库中用户自定义的 OpenAPI 工具，可以在这里动态解析
        # db = SessionLocal()
        # try:
        #     db_tools = db.query(UserTool).filter(UserTool.user_id == user_id).all()
        #     # 将 db_tools 解析成 LangChain Tool 追加到 tools
        # finally:
        #     db.close()

        return tools

    def get_metadata(self, user_id: str = None):
        """返回给前端展示的 JSON 列表（带多租户隔离）"""
        if not user_id:
            return self.built_in_metadata

        all_metadata = self.built_in_metadata.copy()

        # 🌟 核心业务：从数据库拉取用户自己创建的工具，展示到前端
        db = SessionLocal()
        try:
            user_db_tools = db.query(UserTool).filter(UserTool.user_id == user_id).all()
            for t in user_db_tools:
                all_metadata.append({
                    "name": t.tool_name,
                    "description": t.description,
                    "tag": "用户自定义",
                    "icon": "👤",
                    "status": "active"
                })
        except Exception as e:
            print(f"⚠️ 获取用户自定义工具失败: {e}")
        finally:
            db.close()

        return all_metadata


# 🌟 全局单例
tool_registry = ToolRegistry()