import os
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter


class SmartChunker:
    def __init__(self):
        # 1. 针对普通文本的兜底切片
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )

        # 2. 针对 Markdown 的结构感知切片（按标题切）
        self.md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
            ]
        )

    def split(self, pages: list[dict], file_ext: str) -> list[dict]:
        chunks = []
        for page in pages:
            content = page["content"]
            metadata = page["metadata"]

            # 🌟 1. 如果本身已经包含了 parent_content (比如 Excel)
            if "parent_content" in page:
                chunks.append({
                    "child_content": content,
                    "parent_content": page["parent_content"],
                    "metadata": metadata
                })
                continue

            # 🌟 2. 如果是 Markdown，按标题层级切分
            if file_ext == ".md" or file_ext == ".docx":
                md_splits = self.md_splitter.split_text(content)
                for split in md_splits:
                    headers = ", ".join([f"{k}: {v}" for k, v in split.metadata.items()])
                    text = f"【{headers}】\n{split.page_content}" if headers else split.page_content
                    chunks.append(self._create_chunk(text, text, metadata))

            # 🌟 3. 普通文本 / PDF
            else:
                splits = self.text_splitter.split_text(content)
                for text in splits:
                    chunks.append(self._create_chunk(text, text, metadata))

        return chunks

    def _create_chunk(self, child: str, parent: str, metadata: dict) -> dict:
        return {
            "child_content": child,
            "parent_content": parent,
            "metadata": metadata
        }


smart_chunker = SmartChunker()