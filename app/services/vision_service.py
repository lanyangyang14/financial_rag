import base64
import requests
import os

class VisionService:
    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        self.model = "llava" # 你拉取的本地视觉模型

    def describe_image(self, image_path: str) -> str:
        """调用多模态模型生成图片描述"""
        if not os.path.exists(image_path):
            return ""

        # 读取图片并转 Base64
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        prompt = "这是一份财务报表中的图片。请仔细分析图片内容。如果是折线图或柱状图，请说明它的标题、X轴和Y轴代表什么，以及数据趋势是什么。只输出描述，不要废话。"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [base64_image],
            "stream": False
        }

        try:
            response = requests.post(self.ollama_url, json=payload, timeout=60)
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            return ""
        except Exception as e:
            print(f"视觉模型调用失败: {e}")
            return ""

vision_service = VisionService()