from typing import List, Dict, Any


class ParentChildChunker:
    def __init__(self, child_chunk_size: int = 300, overlap: int = 50):
        self.child_chunk_size = child_chunk_size
        self.overlap = overlap

    def split(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        返回包含父子关系的切片列表。
        每一页作为一个父块 (Parent)，内部按段落切成子块 (Child)。
        """
        chunks = []

        for page in pages:
            content = page["content"]
            metadata = page["metadata"]
            parent_id = f"page_{page['page_number']}"

            # 父块：保留整页内容（如果页面太长，可以做适当截断）
            parent_content = content

            # 子块：按段落或长度切分，用于精准检索
            paragraphs = content.split("\n\n")
            for para in paragraphs:
                # 如果段落极短，直接并入下一个；这里为简单起见，按长度切分
                if len(para) <= self.child_chunk_size:
                    child_content = para
                else:
                    # 强切
                    child_content = para[:self.child_chunk_size]

                if child_content.strip():
                    chunks.append({
                        "parent_id": parent_id,
                        "parent_content": parent_content,
                        "child_content": child_content.strip(),
                        "metadata": metadata
                    })

        return chunks