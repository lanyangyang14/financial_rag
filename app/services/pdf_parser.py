import re
import pymupdf as fitz
import pdfplumber
import os
from typing import List, Dict, Any, Generator


class FinancialPDFParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.doc = fitz.open(file_path)
        self.total_pages = len(self.doc)
        self.pending_table = None  # 跨页表格暂存区
        os.makedirs("data/images", exist_ok=True)

    def parse_stream(self) -> Generator[Dict[str, Any], None, None]:
        """🌟 流式逐页解析器（融合了图片、表格、跨页缝合）"""
        with pdfplumber.open(self.file_path) as pdf:
            for page_num in range(self.total_pages):
                fitz_page = self.doc[page_num]
                plumber_page = pdf.pages[page_num]

                page_text = ""
                image_paths = []

                # ---------------- 1. 提取图片 ----------------
                image_list = fitz_page.get_images(full=True)
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = self.doc.extract_image(xref)
                    if len(base_image["image"]) > 10000:
                        img_filename = f"data/images/p{page_num + 1}_img{img_index}.{base_image['ext']}"
                        with open(img_filename, "wb") as f:
                            f.write(base_image["image"])
                        image_paths.append(img_filename)

                # ---------------- 2. 提取文本 ----------------
                blocks = fitz_page.get_text("blocks")
                for block in blocks:
                    if block[6] == 0 and block[4].strip():
                        text = block[4].strip()
                        # 修复：不再误杀包含换行的纯数字区块
                        if len(text) < 10 and text.isdigit() and "\n" not in text:
                            continue
                        page_text += text + "\n"

                # ---------------- 3. 提取表格并缝合 ----------------
                raw_tables = plumber_page.extract_tables()
                # 将原始二维列表转成 Markdown 表格数据
                current_table_data = [table for table in raw_tables if table and table[0]]

                # 🌟 核心：调用跨页缝合算法，传入当前页码
                stitched_tables = self._stitch_tables(current_table_data, page_num + 1)

                # 将缝合好的表格转为 Markdown
                table_mds = []
                for table in stitched_tables:
                    table_mds.append(self._table_to_markdown(table))

                if table_mds:
                    page_text += "\n\n【数据表格】\n" + "\n\n".join(table_mds) + "\n"

                # ---------------- 4. Yield 输出 ----------------
                if page_text.strip() or image_paths:
                    yield {
                        "page_number": page_num + 1,
                        "content": page_text,
                        "metadata": {
                            "source": self.file_path,
                            "page": page_num + 1,
                            "image_paths": image_paths
                        }
                    }

            # 🌟 核心收尾：如果全部解析完，还有挂起的表格，必须强制输出
            if self.pending_table:
                pending_md = self._table_to_markdown(self.pending_table)
                yield {
                    "page_number": self.total_pages,  # 归属到最后一页
                    "content": f"\n\n【数据表格 (跨页延伸)】\n{pending_md}\n",
                    "metadata": {
                        "source": self.file_path,
                        "page": self.total_pages,
                        "image_paths": []
                    }
                }
                self.pending_table = None

    def _stitch_tables(self, current_tables: list, current_page_num: int) -> list:
        """🌟 跨页表格缝合算法"""
        if not current_tables:
            # 如果当前页没表格，但有上次遗留的，说明多页表格结束了，返回遗留的
            if self.pending_table:
                final_table = self.pending_table
                self.pending_table = None
                return [final_table]
            return []

        tables_to_process = []

        # 情况 A：上一页有遗留表格
        if self.pending_table:
            prev_header = self.pending_table[0]
            curr_header = current_tables[0][0]

            # 判断表头是否一致（简单转字符串比对）
            if str(prev_header) == str(curr_header):
                print(f"🧵 [跨页缝合] 发现表头一致，正在缝合第 {current_page_num} 页...")
                # 缝合：把当前表去掉表头后的数据，塞给上一页暂存的表
                self.pending_table.extend(current_tables[0][1:])
                tables_to_process = current_tables[1:]  # 剩余的表走正常逻辑
            else:
                # 表头不一致，说明不是同一张表。吐出旧表，正常处理新表
                tables_to_process = [self.pending_table] + current_tables
                self.pending_table = None
        else:
            tables_to_process = current_tables

        # 情况 B：检查当前页的最后一张表，是否可能跨到了下一页
        if tables_to_process:
            last_table = tables_to_process[-1]
            last_cell_text = str(last_table[-1][-1]) if last_table[-1] else ""

            # 如果最后一行没有句号（说明话没说完），或者表格行数非常多，判定为跨页
            if len(last_cell_text) > 0 and not re.search(r'[。！？.]$', last_cell_text):
                # 暂存最后一张表，留给下一页
                self.pending_table = tables_to_process.pop()
            # 如果最后一张表就是空的，丢弃
            elif not last_cell_text.strip():
                tables_to_process.pop()

        return tables_to_process

    @staticmethod
    def _table_to_markdown(table) -> str:
        """将二维列表转为 Markdown 表格"""
        if not table: return ""
        cleaned_table = [[str(cell).replace('\n', ' ').strip() if cell else "" for cell in row] for row in table]

        # 确保每一行的列数一致
        max_cols = max(len(row) for row in cleaned_table)
        for row in cleaned_table:
            if len(row) < max_cols:
                row.extend([""] * (max_cols - len(row)))

        lines = ["| " + " | ".join(cleaned_table[0]) + " |", "|" + "|".join(["---"] * len(cleaned_table[0])) + "|"]
        for row in cleaned_table[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def close(self):
        self.doc.close()