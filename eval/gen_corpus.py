"""把 ``corpus_spec.py`` 的结构化定义物化成真实文件(五种格式)。

产物
----
``eval/corpus/``          12 个真实文件: 4 md + 2 txt + 2 docx + 2 pdf + 2 png
``eval/qa_set.jsonl``     45 条 QA(带唯一关键串), 供测评与人工核对

为什么要"多格式真文件"
----------------------
入库成功率必须建立在真实文件之上 —— 只有真 PDF / 真 DOCX / 真位图才会触发
不同的解析分支(原生解析 / OCR 路由), 用字符串 mock 测不出解析层的真实表现。

用法
----
    cd enterprise-rag-workbench
    backend/venv/Scripts/python.exe eval/gen_corpus.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from corpus_spec import DOCS, QA, doc_plain_text  # noqa: E402

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS_DIR = os.path.join(EVAL_DIR, "corpus")

# Windows 自带中文字体, 用于渲染"扫描件"位图; 缺失时退回默认字体(仅影响观感, 不影响链路)
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
def _md_table(rows: list[list[str]]) -> str:
    header, *body = rows
    out = ["| " + " | ".join(header) + " |"]
    out.append("| " + " | ".join(["---"] * len(header)) + " |")
    for r in body:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def render_md(doc: dict) -> str:
    lines = [f"# {doc['title']}", ""]
    for sec in doc["sections"]:
        lines.append(f"## {sec['heading']}")
        lines.append("")
        for p in sec.get("paras") or []:
            lines.append(p)
            lines.append("")
        for tbl in sec.get("tables") or []:
            lines.append(_md_table(tbl))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------
def render_txt(doc: dict) -> str:
    lines = [doc["title"], "=" * 20, ""]
    for sec in doc["sections"]:
        lines.append(f"[{sec['heading']}]")
        lines.append("")
        for p in sec.get("paras") or []:
            lines.append(p)
            lines.append("")
        for tbl in sec.get("tables") or []:
            for row in tbl:
                lines.append(" | ".join(row))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# DOCX (真 Word 表格)
# ---------------------------------------------------------------------------
def build_docx(doc: dict, path: str) -> None:
    from docx import Document as DocxDocument
    from docx.shared import Pt

    d = DocxDocument()
    d.styles["Normal"].font.size = Pt(10.5)
    d.add_heading(doc["title"], level=1)
    for sec in doc["sections"]:
        d.add_heading(sec["heading"], level=2)
        for p in sec.get("paras") or []:
            d.add_paragraph(p)
        for tbl in sec.get("tables") or []:
            n_rows, n_cols = len(tbl), len(tbl[0])
            t = d.add_table(rows=n_rows, cols=n_cols)
            t.style = "Table Grid"
            for i, row in enumerate(tbl):
                for j, cell in enumerate(row):
                    t.cell(i, j).text = cell
    d.save(path)


# ---------------------------------------------------------------------------
# PDF (reportlab + 中文 CID 字体)
# ---------------------------------------------------------------------------
def build_pdf(doc: dict, path: str) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font_name = "STSong-Light"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    except Exception:  # noqa: BLE001
        font_name = "Helvetica"

    base = getSampleStyleSheet()["Normal"]
    body = ParagraphStyle(
        "body", parent=base, fontName=font_name, fontSize=10.5, leading=17, spaceAfter=6
    )
    h1 = ParagraphStyle("h1", parent=body, fontSize=17, leading=24, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=body, fontSize=13, leading=19, spaceBefore=8, spaceAfter=6)

    story = [Paragraph(doc["title"], h1)]
    for sec in doc["sections"]:
        story.append(Paragraph(sec["heading"], h2))
        for p in sec.get("paras") or []:
            story.append(Paragraph(p, body))
        for tbl in sec.get("tables") or []:
            data = [[Paragraph(str(c), body) for c in row] for row in tbl]
            t = Table(data, hAlign="LEFT")
            t.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(t)
            story.append(Spacer(1, 6 * mm))

    SimpleDocTemplate(
        path, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm
    ).build(story)


# ---------------------------------------------------------------------------
# PNG ("扫描件": 无文本层, 必须走 OCR)
# ---------------------------------------------------------------------------
def build_png(doc: dict, path: str) -> None:
    import random

    from PIL import Image, ImageDraw, ImageFont

    W, H = 1240, 1600
    img = Image.new("RGB", (W, H), (246, 245, 242))
    draw = ImageDraw.Draw(img)

    font = None
    for fp in _FONT_CANDIDATES:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 26)
                break
            except Exception:  # noqa: BLE001
                continue
    if font is None:
        font = ImageFont.load_default()

    # 纸面边框 + 轻微噪点(模拟扫描质感)
    draw.rectangle([40, 40, W - 40, H - 40], outline=(190, 188, 184), width=2)
    rnd = random.Random(20261104)
    for _ in range(2600):
        x, y = rnd.randrange(40, W - 40), rnd.randrange(40, H - 40)
        g = rnd.randrange(210, 245)
        draw.point((x, y), fill=(g, g, g))

    y = 90
    draw.text((80, y), doc["title"], font=font, fill=(30, 30, 30))
    y += 70
    for sec in doc["sections"]:
        draw.text((80, y), sec["heading"], font=font, fill=(50, 50, 50))
        y += 48
        for p in sec.get("paras") or []:
            # 简单折行
            line = ""
            for ch in p:
                line += ch
                if len(line) >= 30:
                    draw.text((80, y), line, font=font, fill=(40, 40, 40))
                    y += 42
                    line = ""
            if line:
                draw.text((80, y), line, font=font, fill=(40, 40, 40))
                y += 42
            y += 10
    # 模拟表单线框
    draw.rectangle([80, H - 420, W - 80, H - 120], outline=(120, 120, 120), width=1)
    for i in range(1, 6):
        yy = H - 420 + i * 50
        draw.line([82, yy, W - 82, yy], fill=(180, 180, 180), width=1)
    img.save(path, "PNG")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
_BUILDERS = {
    "md": lambda d, p: _write_text(p, render_md(d)),
    "txt": lambda d, p: _write_text(p, render_txt(d)),
    "docx": build_docx,
    "pdf": build_pdf,
    "png": build_png,
}


def _write_text(path: str, text: str) -> None:
    # 统一 LF 与 UTF-8, 避免 Windows 平台差异影响可复现性
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def verify_keys() -> list[str]:
    """校验每条 QA 的 key 真实出现在对应文档文本中, 杜绝"问题与语料漂移"。"""
    by_name = {d["filename"]: d for d in DOCS}
    problems: list[str] = []
    for i, item in enumerate(QA):
        doc = by_name.get(item["doc"])
        if doc is None:
            problems.append(f"QA#{i} 引用了不存在的文档 {item['doc']}")
            continue
        if item["key"] not in doc_plain_text(doc):
            problems.append(f"QA#{i} key 未在 {item['doc']} 中找到: {item['key']!r}")
    return problems


def main() -> int:
    os.makedirs(CORPUS_DIR, exist_ok=True)
    problems = verify_keys()
    if problems:
        print("[FAIL] QA key 校验未通过:")
        for p in problems:
            print("  -", p)
        return 1

    for doc in DOCS:
        ext = doc["filename"].rsplit(".", 1)[-1].lower()
        path = os.path.join(CORPUS_DIR, doc["filename"])
        _BUILDERS[ext](doc, path)
        print(f"[GEN] {doc['filename']:20s} {os.path.getsize(path):>8d} bytes  complex={doc['complex']}")

    qa_path = os.path.join(EVAL_DIR, "qa_set.jsonl")
    with open(qa_path, "w", encoding="utf-8", newline="\n") as f:
        for item in QA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"[GEN] qa_set.jsonl        {len(QA)} questions")
    print(f"[OK ] corpus -> {CORPUS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
