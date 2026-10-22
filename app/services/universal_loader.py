import os
import re  # 🌟 修复：补上缺失的正则表达式库
import pandas as pd
from docx import Document
from pptx import Presentation

class UniversalLoader:
    """企业级多格式文档加载器"""

    def load(self, file_path: str) -> list[dict]:
        """返回统一格式的页面字典列表"""
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            from app.services.pdf_parser import FinancialPDFParser
            parser = FinancialPDFParser(file_path)
            return list(parser.parse_stream())

        elif ext in [".md", ".txt"]:
            return self._load_text(file_path)
        elif ext == ".docx":
            return self._load_word(file_path)
        elif ext in [".xlsx", ".xls"]:
            return self._load_excel(file_path)
        elif ext == ".pptx":
            return self._load_ppt(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

    def _load_text(self, file_path: str) -> list[dict]:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return [{
            "page_number": 1,
            "content": content,
            "metadata": {"source": file_path, "page": 1}
        }]

    def _load_word_ultimate(self, file_path: str) -> list[dict]:
        """
        🌟 终极版 Word 解析：真实顺序提取 + 表格自然语言化 + 保留排版细节
        """
        doc = Document(file_path)
        results = []

        current_chunk_text = []
        current_heading = "文档开头"

        # 辅助函数：保存当前块
        def save_current_chunk():
            if not current_chunk_text: return
            content = "\n".join(current_chunk_text).strip()
            if len(content) > 10:  # 过滤太短的无效块
                results.append({
                    "page_number": 1,
                    "content": content,
                    "parent_content": current_heading,
                    "metadata": {"source": file_path, "heading": current_heading}
                })
            current_chunk_text.clear()

        # 💡 核心改进 1：按文档真实顺序遍历（解决图文、表格乱序问题）
        # doc.element.body 包含了段落和表格的真实排列顺序
        for child in doc.element.body:
            if child.tag.endswith(qn('p')):  # 如果是段落
                para = Paragraph(child, doc)
                text = para.text.strip()
                if not text: continue

                # 💡 核心改进 2：保留列表结构（无序列表和有序列表）
                if para.style.name.startswith('List'):
                    # 检查是否有编号属性
                    numPr = para._element.xpath('./w:pPr/w:numPr')
                    if numPr:
                        # 粗略判断：可以根据具体 numId 区分有序无序，这里为了通用，统一用 "-" 代替
                        text = f"- {text}"

                # 识别标题并分块（结合你的 SmartChunker 思路）
                style_name = para.style.name.lower()
                if style_name.startswith('heading'):
                    save_current_chunk()  # 遇到新标题，保存上一块

                    try:
                        level = int(re.search(r'\d+', style_name).group())
                        md_heading = f"{'#' * level} {text}"
                    except:
                        md_heading = f"### {text}"

                    current_heading = text
                    current_chunk_text.append(f"\n{md_heading}\n")
                else:
                    current_chunk_text.append(text)

                    # 💡 核心改进 3：提取图片替代文本 (Alt Text)
                    # 如果这个段落里包含图片
                    if para._element.xpath('.//pic:pic'):
                        # Word 中一般有图注（Caption），如果没有图注，我们至少占个位
                        current_chunk_text.append("[此处包含一张图片/图表]")

            elif child.tag.endswith(qn('tbl')):  # 如果是表格
                # 遇到表格，先保存之前的文本
                save_current_chunk()

                table = Table(child, doc)
                # 💡 核心改进 4：表格“语义化”（按行转自然语言，而不是 Markdown）
                table_text = []

                # 提取表头（假设第一行是表头）
                headers = [cell.text.strip().replace('\n', ' ') for cell in table.rows[0].cells]
                table_text.append(f"\n### 表格数据（包含列：{', '.join(headers)}）\n")

                for row_idx, row in enumerate(table.rows):
                    if row_idx == 0: continue  # 跳过表头

                    row_data = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
                    row_str_parts = []
                    for col_name, val in zip(headers, row_data):
                        if val:  # 如果单元格有值
                            row_str_parts.append(f"{col_name}为{val}")

                    if row_str_parts:
                        # 转成类似于你 Excel 处理时的自然语言句
                        table_text.append("，".join(row_str_parts) + "。")

                current_chunk_text.extend(table_text)
                # 表格作为一个独立的核心块保存
                current_heading = f"数据表格区域"
                save_current_chunk()

        # 保存最后一块
        save_current_chunk()

        return results

    def _load_excel(self, file_path: str) -> list[dict]:
        """🌟 企业级 Excel 解析：智能表头 + 自然语言转换 + 元数据分离"""
        xls = pd.ExcelFile(file_path)
        results = []

        # 辅助函数：清理单元格内容（去除数字末尾多余的 .0）
        def clean_value(val):
            if pd.isna(val):
                return ""
            val_str = str(val).strip()
            if val_str.endswith('.0') and re.match(r'^-?\d+\.0$', val_str):
                val_str = val_str[:-2]
            return val_str

        for sheet_name in xls.sheet_names:
            # 1. 探测表头（最多读取前 5 行寻找数据行）
            df_probe = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=5)
            if df_probe.empty:
                continue

            header_row_index = 0  # 默认假设第 1 行是表头
            for i in range(len(df_probe)):
                # 如果这一行的数据里，数字占比超过 50%，说明它是数据行
                valid_vals = [str(v).strip() for v in df_probe.iloc[i].dropna()]
                if valid_vals:
                    numeric_count = sum(1 for v in valid_vals if re.match(r'^-?\d+(\.\d+)?$', v))
                    if numeric_count / len(valid_vals) > 0.5:
                        header_row_index = max(0, i - 1)  # 它的上一行就是表头
                        break

            # 2. 根据探测结果读取完整数据
            header_rows = [0] if header_row_index == 0 else [0, 1]
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_rows)
            except Exception:
                # 兼容处理：如果多级表头报错，退回到默认单行表头
                df = pd.read_excel(file_path, sheet_name=sheet_name, header=0)

            # 3. 处理表头（合并多级表头，清理 Unnamed）
            if isinstance(df.columns, pd.MultiIndex):
                new_columns = []
                for top, sub in df.columns:
                    top_str = str(top).strip() if "Unnamed" not in str(top) else ""
                    sub_str = str(sub).strip() if "Unnamed" not in str(sub) else ""
                    if top_str and sub_str:
                        new_columns.append(f"{top_str}_{sub_str}")
                    else:
                        new_columns.append(top_str or sub_str)
                df.columns = new_columns
            else:
                df.columns = [str(c).strip() for c in df.columns if "Unnamed" not in str(c)]

            # 4. 清理全空的行
            df.dropna(how='all', inplace=True)

            # 5. 按行转自然语言（Row-as-Text）
            row_texts = []
            for index, row in df.iterrows():
                row_str_parts = []
                for col_name, val in row.items():
                    cv = clean_value(val)
                    if cv and str(col_name).strip():
                        row_str_parts.append(f"{col_name}为{cv}")

                if row_str_parts:
                    row_texts.append("，".join(row_str_parts) + "。")

            if not row_texts:
                continue

            # 6. 生成父子块策略的上下文（父块概览）
            sample_text = "\n".join(row_texts[:5])
            parent_content = f"工作表【{sheet_name}】数据概览（共 {len(row_texts)} 行）：\n{sample_text}"

            # 7. 组装并返回结果
            for i, row_text in enumerate(row_texts):
                results.append({
                    "page_number": 1,
                    "content": row_text,  # 子块：用于向量计算
                    "parent_content": parent_content,  # 父块：仅作上下文，存为 Payload 即可
                    "metadata": {
                        "source": file_path,
                        "page": 1,
                        "sheet_name": sheet_name,
                        "row_index": i,
                        "columns": list(df.columns)  # 新增：列名元数据
                    }
                })

        return results

    def _load_ppt(self, file_path: str) -> list[dict]:
        """PPT 按页切分"""
        prs = Presentation(file_path)
        results = []
        for idx, slide in enumerate(prs.slides):
            slide_text = []
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    slide_text.append(shape.text)
            results.append({
                "page_number": idx + 1,
                "content": "\n".join(slide_text),
                "metadata": {"source": file_path, "page": idx + 1}
            })
        return results

universal_loader = UniversalLoader()