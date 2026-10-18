import pymupdf as fitz
import pdfplumber
import os
from typing import List, Dict, Any


class FinancialPDFParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.doc = fitz.open(file_path)
        self.total_pages = len(self.doc)
        # 确保图片保存目录存在
        os.makedirs("data/images", exist_ok=True)

    def extract_text_with_metadata(self) -> List[Dict[str, Any]]:
        pages_data = []

        with pdfplumber.open(self.file_path) as pdf:
            for page_num in range(self.total_pages):
                fitz_page = self.doc[page_num]
                plumber_page = pdf.pages[page_num]

                page_text = ""

                # 🌟 核心新增：提取当前页的图片
                image_paths = []
                image_list = fitz_page.get_images(full=True)
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = self.doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]

                    # 只保留有一定大小的图片（过滤掉小图标/线条）
                    if len(image_bytes) > 10000:
                        img_filename = f"data/images/p{page_num + 1}_img{img_index}.{image_ext}"
                        with open(img_filename, "wb") as f:
                            f.write(image_bytes)
                        image_paths.append(img_filename)

                # 提取文本
                blocks = fitz_page.get_text("blocks")
                for block in blocks:
                    if block[6] == 0 and block[4].strip():
                        page_text += block[4].strip() + "\n"

                # 提取表格
                table_mds = []
                tables = plumber_page.extract_tables()
                if tables:
                    for table in tables:
                        if table and table[0]:
                            table_mds.append(self._table_to_markdown(table))
                if table_mds:
                    page_text += "\n\n【数据表格】\n" + "\n\n".join(table_mds) + "\n"

                if page_text.strip() or image_paths:
                    pages_data.append({
                        "page_number": page_num + 1,
                        "content": page_text,
                        # 把图片路径也塞进 metadata 里
                        "metadata": {
                            "source": self.file_path,
                            "page": page_num + 1,
                            "image_paths": image_paths  # 👈 关键：携带图片路径
                        }
                    })
        return pages_data

    @staticmethod
    def _table_to_markdown(table) -> str:
        # ... (保留之前的表格转 Markdown 代码) ...
        if not table: return ""
        cleaned_table = [[str(cell).replace('\n', ' ').strip() if cell else "" for cell in row] for row in table]
        lines = ["| " + " | ".join(cleaned_table[0]) + " |", "|" + "|".join(["---"] * len(cleaned_table[0])) + "|"]
        for row in cleaned_table[1:]:
            if len(row) < len(cleaned_table[0]): row += [""] * (len(cleaned_table[0]) - len(row))
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def close(self):
        self.doc.close()