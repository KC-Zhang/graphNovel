"""LLM-backed coarse document classification used to choose the PDF default view."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..utils.llm_client import LLMClient


logger = logging.getLogger(__name__)

DOCUMENT_SAMPLE_CHARS = 2000
_KINDS = {"novel", "textbook", "uncertain"}
_TEXTBOOK_ALIASES = {
    "academic",
    "academic_paper",
    "article",
    "manual",
    "nonfiction",
    "non_fiction",
    "paper",
    "reference",
    "report",
    "text_book",
}


@dataclass(frozen=True)
class DocumentClassification:
    kind: str
    confidence: float


def document_sample(text: str, limit: int = DOCUMENT_SAMPLE_CHARS) -> str:
    """返回首个有内容的文本样本，略过空行并严格限制发送给 LLM 的长度。"""
    nonempty_lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return "\n".join(nonempty_lines)[: max(0, limit)]


def _bounded_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _parse_classification(payload: Dict[str, Any]) -> DocumentClassification:
    raw_kind = str(
        payload.get("document_kind")
        or payload.get("kind")
        or payload.get("text_type")
        or "uncertain"
    ).strip().casefold().replace("-", "_").replace(" ", "_")
    if raw_kind in _TEXTBOOK_ALIASES:
        raw_kind = "textbook"
    if raw_kind not in _KINDS:
        raw_kind = "uncertain"
    confidence = _bounded_confidence(payload.get("confidence"))
    if raw_kind == "uncertain":
        confidence = min(confidence, 0.5)
    return DocumentClassification(raw_kind, confidence)


def classify_document(
    text: str,
    llm_client: Optional[LLMClient] = None,
) -> DocumentClassification:
    """
    Classify a PDF as novel, textbook-like structured nonfiction, or uncertain.

    Any missing configuration, request error, or malformed response deliberately
    yields ``uncertain`` so upload remains usable and the user can choose a mode.
    """
    sample = document_sample(text)
    if not sample:
        return DocumentClassification("uncertain", 0.0)

    try:
        client = llm_client or LLMClient()
        payload = client.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the supplied beginning of a PDF. Return only JSON with "
                        "document_kind and confidence. document_kind must be novel, textbook, "
                        "or uncertain. Use textbook for textbooks, academic papers, reports, "
                        "manuals, reference works, and other layout-dependent structured nonfiction. "
                        "Use novel for narrative fiction best read as reflowed chapters."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        'Return {"document_kind":"novel|textbook|uncertain","confidence":0.0}.\n\n'
                        f'PDF sample (at most {DOCUMENT_SAMPLE_CHARS} characters):\n"""\n{sample}\n"""'
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=120,
        )
        if not isinstance(payload, dict):
            raise ValueError("classification response is not an object")
        return _parse_classification(payload)
    except Exception as exc:
        # 不记录样本或原始书籍文本。
        logger.warning(
            "PDF 文档分类失败，由用户选择阅读模式 (error_type=%s)",
            type(exc).__name__,
        )
        return DocumentClassification("uncertain", 0.0)
