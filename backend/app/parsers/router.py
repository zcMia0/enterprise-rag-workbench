"""解析路由: 启发式动态选择原生 / OCR 路径。

规则 (可解释, 便于演示):
1. 图片型文件 (png/jpg) 一律 OCR。
2. PDF 若文本密度 < 阈值(默认 0.35) 或图片数 > 表格数*2 且文本极少 -> OCR。
3. 其余 (docx/md/txt 文本丰富) -> 原生。

返回 (path, reason): 选中的链路名与决策依据, 写入 Document.parse_path 便于追溯。
"""
from __future__ import annotations

from app.logging_config import get_logger
from app.parsers.base import ParsedDocument

log = get_logger("parser", "ROUTER")

TEXT_DENSITY_THRESHOLD = 0.35


def choose_path(file_type: str, doc: ParsedDocument | None = None) -> tuple[str, str]:
    """决策原生还是 OCR。

    Args:
        file_type: 文件扩展名 (pdf/docx/md/txt/png/jpg)
        doc: 若已做一次轻量原生探测, 可传入以计算密度; 否则按类型粗判。
    """
    ft = (file_type or "").lower()
    if ft in ("png", "jpg", "jpeg", "bmp", "tif", "tiff"):
        return "ocr", "image file -> ocr"

    if doc is not None:
        density = doc.text_density
        if density < TEXT_DENSITY_THRESHOLD:
            return "ocr", f"low text density ({density}) -> ocr"
        if doc.image_count > 0 and doc.text_length < 200:
            return "ocr", "few text but has images -> ocr"
        return "native", f"text density {density} -> native"

    # 无探测信息时按类型粗判: 文本类默认原生
    return "native", f"default by type ({ft}) -> native"
