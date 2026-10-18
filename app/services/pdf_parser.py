import pymupdf as fitz
import pdfplumber
from typing import List, Dict, Any,Optional


class FinancialPDFParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        # 用 fitz 加载获取总页数
        self.doc = fitz.open(file_path)
        self.total_pages = len(self.doc)

    def extract_text_with_metadata(self) -> List[Dict[str, Any]]:
        pages_data = []

        # 用 pdfplumber 提取表格
        with pdfplumber.open(self.file_path) as pdf:
            for page_num in range(self.total_pages):
                # 🌟 关键点：分别获取两个不同库的 page 对象
                fitz_page = self.doc[page_num]
                plumber_page = pdf.pages[page_num]

                # 1. 用 fitz 提取纯文本
                page_text = ""
                blocks = fitz_page.get_text("blocks")  # 这里 fitz_page 调 get_text 没问题
                for block in blocks:
                    block_type = block[6]
                    text = block[4].strip()
                    if block_type == 0 and text:
                        if text.isdigit(): continue
                        page_text += text + "\n"

                # 2. 用 pdfplumber 提取表格
                table_mds = []
                tables = plumber_page.extract_tables()
                if tables:
                    for table in tables:
                        if not table or not table[0]: continue
                        # 这里的调用逻辑没问题
                        md_table = self._table_to_markdown(table)
                        table_mds.append(md_table)

                # 3. 合并
                if table_mds:
                    page_text += "\n\n【数据表格】\n" + "\n\n".join(table_mds) + "\n"

                if page_text.strip():
                    pages_data.append({
                        "page_number": page_num + 1,
                        "content": page_text,
                        "metadata": {
                            "source": self.file_path,
                            "page": page_num + 1
                        }
                    })
        return pages_data

    @staticmethod
    def _table_to_markdown(table: List[List[Optional[str]]]) -> str:
        # 🌟 关键点：去掉了 self 参数
        if not table: return ""
        cleaned_table = []
        for row in table:
            cleaned_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
            cleaned_table.append(cleaned_row)

        lines = []
        lines.append("| " + " | ".join(cleaned_table[0]) + " |")
        lines.append("|" + "|".join(["---"] * len(cleaned_table[0])) + "|")
        for row in cleaned_table[1:]:
            if len(row) < len(cleaned_table[0]):
                row += [""] * (len(cleaned_table[0]) - len(row))
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def close(self):
        self.doc.close()