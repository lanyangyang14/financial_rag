import base64
import requests
import os

class VisionService:
    def __init__(self):
        # 🌟 修复：容器内访问宿主机 Ollama 要用 host.docker.internal，从环境变量读取
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.ollama_url = base + "/api/generate"
        self.model = "llava"

    def parse_complex_pdf_image(self, image_path: str, is_formula_or_table: bool = True) -> str:
        """调用多模态模型，专门针对财报中的公式和表格进行解析"""
        if not os.path.exists(image_path):
            return ""

        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        if is_formula_or_table:
            prompt = "你是一个专业的财务文档解析专家。请识别图片中的内容。如果是数学公式，请必须使用 LaTeX 格式输出（用 $$ 包裹）。如果是表格，请转换为一模一样的 Markdown 表格格式。不要输出任何多余的解释，只输出转换后的结果。"
        else:
            prompt = "请描述图片内容。"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [base64_image],
            "stream": False
        }

        try:
            # 无 GPU 时 llava 跑 CPU 较慢，超时调大避免公式/表格解析被掐断返回空
            response = requests.post(self.ollama_url, json=payload, timeout=600)
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            return ""
        except Exception as e:
            print(f"视觉模型调用失败: {e}")
            return ""

vision_service = VisionService()