import asyncio
import os
from app.services.pdf_parser import FinancialPDFParser
from app.services.chunker import ParentChildChunker
from app.services.vector_store import vector_store


async def main():
    pdf_path = "test.pdf"
    if not os.path.exists(pdf_path):
        print("找不到 PDF 文件")
        return

    # 1. 初始化数据库集合
    vector_store.init_collection()

    # 2. 解析 PDF
    print("开始解析 PDF...")
    parser = FinancialPDFParser(pdf_path)
    pages = parser.extract_text_with_metadata()
    parser.close()

    # 3. 切片
    print("开始进行父子文档切片...")
    chunker = ParentChildChunker(child_chunk_size=300)
    chunks = chunker.split(pages)
    print(f"切分完成，共生成 {len(chunks)} 个子块。")

    # 4. 向量化并入库（为了测试速度，我们只取前 10 个切片存进去）
    print("开始生成向量并存入 Qdrant (测试前10个块)...")
    await vector_store.insert_chunks(chunks[:10], document_id="tencent_2024")

    print("✅ 测试入库完成！请打开浏览器访问 http://localhost:6333/dashboard 查看数据。")


if __name__ == "__main__":
    asyncio.run(main())