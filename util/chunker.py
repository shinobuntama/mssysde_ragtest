"""Markdown化したドキュメントを、検索に適したチャンクに分割する。

方針: 構造ベース(見出し・表) + 再帰的分割(段落 → 文) + オーバーラップ
  1. 本文をブロック(見出し / 表 / 段落)に分ける
  2. ブロックを順に詰めてチャンクを作る。見出しが来て一定量たまっていれば区切る
  3. 長すぎるブロックだけ、表は行単位(ヘッダー行を付け直す)、段落は文単位で分割する
  4. 各チャンクの先頭に、見出しの階層(パンくず)を付ける
"""
import re

MAX_CHARS = 1000      # チャンクの目安の最大文字数
MIN_CHARS = 300       # 見出しで区切るために最低限ためる文字数
OVERLAP = 120         # 長い段落を分割するときの重なり文字数
HARD_LIMIT = 3000     # これを超える断片は文字数で強制分割(埋め込み上限の安全策)

_HEADING = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')
_TABLE_SEP = re.compile(r'^\|[\s:|\-]+\|?\s*$')
# 文末(。！？ . ! ?)と改行の直後で分割する。文字は削らないので、連結すると元に戻る
_SENTENCE_SPLIT = re.compile(r'(?<=[。！？])|(?<=[.!?])(?=\s)|(?<=\n)')


def _hard_split(text: str, limit: int) -> list[str]:
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def _split_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """文単位で max_chars 程度に分割。前のチャンクの末尾 overlap 文字を次の先頭に重ねる"""
    units = []
    for s in _SENTENCE_SPLIT.split(text):
        if not s:
            continue
        units.extend(_hard_split(s, max_chars) if len(s) > max_chars else [s])

    chunks, cur = [], ""
    for u in units:
        if cur and len(cur) + len(u) > max_chars:
            chunks.append(cur)
            cur = (cur[-overlap:] if overlap else "") + u
        else:
            cur += u
    if cur.strip():
        chunks.append(cur)
    return chunks


def _split_table(table: str, max_chars: int) -> list[str]:
    """表を行単位で分割し、各断片の先頭にヘッダー行を付け直す"""
    lines = table.split("\n")
    if len(lines) < 3 or not _TABLE_SEP.match(lines[1]):
        return _split_text(table, max_chars, 0)

    head = "\n".join(lines[:2])
    chunks, cur, size = [], [], len(head)
    for row in lines[2:]:
        if cur and size + len(row) + 1 > max_chars:
            chunks.append(head + "\n" + "\n".join(cur))
            cur, size = [], len(head)
        cur.append(row)
        size += len(row) + 1
    if cur:
        chunks.append(head + "\n" + "\n".join(cur))
    return chunks


def _to_blocks(pages: list[tuple[int, str]]) -> list[dict]:
    """(ページ番号, Markdown) のリストを、見出し階層つきのブロック列に変換"""
    blocks = []
    stack: list[tuple[int, str]] = []   # (見出しレベル, 見出し文字列)

    def add(page, kind, text):
        blocks.append({"page": page, "kind": kind, "text": text,
                       "path": tuple(t for _, t in stack)})

    for page, text in pages:
        for raw in re.split(r'\n\s*\n', text):
            block = raw.strip("\n")
            if not block.strip():
                continue
            lines = block.split("\n")
            # ブロック先頭が見出しなら、見出しと本文に分ける
            m = _HEADING.match(lines[0])
            if m:
                level, title = len(m.group(1)), m.group(2)
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
                add(page, "heading", lines[0].strip())
                block = "\n".join(lines[1:]).strip("\n")
                if not block.strip():
                    continue
            kind = "table" if block.lstrip().startswith("|") else "text"
            add(page, kind, block)
    return blocks


def _with_path(path: tuple, body: str) -> str:
    return f"【{' > '.join(path)}】\n\n{body}" if path else body


def _chunk_group(pages, max_chars, min_chars, overlap) -> list[tuple[int, str]]:
    result = []
    cur, kinds = [], []
    cur_len, cur_page, cur_path = 0, None, ()

    def flush():
        nonlocal cur, kinds, cur_len, cur_page, cur_path
        if cur:
            result.append((cur_page, _with_path(cur_path, "\n\n".join(cur))))
        cur, kinds, cur_len, cur_page, cur_path = [], [], 0, None, ()

    for b in _to_blocks(pages):
        if len(b["text"]) <= max_chars:
            pieces = [b["text"]]
        elif b["kind"] == "table":
            pieces = _split_table(b["text"], max_chars)
        else:
            pieces = _split_text(b["text"], max_chars, overlap)

        for piece in pieces:
            for part in (_hard_split(piece, HARD_LIMIT) if len(piece) > HARD_LIMIT else [piece]):
                plen = len(part) + 2
                is_heading = b["kind"] == "heading"
                # 見出しだけがたまっている間は、見出しを本文と同じチャンクにするため区切らない
                only_headings = all(k == "heading" for k in kinds)
                too_big = cur_len + plen > max_chars and not only_headings
                if cur and ((is_heading and cur_len >= min_chars) or too_big):
                    # 見出しだけがチャンクの末尾に取り残されないよう、次のチャンクへ持ち越す
                    carry = None
                    if not is_heading and kinds[-1] == "heading" and len(cur) > 1:
                        carry = (cur.pop(), b["path"])
                        kinds.pop()
                    flush()
                    if carry:
                        cur, kinds, cur_len = [carry[0]], ["heading"], len(carry[0]) + 2
                        cur_page, cur_path = b["page"], carry[1]
                if not cur:
                    cur_page, cur_path = b["page"], b["path"]
                cur.append(part)
                kinds.append(b["kind"])
                cur_len += plen
    flush()
    return result


def chunk_pages(pages: list[tuple[int, str]], merge_pages: bool = False,
                max_chars: int = MAX_CHARS, min_chars: int = MIN_CHARS,
                overlap: int = OVERLAP) -> list[tuple[int, str]]:
    """(ページ番号, Markdown) のリストをチャンク化して (ページ番号, 本文) のリストを返す

    merge_pages=True : 全ページを連結してから分割する(PDF向け。ページをまたぐ文章を保てる)
                       各チャンクの page_number は、チャンクが始まるページ
    merge_pages=False: 各要素を独立に分割する(Excelのシートなど、まとまりが独立している場合)
    """
    groups = [pages] if merge_pages else [[p] for p in pages]
    result = []
    for g in groups:
        result.extend(_chunk_group(g, max_chars, min_chars, overlap))
    return result
