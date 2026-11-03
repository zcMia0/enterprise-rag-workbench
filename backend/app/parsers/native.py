"""原生解析链路: PDF / Docx / Markdown / TXT。

依赖策略:
- PDF   : 优先 pypdf (轻量), 失败回退纯文本占位 (不阻断)。
- Docx  : python-docx 提取段落与表格 (表格保留为 HTML)。
- MD/TXT: 直接读取, 简单识别标题层级。

所有解析失败均降级为"可读文本 + 标记", 保证上传链路不中断。
"""
from __future__ import annotations

import os

from app.logging_config import get_logger
from app.parsers.base import ParsedBlock, ParsedDocument

log = get_logger("parser", "NATIVE")


def _parse_pdf(path: str) -> ParsedDocument:
    doc = ParsedDocument()
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:  # noqa: BLE001
        log.warning("pypdf not installed; PDF parsed as empty placeholder")
        doc.blocks.append(ParsedBlock(type="text", content="[PDF 内容待解析: 未安装 pypdf]", page=1))
        return doc
    try:
        reader = PdfReader(path)
        doc.page_count = len(reader.pages)
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                doc.blocks.append(ParsedBlock(type="text", content=text.strip(), page=i))
                doc.text_length += len(text)
    except Exception as exc:  # noqa: BLE001
        log.warning(f"pdf parse error ({exc})")
        doc.blocks.append(ParsedBlock(type="text", content="[PDF 解析失败]", page=1))
    return doc


def _parse_docx(path: str) -> ParsedDocument:
    doc = ParsedDocument()
    try:
        from docx import Document as DocxDocument  # type: ignore
    except Exception:  # noqa: BLE001
        log.warning("python-docx not installed; DOCX parsed as empty placeholder")
        doc.blocks.append(ParsedBlock(type="text", content="[DOCX 内容待解析: 未安装 python-docx]", page=1))
        return doc
    try:
        d = DocxDocument(path)
        # 正文段落
        for p in d.paragraphs:
            t = p.text.strip()
            if t:
                doc.blocks.append(ParsedBlock(type="text", content=t, page=1))
                doc.text_length += len(t)
        # 表格 -> 保护式 HTML
        for tbl in d.tables:
            html = _table_to_html(tbl)
            doc.blocks.append(ParsedBlock(type="table", content=html, page=1))
            doc.table_count += 1
    except Exception as exc:  # noqa: BLE001
        log.warning(f"docx parse error ({exc})")
        doc.blocks.append(ParsedBlock(type="text", content="[DOCX 解析失败]", page=1))
    return doc


def _table_to_html(tbl) -> str:  # type: ignore[no-untyped-def]
    rows = []
    for r in tbl.rows:
        cells = "".join(f"<td>{c.text.strip()}</td>" for c in r.cells)
        rows.append(f"<tr>{cells}</tr>")
    return f"<table>{''.join(rows)}</table>"


def _is_md_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and "|" in s[1:-1]


def _is_md_table_sep(line: str) -> bool:
    s = line.strip().replace("|", "").replace(" ", "")
    return bool(s) and all(c in "-:" for c in s) and "-" in s


def _parse_text(path: str) -> ParsedDocument:
    doc = ParsedDocument()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
    except Exception as exc:  # noqa: BLE001
        log.warning(f"text read error ({exc})")
        raw = ""

    lines = raw.splitlines()
    i = 0
    buf: list[str] = []

    def _flush_text():
        if buf:
            text = "\n".join(buf).strip()
            if text:
                doc.blocks.append(ParsedBlock(type="text", content=text, page=1))
                doc.text_length += len(text)
            buf.clear()

    while i < len(lines):
        line = lines[i]
        # 检测 Markdown 管道表格: 表头行 + 分隔行
        if _is_md_table_row(line) and i + 1 < len(lines) and _is_md_table_sep(lines[i + 1]):
            _flush_text()
            table_lines = [line]
            i += 1
            while i < len(lines) and _is_md_table_row(lines[i]):
                table_lines.append(lines[i])
                i += 1
            # 以 Markdown 原样保留, 标记为受保护表格块
            doc.blocks.append(
                ParsedBlock(type="table", content="\n".join(table_lines), page=1)
            )
            doc.table_count += 1
            continue
        if line.strip() == "":
            _flush_text()
        else:
            buf.append(line)
        i += 1
    _flush_text()

    if not doc.blocks:
        doc.blocks.append(ParsedBlock(type="text", content="[空文件]", page=1))
    return doc


def parse_native(path: str, file_type: str) -> ParsedDocument:
    """原生解析入口。"""
    log.info(f"native parse start -> {os.path.basename(path)} ({file_type})")
    if file_type == "pdf":
        return _parse_pdf(path)
    if file_type == "docx":
        return _parse_docx(path)
    # md / txt / 其它纯文本
    return _parse_text(path)
