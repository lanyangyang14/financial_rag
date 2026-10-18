from app.services.pdf_parser import FinancialPDFParser
import os

# ⚠️ 请把这里换成你真实 PDF 文件的路径！
# 如果没有 PDF，你可以去网上下一个年报，比如放在 D:\financial_rag\data\test.pdf
pdf_file_path = "test.pdf"

if not os.path.exists(pdf_file_path):
    print(f"找不到文件: {pdf_file_path}，请准备一个财报 PDF 并修改路径。")
else:
    print("开始解析...")
    parser = FinancialPDFParser(pdf_file_path)
    pages = parser.extract_text_with_metadata()
    parser.close()

    print(f"解析完成，共 {len(pages)} 页。")

    if pages:
        print("====== 第 1 页内容预览 ======")
        # 只打印前 500 个字符，防止刷屏
        print(pages[0]["content"][:800])
        print("====== 元数据 ======")
        print(pages[0]["metadata"])