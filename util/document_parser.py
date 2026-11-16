import io
import re
import pymupdf
import pymupdf4llm
import pandas as pd
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


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


def _docx_table_to_markdown(table: Table) -> str:
    """Wordの表をMarkdown表に変換。1行目をヘッダーとして扱う"""
    rows = []
    for row in table.rows:
        cells = []
        prev_tc = None
        for cell in row.cells:
            # 横方向に結合されたセルは同じセルが繰り返し返るため、重複を除く
            if cell._tc is prev_tc:
                continue
            prev_tc = cell._tc
            text = cell.text.replace("\n", " ").replace("|", "\\|").strip()
            cells.append(text)
            # 結合セルは占有していた列数ぶん空セルを足して列位置を保つ
            span = cell._tc.grid_span
            cells.extend([""] * (span - 1))
        rows.append(cells)

    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    rows = [r + [""] * (col_count - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |",
             "|" + "|".join(["---"] * col_count) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def parse_docx(data: bytes) -> list[tuple[int, str]]:
    """Word(.docx)をMarkdownに変換。戻り値: [(1, 本文)]  ※ .doc(旧形式)は非対応

    - 見出し(Heading N / 見出し N)は '#' に変換。先頭にファイル名の '#' が付くため1段下げる
    - 箇条書きスタイルは '- '、表はMarkdown表に変換
    - 段落と表は文書内の並び順のまま出力
    """
    doc = Document(io.BytesIO(data))
    blocks = []
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style = para.style.name if para.style is not None else ""
            m = re.match(r"(?:Heading|見出し)\s*(\d)", style)
            if m:
                blocks.append("#" * min(int(m.group(1)) + 1, 6) + " " + text)
            elif style == "Title":
                blocks.append("## " + text)
            elif style.startswith("List"):
                item = "- " + text
                # 連続する箇条書きは空行を挟まず1ブロックにまとめる
                if blocks and blocks[-1].startswith("- "):
                    blocks[-1] += "\n" + item
                else:
                    blocks.append(item)
            else:
                blocks.append(text)
        elif child.tag.endswith("}tbl"):
            md = _docx_table_to_markdown(Table(child, doc))
            if md:
                blocks.append(md)

    if not blocks:
        return []
    return [(1, "\n\n".join(blocks))]
