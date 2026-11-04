"""解析层基础抽象。

双链路共用同一输出结构: 一个 ParsedDocument 包含若干 ParsedBlock。
Block 类型:
- text : 纯文本段落
- table: 表格 (以 HTML <table> 形式保留, 供保护式切分)
- image: 图片 (以占位描述 + 可选 OCR 文本)

解析产出同时计算文档级启发式特征 (表格数 / 图片数 / 文本密度),
供路由层动态选择解析路径。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ParsedBlock:
    type: Literal["text", "table", "image"]
    content: str          # 文本 or HTML(table) or 图片描述
    page: int = 1
    ocr_text: str = ""    # 图片/扫描块的 OCR 文本 (可选)


@dataclass
class ParsedDocument:
    blocks: list[ParsedBlock] = field(default_factory=list)
    table_count: int = 0
    image_count: int = 0
    text_length: int = 0
    page_count: int = 1

    @property
    def text_density(self) -> float:
        """文本密度: 纯文本字符 / (纯文本 + 表格 + 图片占位) 字符, 取值 0~1。

        含义是"可提取内容里有多少比例是普通段落文字", 表格与图片占比越高该值越低。
        注意: **不要**再用它判断是否为扫描件 —— 表格密集的正常文档密度同样很低。
        是否为扫描件由 ``parsers.router`` 依据"PDF 是否存在文本层"判断。
        """
        text_chars = sum(len(b.content) for b in self.blocks if b.type == "text")
        other_chars = sum(len(b.content) for b in self.blocks if b.type != "text")
        total = text_chars + other_chars
        if total == 0:
            return 1.0
        return round(text_chars / total, 4)

    def to_text(self) -> str:
        parts = []
        for b in self.blocks:
            if b.type == "image" and b.ocr_text:
                parts.append(b.ocr_text)
            else:
                parts.append(b.content)
        return "\n\n".join(parts)
