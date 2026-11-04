"""半结构化保护式切分。

核心思想:
- 文本块按 chunk_size 滑动窗口切分 (带 overlap), 尽量在段落边界断开。
- 受保护块 (<table> / <img>) 不被拆分: 先 flush 当前文本缓冲, 再以整块形式单独成 chunk,
  标记 protected=True, 降低表格碎片化与结构丢失。
- 每个 chunk 携带 page / has_table / has_image, 供检索与溯源使用。

产出 ChunkPlan (与 DB 模型解耦), 由 document_service 落库并分配索引/段落。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.logging_config import get_logger
from app.parsers.base import ParsedBlock, ParsedDocument

log = get_logger("chunker", "SPLIT")

_settings = get_settings()


@dataclass
class ChunkPlan:
    content: str
    page: int = 1
    has_table: bool = False
    has_image: bool = False
    protected: bool = False
    token_count: int = 0


def _count_tokens(text: str) -> int:
    # 粗估: 中文按字、英文按词, 取近似
    return max(1, len(text) // 2)


def _split_text_window(text: str, size: int, overlap: int) -> list[str]:
    """对纯文本做带 overlap 的滑动窗口切分, 优先在换行处断开。"""
    if len(text) <= size:
        return [text] if text.strip() else []
    paras = text.split("\n\n")
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 2 <= size:
            buf = (buf + "\n\n" + p).strip() if buf else p
        else:
            if buf:
                chunks.append(buf)
                # 必须清空: 否则当前段落走"硬切"分支时, 旧缓冲会被后续段落的
                # "buf + p" 再次带上, 造成内容重复入库(白占 token 预算)
                buf = ""
            # 单段超长 -> 硬切
            if len(p) > size:
                start = 0
                while start < len(p):
                    chunks.append(p[start : start + size])
                    start += size - overlap
            else:
                buf = p
    if buf:
        chunks.append(buf)
    # 施加 overlap: 后续块前缀上一块末尾 overlap 字符
    if overlap > 0 and len(chunks) > 1:
        out = [chunks[0]]
        for prev, cur in zip(chunks, chunks[1:]):
            carry = prev[-overlap:] if len(prev) >= overlap else prev
            out.append((carry + "\n" + cur).strip())
        chunks = out
    return chunks


def build_chunks(doc: ParsedDocument) -> list[ChunkPlan]:
    """主入口: 由 ParsedDocument 生成保护式 chunk 列表。"""
    size = _settings.chunk_size
    overlap = _settings.chunk_overlap
    plans: list[ChunkPlan] = []
    text_buffer: list[str] = []
    cur_page = 1

    def flush() -> None:
        nonlocal text_buffer
        joined = "\n\n".join(text_buffer).strip()
        text_buffer = []
        if not joined:
            return
        for piece in _split_text_window(joined, size, overlap):
            plans.append(
                ChunkPlan(content=piece, page=cur_page, token_count=_count_tokens(piece))
            )

    for block in doc.blocks:
        cur_page = max(cur_page, block.page)
        if block.type in ("table", "image"):
            # 受保护: 先落文本, 再整体成块
            flush()
            plans.append(
                ChunkPlan(
                    content=block.content
                    if block.type == "table"
                    else f"{block.content}\n{block.ocr_text}".strip(),
                    page=block.page,
                    has_table=block.type == "table",
                    has_image=block.type == "image",
                    protected=True,
                    token_count=_count_tokens(block.content),
                )
            )
        else:
            text_buffer.append(block.content)

    flush()
    log.info(f"chunking done -> {len(plans)} chunks (size={size}, overlap={overlap})")
    return plans
