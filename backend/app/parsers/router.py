"""解析路由: 按"是否存在文本层"动态选择原生 / OCR 路径。

为什么需要路由
--------------
企业文档里混着两类东西:
- 带文本层的原生文件 (docx / md / txt / 文本型 pdf) —— 解析又快又准, 不该送去 OCR;
- 没有文本层的图像 (png / jpg) 与纯图片型 pdf —— 除了 OCR 没有别的办法。

早期版本用"文本密度 < 0.35 就 OCR"这一条阈值统管所有格式, 实测会把**表格密集的
docx/md 误判为扫描件**(每张表按 500 字符的"非文本"计, 表格越多密度越低), 导致这类
高价值文档被送进 OCR 拿到一堆噪声。测评集(``eval/``)复现了该问题, 故改为下面的决策表。

决策表 (自上而下, 命中即返回)
------------------------------
1. 图像文件 (png/jpg/...)                -> OCR          没有文本层, 只能 OCR
2. 非 PDF 的原生格式 (docx/md/txt/...)   -> 原生         这类格式按定义必然带文本层
   · 例外: 解析后几乎取不到文字且含图片  -> OCR          视为"图文混排的伪原生文件"
3. PDF                                   -> 看文本层
   · 全文可提取字符 < MIN_TEXT_CHARS     -> OCR          无文本层, 判定为扫描件
   · 每页平均字符 < MIN_CHARS_PER_PAGE   -> OCR          文本层极薄, 判定为扫描件
   · 其余                                -> 原生

返回 ``(path, reason)``: 选中的链路与可解释依据, 写入 ``Document.parse_path`` 便于追溯。
"""
from __future__ import annotations

from app.logging_config import get_logger
from app.parsers.base import ParsedDocument

log = get_logger("parser", "ROUTER")

#: 图像类扩展名 —— 一律走 OCR
IMAGE_TYPES = frozenset({"png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp", "gif"})

#: 一定带文本层的原生格式 —— 默认不走 OCR
NATIVE_TYPES = frozenset({"docx", "doc", "md", "markdown", "txt", "text", "csv", "json"})

#: PDF 全文可提取字符低于此值 -> 认为没有文本层
MIN_TEXT_CHARS = 50

#: PDF 每页平均可提取字符低于此值 -> 认为文本层极薄(扫描件特征)
MIN_CHARS_PER_PAGE = 40


def choose_path(file_type: str, doc: ParsedDocument | None = None) -> tuple[str, str]:
    """决策走原生解析还是 OCR。

    Args:
        file_type: 文件扩展名(pdf/docx/md/txt/png/jpg…), 大小写不敏感。
        doc: 原生链路探测结果; 为 None 时只能按类型粗判。

    Returns:
        (解析路径, 决策依据)。路径取值为 ``"native"`` 或 ``"ocr"``。
    """
    ft = (file_type or "").lower().lstrip(".")

    # 1) 图像: 没有文本层
    if ft in IMAGE_TYPES:
        return "ocr", "image file (no text layer) -> ocr"

    # 无探测结果时按类型粗判: 文本类默认原生, 未知类型也先试原生(失败会降级为空占位)
    if doc is None:
        if ft == "pdf":
            return "native", "pdf without probe -> native (will fallback if empty)"
        return "native", f"default by type ({ft or 'unknown'}) -> native"

    # 2) 非 PDF 的原生格式: 按定义带文本层, 只有当解析不出任何文字时才考虑 OCR
    if ft in NATIVE_TYPES or ft not in {"pdf"}:
        if doc.text_length < MIN_TEXT_CHARS and doc.image_count > 0:
            return "ocr", (
                f"almost no text ({doc.text_length} chars) but {doc.image_count} images -> ocr"
            )
        if doc.text_length < MIN_TEXT_CHARS and doc.table_count == 0:
            return "ocr", f"almost no extractable text ({doc.text_length} chars) -> ocr"
        return "native", (
            f"text layer present ({doc.text_length} chars, "
            f"{doc.table_count} tables) -> native"
        )

    # 3) PDF: 依据文本层判断是否为扫描件
    if doc.text_length < MIN_TEXT_CHARS:
        return "ocr", f"pdf text layer missing ({doc.text_length} chars) -> ocr"
    pages = max(doc.page_count, 1)
    per_page = doc.text_length / pages
    if per_page < MIN_CHARS_PER_PAGE:
        return "ocr", f"pdf text layer too thin ({per_page:.1f} chars/page) -> ocr"
    return "native", (
        f"pdf text layer ok ({doc.text_length} chars / {pages}p = {per_page:.0f} chars/page) -> native"
    )
