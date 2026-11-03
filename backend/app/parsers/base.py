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
        """文本密度: 文本字符占比 (0~1)。越低越像扫描件, 越需要 OCR。"""
        total = self.text_length + self.table_count * 500 + self.image_count * 1000
        if total == 0:
            return 1.0
        return round(self.text_length / total, 4)

    def to_text(self) -> str:
        parts = []
        for b in self.blocks:
            if b.type == "image" and b.ocr_text:
                parts.append(b.ocr_text)
            else:
                parts.append(b.content)
        return "\n\n".join(parts)
