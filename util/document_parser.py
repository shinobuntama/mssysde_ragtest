import io
import pymupdf
import pymupdf4llm
import pandas as pd


def parse_pdf(data: bytes) -> list[tuple[int, str]]:
    """PDFをページごとのMarkdownに変換。戻り値: [(ページ番号, 本文), ...]"""
    doc = pymupdf.open(stream=data, filetype="pdf")
    chunks = pymupdf4llm.to_markdown(doc, page_chunks=True)
    return [
        (i, c["text"]) for i, c in enumerate(chunks, start=1)
        if c["text"].strip()
    ]


def parse_excel(data: bytes, ext: str) -> list[tuple[int, str]]:
    """ExcelをシートごとのMarkdown表に変換。xlsx: openpyxl / xls: xlrd"""
    engine = "openpyxl" if ext == ".xlsx" else "xlrd"
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, engine=engine)
    result = []
    for i, (name, df) in enumerate(sheets.items(), start=1):
        df = df.dropna(how="all").dropna(axis=1, how="all").fillna("")
        if df.empty:
            continue
        result.append((i, f"## シート: {name}\n\n" + df.to_markdown(index=False)))
    return result
