"""OCR 智能识别链路: 针对扫描件 / 图片型 PDF。

真实引擎: PaddleOCR (重) 或 RapidOCR (轻)。本环境默认 mock,
           但保留真实调用分支。Mock OCR 会模拟"识别到表格/图片"的结构化结果,
           以驱动半结构化保护式切分演示。

无论真实或 Mock, 产出均为 ParsedDocument, 与原生链路同构。
"""
from __future__ import annotations

import os

from app.config import get_settings
from app.logging_config import get_logger
from app.parsers.base import ParsedBlock, ParsedDocument

log = get_logger("parser", "OCR")

_settings = get_settings()


def _ocr_real(path: str) -> ParsedDocument:
    """真实 OCR (RapidOCR 优先, 其次 PaddleOCR)。"""
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore

        engine = RapidOCR()
        result, _ = engine(path)
        doc = ParsedDocument()
        para_lines: list[str] = []
        for box, text, score in result:  # noqa: B007
            para_lines.append(str(text))
        if para_lines:
            doc.blocks.append(ParsedBlock(type="text", content="\n".join(para_lines), page=1))
            doc.text_length += sum(len(t) for t in para_lines)
        doc.page_count = 1
        return doc
    except Exception as exc:  # noqa: BLE001
        log.warning(f"real OCR unavailable ({exc}); mock OCR fallback")
        return _ocr_mock(path)


def _ocr_mock(path: str) -> ParsedDocument:
    """Mock OCR: 模拟从扫描件识别出文本 + 一张带表格的图片。

    为演示保护式切分, 这里构造一个含 <table> 的结构, 让链路能走"表格保护"分支。
    """
    doc = ParsedDocument()
    doc.page_count = 1
    doc.image_count = 1
    # 模拟识别文本
    doc.blocks.append(
        ParsedBlock(
            type="text",
            content="本页为扫描件 OCR 结果。下方为识别出的表格区域。",
            page=1,
        )
    )
    doc.text_length += 24
    # 模拟 OCR 命中的表格 (HTML 形式, 供保护式切分)
    doc.blocks.append(
        ParsedBlock(
            type="table",
            content=(
                "<table><tr><td>字段名</td><td>类型</td><td>说明</td></tr>"
                "<tr><td>user_id</td><td>int</td><td>用户唯一标识</td></tr>"
                "<tr><td>created_at</td><td>datetime</td><td>创建时间</td></tr></table>"
            ),
            page=1,
        )
    )
    doc.table_count += 1
    # 模拟识别出的图片块
    doc.blocks.append(
        ParsedBlock(
            type="image",
            content="[图片: 系统架构示意图]",
            page=1,
            ocr_text="架构图包含网关、服务层与存储层三层。",
        )
    )
    return doc


def parse_ocr(path: str, file_type: str) -> ParsedDocument:
    """OCR 解析入口。"""
    log.info(f"ocr parse start -> {os.path.basename(path)} ({file_type})")
    if _settings.ocr_engine == "mock":
        return _ocr_mock(path)
    return _ocr_real(path)
