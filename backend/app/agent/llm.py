"""LLM 服务: 真实大模型流式生成 + Mock 规则化生成器。

真实: 走 OpenAI 兼容接口 (DashScope qwen 等), 支持 stream。
Mock: 基于检索证据生成"带引用"的确定性回答, 逐 token 流式吐出,
      保证离线演示时 Agent 对话与来源溯源都可用。

无论哪种, generate_stream() 都是生成器, 产出逐片文本, 供 SSE 推送。
"""
from __future__ import annotations

from app.config import get_settings
from app.logging_config import get_logger

log = get_logger("agent", "LLM")

_settings = get_settings()


class LLMService:
    def __init__(self) -> None:
        self.mode = "mock"
        self._client = None
        if not _settings.mock_mode and _settings.llm_api_key:
            try:
                from openai import OpenAI  # type: ignore

                self._client = OpenAI(
                    api_key=_settings.llm_api_key, base_url=_settings.llm_base_url
                )
                self.mode = "real"
                log.info(f"llm provider = real ({_settings.llm_model})")
            except Exception as exc:  # noqa: BLE001
                log.warning(f"llm client init failed ({exc}); mock")
                self.mode = "mock"
        else:
            log.info("llm provider = mock (rule-based generator)")

    def generate_stream(self, system: str, prompt: str):
        """流式生成, 返回 str 生成器。"""
        if self.mode == "real" and self._client is not None:
            try:
                stream = self._client.chat.completions.create(
                    model=_settings.llm_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
                return
            except Exception as exc:  # noqa: BLE001
                log.warning(f"real llm stream failed ({exc}); mock fallback")
        yield from self._mock_stream(system, prompt)

    def _mock_stream(self, system: str, prompt: str):
        answer = self._mock_answer(system, prompt)
        # 逐字符/逐词吐出, 模拟流式
        import re

        for tok in re.split(r"(\s+)", answer):
            yield tok

    def _mock_answer(self, system: str, prompt: str) -> str:
        """规则化生成: 从 prompt 提取 [EVIDENCE] 段, 组织成带引用回答。"""
        # prompt 中我们约定把证据放在 <<EVIDENCE>> ... <<END>> 之间
        ev_start = prompt.find("<<EVIDENCE>>")
        ev_end = prompt.find("<<END>>")
        has_evidence = ev_start != -1 and ev_end != -1
        question = prompt.split("<<QUESTION>>")[-1].split("<<EVIDENCE>>")[0].strip()
        if not has_evidence:
            return (
                "抱歉，知识库中未检索到与您问题相关的证据，"
                "为避免编造，我暂不作答。请尝试调整关键词或确认文档已入库。"
            )
        evidence = prompt[ev_start + len("<<EVIDENCE>>") : ev_end].strip()
        # 取前若干证据片段
        snippets = [e for e in evidence.split("\n---\n") if e.strip()][:3]
        cited = "\n".join(f"{i+1}. {s[:120]}" for i, s in enumerate(snippets))
        return (
            f"根据企业知识库中的相关资料，关于您的问题「{question}」，"
            f"整理回答如下：\n\n"
            f"{evidence[:400]}\n\n"
            f"【引用证据】\n{cited}\n\n"
            f"（以上结论均来自知识库检索结果，可查看右侧来源溯源。）"
        )
