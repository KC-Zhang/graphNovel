"""
书籍分章服务
将整本书的文本切分为有序的"章节"（episode），用于按阅读进度逐步展开图谱。
"""

import re
import logging
from dataclasses import dataclass
from functools import lru_cache
from statistics import median
from typing import List, Dict, Any, Optional, Set, Callable

import tiktoken

from ..utils.llm_client import LLMClient


logger = logging.getLogger(__name__)

# 章节标题识别的正则（按行匹配，行需较短）
_SEMANTIC_CHAPTER_PATTERNS = [
    # 中文：第X章 / 第X回 / 第X节 / 第X卷 / 第X部 / 第X篇
    re.compile(r'^\s*第\s*[0-9一二三四五六七八九十百千零两〇]+\s*[章回节卷篇部集]'),
    # 中文特殊章节
    re.compile(r'^\s*(序章|序言|序|楔子|引子|前言|后记|後記|尾声|尾聲|番外|终章|終章)\b'),
    # 英文：Chapter 1 / CHAPTER I / Prologue / Epilogue
    re.compile(r'^\s*(chapter|prologue|epilogue|part|book)\s+[0-9ivxlcdm]+', re.IGNORECASE),
    re.compile(r'^\s*(prologue|epilogue|preface|foreword|introduction)\s*$', re.IGNORECASE),
]

_NUMERIC_HEADING_PATTERN = re.compile(r'^\s*([0-9]{1,3})\s*[.、]?\s*$')

# 章节标题行的最大长度（避免把正文误判为标题）
_MAX_HEADING_LEN = 40

# 无标题时的兜底分段大小（字符数）
_FALLBACK_SEGMENT_SIZE = 4000
_FALLBACK_MIN_SIZE = 1500
_FALLBACK_TITLE_MAX_LEN = 72
_DENSE_RUN_MAX_MEDIAN_TOKENS = 120
_DUPLICATE_RUN_MIN_RATIO = 4
_LLM_STRUCTURE_SAMPLE_TOKENS = 20000
_LLM_STRUCTURE_MIN_CONFIDENCE = 0.65

_BOILERPLATE_TITLE_LINES = {
    "contents",
    "table of contents",
    "copyright",
    "all rights reserved",
}

_STRUCTURE_HEADING_PATTERNS = {
    "chapter_number",
    "standalone_number_then_title",
    "same_line_number_title",
    "chinese_numbered",
    "unknown",
}

_STRUCTURE_TITLE_MODES = {
    "auto",
    "heading_line",
    "next_lines",
    "same_line_after_number",
}


@dataclass(frozen=True)
class BookStructureStrategy:
    """LLM-detected rules for how this book marks and names body chapters."""

    confidence: float
    heading_pattern: str
    title_mode: str = "auto"
    title_lines_after_heading: int = 0
    subtitle_lines_after_title: int = 0
    ignore_toc: bool = True


@lru_cache(maxsize=1)
def _token_encoding():
    return tiktoken.get_encoding("o200k_base")


def _count_tokens(text: str) -> int:
    """Count tokens with OpenAI's standard tokenizer."""
    if not text:
        return 0
    return len(_token_encoding().encode(text))


def _truncate_to_token_budget(text: str, max_tokens: int) -> str:
    if not text:
        return ""
    tokens = _token_encoding().encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _token_encoding().decode(tokens[:max_tokens])


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _parse_structure_strategy(payload: Dict[str, Any]) -> Optional[BookStructureStrategy]:
    if not isinstance(payload, dict):
        return None

    title_strategy = payload.get("title_strategy")
    if not isinstance(title_strategy, dict):
        title_strategy = {}

    heading_pattern = str(
        payload.get("heading_pattern")
        or payload.get("chapter_pattern")
        or "unknown"
    ).strip().lower().replace("-", "_")
    if heading_pattern not in _STRUCTURE_HEADING_PATTERNS:
        heading_pattern = "unknown"

    title_mode = str(
        title_strategy.get("mode")
        or payload.get("title_mode")
        or "auto"
    ).strip().lower().replace("-", "_")
    if title_mode not in _STRUCTURE_TITLE_MODES:
        title_mode = "auto"

    return BookStructureStrategy(
        confidence=_bounded_float(payload.get("confidence"), 0.0, 0.0, 1.0),
        heading_pattern=heading_pattern,
        title_mode=title_mode,
        title_lines_after_heading=_bounded_int(
            title_strategy.get("title_lines_after_heading", payload.get("title_lines_after_heading")),
            0,
            0,
            3,
        ),
        subtitle_lines_after_title=_bounded_int(
            title_strategy.get("subtitle_lines_after_title", payload.get("subtitle_lines_after_title")),
            0,
            0,
            2,
        ),
        ignore_toc=bool(payload.get("ignore_toc", True)),
    )


def analyze_book_structure(
    text: str,
    llm_client: Optional[LLMClient] = None,
) -> Optional[BookStructureStrategy]:
    """
    Ask the primary LLM to infer the book's chapter structure from the
    beginning of the extracted text. The LLM does not return offsets.
    """
    if not text or not text.strip():
        return None

    try:
        client = llm_client or LLMClient()
    except Exception as exc:
        logger.info("跳过 LLM 分章结构分析，LLM 未配置或不可用: %s", exc)
        return None

    sample = _truncate_to_token_budget(text, _LLM_STRUCTURE_SAMPLE_TOKENS)
    messages = [
        {
            "role": "system",
            "content": (
                "You inspect flattened book text and infer the chapter structure. "
                "Return only valid JSON. Do not return chapter offsets or full segmentation. "
                "Decide how body chapter starts are marked and how display titles should be built."
            ),
        },
        {
            "role": "user",
            "content": (
                "Infer the structure for deterministic segmentation.\n\n"
                "Allowed heading_pattern values:\n"
                "- chapter_number: lines like Chapter 1, chapter 1, CHAPTER I, or 第1章\n"
                "- standalone_number_then_title: a line containing only 1, then title lines after it\n"
                "- same_line_number_title: a line like 1   Master Your Emotional Self\n"
                "- chinese_numbered: lines like 第一章 标题 or 第一回 标题\n"
                "- unknown\n\n"
                "Allowed title_strategy.mode values:\n"
                "- heading_line: title is on the heading line itself\n"
                "- next_lines: title is in short non-empty lines after the heading marker\n"
                "- same_line_after_number: title follows a number on the same line\n"
                "- auto\n\n"
                "Return JSON with this exact shape:\n"
                "{\n"
                '  "confidence": 0.0,\n'
                '  "heading_pattern": "unknown",\n'
                '  "ignore_toc": true,\n'
                '  "front_matter_markers": ["Contents"],\n'
                '  "title_strategy": {\n'
                '    "mode": "auto",\n'
                '    "title_lines_after_heading": 0,\n'
                '    "subtitle_lines_after_title": 0\n'
                "  },\n"
                '  "example_headings": ["Chapter 1"]\n'
                "}\n\n"
                "Use title_lines_after_heading and subtitle_lines_after_title to describe how each "
                "chapter display title should be constructed from nearby lines.\n\n"
                f"Book sample:\n\"\"\"\n{sample}\n\"\"\""
            ),
        },
    ]

    try:
        payload = client.chat_json(messages=messages, temperature=0.0, max_tokens=1200)
    except Exception as exc:
        logger.warning("LLM 分章结构分析失败，回退到确定性分章: %s", exc)
        return None

    strategy = _parse_structure_strategy(payload)
    if not strategy:
        return None
    logger.info(
        "LLM 分章结构分析结果: pattern=%s title_mode=%s title_lines=%s subtitle_lines=%s confidence=%.2f ignore_toc=%s",
        strategy.heading_pattern,
        strategy.title_mode,
        strategy.title_lines_after_heading,
        strategy.subtitle_lines_after_title,
        strategy.confidence,
        strategy.ignore_toc,
    )
    return strategy


def _is_semantic_heading(line: str) -> bool:
    """判断一行是否为语义明确的章节标题"""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_LEN:
        return False
    for pattern in _SEMANTIC_CHAPTER_PATTERNS:
        if pattern.match(stripped):
            return True
    return False


def _numeric_heading_value(line: str) -> Optional[int]:
    """返回纯数字标题的数值；非纯数字标题返回 None。"""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_LEN:
        return None
    match = _NUMERIC_HEADING_PATTERN.match(stripped)
    return int(match.group(1)) if match else None


def _same_line_number_title_parts(line: str) -> Optional[tuple[int, str]]:
    stripped = re.sub(r'\s+', ' ', (line or '').strip())
    if not stripped or len(stripped) > 120:
        return None
    match = re.match(r'^([0-9]{1,3})\s+(.+)$', stripped)
    if not match:
        return None
    title = _clean_title_candidate(match.group(2))
    if not _is_chapter_title_fragment(title):
        return None
    return int(match.group(1)), title


def _contains_sentence_punctuation(line: str) -> bool:
    return bool(re.search(r'[。！？.!?]', line or ''))


def _is_numbered_title_line(line: str) -> bool:
    line = _clean_title_candidate(line)
    if not _is_chapter_title_fragment(line):
        return False
    if _contains_sentence_punctuation(line):
        return False
    if len(line) > 80:
        return False
    if len(line.split()) > 10:
        return False
    return True


def _standalone_number_title_indices(lines: List[str]) -> List[int]:
    indices: List[int] = []
    for i, line in enumerate(lines):
        if _numeric_heading_value(line) is None:
            continue
        _, title = _next_nonempty_line(lines, i + 1)
        if _is_numbered_title_line(title):
            indices.append(i)
    return indices


def _chapter_number_label(line: str) -> Optional[str]:
    """返回章节编号文本，兼容 PDF 抽取出的空格数字，如 1 0。"""
    stripped = re.sub(r'\s+', ' ', (line or '').strip())
    if not stripped or len(stripped) > _MAX_HEADING_LEN:
        return None
    numeric_value = _numeric_heading_value(stripped)
    if numeric_value is not None:
        return str(numeric_value)
    if re.fullmatch(r'(?:\d\s*){1,3}', stripped):
        return re.sub(r'\s+', '', stripped)
    if re.fullmatch(r'[ivxlcdmIVXLCDM]+', stripped):
        return stripped.upper()
    return None


def _roman_to_int(value: str) -> Optional[int]:
    value = (value or '').strip().upper()
    if not value or not re.fullmatch(r'[IVXLCDM]+', value):
        return None
    numerals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total = 0
    prev = 0
    for ch in reversed(value):
        current = numerals[ch]
        if current < prev:
            total -= current
        else:
            total += current
            prev = current
    return total if total > 0 else None


def _chinese_number_to_int(value: str) -> Optional[int]:
    value = re.sub(r'\s+', '', value or '')
    if not value:
        return None
    if value.isdigit():
        return int(value)
    digits = {
        '零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
        '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
    }
    units = {'十': 10, '百': 100, '千': 1000}
    if all(ch in digits for ch in value):
        n = 0
        for ch in value:
            n = n * 10 + digits[ch]
        return n
    total = 0
    current = 0
    seen = False
    for ch in value:
        if ch in digits:
            current = digits[ch]
            seen = True
        elif ch in units:
            total += (current or 1) * units[ch]
            current = 0
            seen = True
        else:
            return None
    total += current
    return total if seen and total > 0 else None


def _heading_number_at(lines: List[str], line_no: int) -> Optional[int]:
    """Return the chapter/order number for a candidate heading when one is explicit."""
    line = re.sub(r'\s+', ' ', (lines[line_no] if line_no < len(lines) else '').strip())
    if _is_chapter_marker_line(line):
        _, number = _next_nonempty_line(lines, line_no + 1)
        label = _chapter_number_label(number)
        if label is None:
            return None
        return int(label) if label.isdigit() else _roman_to_int(label)

    numeric_value = _numeric_heading_value(line)
    if numeric_value is not None:
        return numeric_value

    same_line_number_title = _same_line_number_title_parts(line)
    if same_line_number_title is not None:
        return same_line_number_title[0]

    english = re.match(r'^\s*(?:chapter|part|book)\s+([0-9]+|[ivxlcdm]+)\b', line, re.IGNORECASE)
    if english:
        raw = english.group(1)
        return int(raw) if raw.isdigit() else _roman_to_int(raw)

    chinese = re.match(r'^\s*第\s*([0-9一二三四五六七八九十百千零两〇]+)\s*[章回节卷篇部集]', line)
    if chinese:
        return _chinese_number_to_int(chinese.group(1))

    return None


def _compact_alpha(line: str) -> str:
    return re.sub(r'[^A-Za-z]', '', line or '').lower()


def _is_chapter_marker_line(line: str) -> bool:
    """识别 PDF 中常见的独立章节标记，如 C H A P T E R。"""
    return _compact_alpha(line) == 'chapter' and not re.search(r'\d', line or '')


def _next_nonempty_line(lines: List[str], start: int) -> tuple[Optional[int], str]:
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        if stripped:
            return i, stripped
    return None, ''


def _chapter_marker_indices(lines: List[str]) -> List[int]:
    """找出多行 PDF 章节标记：C H A P T E R / 1 / Title。"""
    indices: List[int] = []
    for i, line in enumerate(lines):
        if not _is_chapter_marker_line(line):
            continue
        number_idx, number = _next_nonempty_line(lines, i + 1)
        if number_idx is None:
            continue
        if _chapter_number_label(number) is None:
            continue
        title_idx, title = _next_nonempty_line(lines, number_idx + 1)
        if title_idx is None or not _is_chapter_title_fragment(title):
            continue
        indices.append(i)
    return indices


def _is_chapter_title_fragment(line: str) -> bool:
    line = _clean_title_candidate(line)
    if not line or len(line) > 100:
        return False
    if _is_chapter_marker_line(line) or _chapter_number_label(line) is not None:
        return False
    if _is_semantic_heading(line):
        return False
    if not re.search(r'[\w\u4e00-\u9fff]', line):
        return False
    return True


def _should_join_chapter_title_line(previous: str, candidate: str) -> bool:
    candidate = _clean_title_candidate(candidate)
    if not _is_chapter_title_fragment(candidate):
        return False
    if len(candidate) <= 1:
        return False
    if candidate.startswith(('—', '-', '–', '"', "'", '“', '‘')):
        return False
    if re.search(r'[。！？.!?]\s*$', candidate):
        return False
    if previous.endswith((',', ':', ';', '-', '—', '–', '&')):
        return True
    previous_last_word = re.sub(r'[^A-Za-z]+', '', previous.split()[-1]).lower() if previous.split() else ''
    if previous_last_word in {'and', 'or', 'of', 'to', 'by', 'with', 'from', 'into', 'the'}:
        return True
    return len(candidate) <= 24 and len(candidate.split()) <= 3


def _chapter_marker_title(lines: List[str], number_line_no: int) -> str:
    title_idx, first = _next_nonempty_line(lines, number_line_no + 1)
    if title_idx is None or not _is_chapter_title_fragment(first):
        return ''

    title_lines = [_clean_title_candidate(first)]
    next_idx, next_line = _next_nonempty_line(lines, title_idx + 1)
    if next_idx is not None and _should_join_chapter_title_line(title_lines[-1], next_line):
        title_lines.append(_clean_title_candidate(next_line))

    return ' '.join(title_lines)


def _looks_like_numbered_chapter_sequence(values: List[int], offsets: List[int], text: str) -> bool:
    """
    判断纯数字标题是否更像章节编号而不是 PDF 页码。

    PDF 提取文本常把页码放在独立短行上，若直接把所有纯数字行当章节，
    会把一本书切成几百个页面。这里仅接受从 1 开始、基本连续、数量合理的
    数字序列作为章节标题。
    """
    if len(values) < 2:
        return False
    if values[0] != 1:
        return False
    if len(values) > 80:
        return False
    deltas = [b - a for a, b in zip(values, values[1:])]
    if not deltas:
        return False
    adjacent_ratio = sum(1 for d in deltas if d == 1) / len(deltas)
    if adjacent_ratio < 0.7:
        return False
    if any(d <= 0 or d > 3 for d in deltas):
        return False
    spans = [
        _count_tokens(text[offsets[i]:offsets[i + 1] if i + 1 < len(offsets) else len(text)])
        for i in range(len(offsets))
    ]
    return median(spans) >= 5


def _numbered_heading_runs(
    heading_indices: List[int],
    lines: List[str],
    offsets: List[int],
    text: str,
) -> List[Dict[str, Any]]:
    """Group explicit-number heading candidates into monotonic runs."""
    runs: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    numbered = []
    for pos, line_no in enumerate(heading_indices):
        number = _heading_number_at(lines, line_no)
        if number is not None:
            numbered.append((pos, line_no, number))

    for pos, line_no, number in numbered:
        if current is None or number <= current["numbers"][-1]:
            current = {"positions": [], "line_numbers": [], "numbers": []}
            runs.append(current)
        current["positions"].append(pos)
        current["line_numbers"].append(line_no)
        current["numbers"].append(number)

    for run in runs:
        spans = []
        for pos in run["positions"]:
            start = offsets[heading_indices[pos]]
            end = offsets[heading_indices[pos + 1]] if pos + 1 < len(heading_indices) else len(text)
            spans.append(_count_tokens(text[start:end]))
        run["median_tokens"] = median(spans) if spans else 0
        run["count"] = len(run["positions"])
        run["first_position"] = run["positions"][0] if run["positions"] else 0
        run["first_offset"] = offsets[run["line_numbers"][0]] if run["line_numbers"] else 0
        run["score"] = run["median_tokens"] * min(run["count"], 12)
    return runs


def _select_heading_indices(
    heading_indices: List[int],
    lines: List[str],
    offsets: List[int],
    text: str,
) -> List[int]:
    """
    Remove dense front-matter heading runs, such as tables of contents, using
    relative token-span evidence instead of book-specific patterns.
    """
    if len(heading_indices) < 4:
        return heading_indices

    runs = [run for run in _numbered_heading_runs(heading_indices, lines, offsets, text) if run["count"] >= 3]
    if len(runs) < 2:
        return heading_indices

    first = runs[0]
    best = max(runs[1:], key=lambda run: run["score"], default=None)
    if not best:
        return heading_indices

    first_dense = first["median_tokens"] <= _DENSE_RUN_MAX_MEDIAN_TOKENS
    first_irregular_before_body = (
        bool(first["numbers"])
        and bool(best["numbers"])
        and first["numbers"][0] != 1
        and best["numbers"][0] == 1
    )
    much_larger_later = best["median_tokens"] >= max(
        first["median_tokens"] * _DUPLICATE_RUN_MIN_RATIO,
        _DENSE_RUN_MAX_MEDIAN_TOKENS,
    )
    if not ((first_dense or first_irregular_before_body) and much_larger_later):
        return heading_indices

    start_position = best["first_position"]
    end_position = len(heading_indices)
    following_runs = [run for run in runs if run["first_position"] > start_position]
    if following_runs:
        next_run = min(following_runs, key=lambda run: run["first_position"])
        next_is_much_smaller = next_run["median_tokens"] * _DUPLICATE_RUN_MIN_RATIO <= best["median_tokens"]
        if next_run["median_tokens"] <= _DENSE_RUN_MAX_MEDIAN_TOKENS or next_is_much_smaller:
            end_position = next_run["first_position"]

    return heading_indices[start_position:end_position]


def _heading_title(lines: List[str], line_no: int) -> str:
    """提取标题；英文 Chapter 行后紧跟短标题时合并展示。"""
    title = lines[line_no].strip()
    if _is_chapter_marker_line(title):
        number_idx, number = _next_nonempty_line(lines, line_no + 1)
        number_label = _chapter_number_label(number)
        marker_title = _chapter_marker_title(lines, number_idx or line_no)
        if number_label and marker_title:
            return f"Chapter {number_label} — {marker_title}"
        if number_label:
            return f"Chapter {number_label}"
        return "Chapter"

    english = re.match(
        r'^\s*(chapter|part|book)\s+([0-9]+|[ivxlcdm]+)\b[\s.:\-–—]*(.*)$',
        title,
        re.IGNORECASE,
    )
    if not english:
        return title
    rest = _clean_title_candidate(english.group(3))
    if rest and _is_chapter_title_fragment(rest):
        return title
    if line_no + 1 >= len(lines):
        return title
    collected_title, _ = _collect_numbered_title_after(lines, line_no + 1)
    if collected_title:
        return f"{title} — {collected_title}"
    return title


def _line_offsets(lines: List[str]) -> List[int]:
    offsets: List[int] = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1  # +1 为换行符
    return offsets


def _build_episodes_from_headings(
    text: str,
    lines: List[str],
    offsets: List[int],
    heading_indices: List[int],
    title_for_line: Callable[[int], str],
) -> List[Dict[str, Any]]:
    if len(heading_indices) < 2:
        return []

    episodes: List[Dict[str, Any]] = []

    first_heading_line = heading_indices[0]
    preamble = text[:offsets[first_heading_line]].strip()
    if len(preamble) >= 200:
        episodes.append({
            "title": _default_preamble_title(preamble),
            "start_char": 0,
            "end_char": offsets[first_heading_line],
        })

    for idx, line_no in enumerate(heading_indices):
        start = offsets[line_no]
        if idx + 1 < len(heading_indices):
            end = offsets[heading_indices[idx + 1]]
        else:
            end = len(text)
        episodes.append({
            "title": title_for_line(line_no),
            "start_char": start,
            "end_char": end,
        })

    return _merge_tiny_episodes(text, episodes)


def _is_english_chapter_number_line(line: str) -> bool:
    return bool(re.match(r'^\s*(?:chapter|part|book)\s+([0-9]+|[ivxlcdm]+)\b', line or '', re.IGNORECASE))


def _collect_title_lines_after(lines: List[str], start: int, count: int) -> List[str]:
    title_lines: List[str] = []
    cursor = start
    for _ in range(count):
        line_no, line = _next_nonempty_line(lines, cursor)
        if line_no is None:
            break
        clean = _clean_title_candidate(line)
        if not _is_chapter_title_fragment(clean):
            break
        title_lines.append(clean)
        cursor = line_no + 1
    return title_lines


def _collect_structured_title_parts_after(
    lines: List[str],
    start: int,
    title_line_groups: int,
    subtitle_line_groups: int,
) -> List[str]:
    parts: List[str] = []
    cursor = start
    total_groups = title_line_groups + subtitle_line_groups
    for group_index in range(total_groups):
        line_no, line = _next_nonempty_line(lines, cursor)
        if line_no is None:
            break
        clean = _clean_title_candidate(line)
        if not _is_chapter_title_fragment(clean):
            break
        if group_index >= title_line_groups and _contains_sentence_punctuation(clean):
            break

        group_lines = [clean]
        cursor = line_no + 1

        if group_index < title_line_groups:
            while True:
                next_idx, next_line = _next_nonempty_line(lines, cursor)
                if next_idx is None or not _should_join_chapter_title_line(group_lines[-1], next_line):
                    break
                group_lines.append(_clean_title_candidate(next_line))
                cursor = next_idx + 1

        parts.append(' '.join(group_lines))

    return parts


def _collect_numbered_title_after(lines: List[str], start: int) -> tuple[str, int]:
    line_no, line = _next_nonempty_line(lines, start)
    if line_no is None or not _is_numbered_title_line(line):
        return "", start

    title_lines = [_clean_title_candidate(line)]
    cursor = line_no + 1
    while True:
        next_idx, next_line = _next_nonempty_line(lines, cursor)
        if next_idx is None or not _should_join_chapter_title_line(title_lines[-1], next_line):
            break
        clean_next = _clean_title_candidate(next_line)
        if not _is_numbered_title_line(clean_next):
            break
        title_lines.append(clean_next)
        cursor = next_idx + 1

    return ' '.join(title_lines), cursor


def _numbered_heading_title(lines: List[str], line_no: int) -> str:
    number = _heading_number_at(lines, line_no)
    if number is None:
        return _heading_title(lines, line_no)

    title, cursor = _collect_numbered_title_after(lines, line_no + 1)
    if not title:
        return _heading_title(lines, line_no)

    parts = [title]
    subtitle_idx, subtitle = _next_nonempty_line(lines, cursor)
    if subtitle_idx is not None and _is_numbered_title_line(subtitle):
        parts.append(_clean_title_candidate(subtitle))

    return f"Chapter {number} — {' — '.join(parts)}"


def _strategy_heading_indices(lines: List[str], strategy: BookStructureStrategy) -> List[int]:
    indices: List[int] = []
    for i, line in enumerate(lines):
        if strategy.heading_pattern == "chapter_number":
            if _is_chapter_marker_line(line) or _is_english_chapter_number_line(line) or re.match(
                r'^\s*第\s*[0-9一二三四五六七八九十百千零两〇]+\s*[章回节卷篇部集]',
                line or '',
            ):
                indices.append(i)
        elif strategy.heading_pattern == "standalone_number_then_title":
            if _numeric_heading_value(line) is not None:
                _, title = _next_nonempty_line(lines, i + 1)
                if _is_chapter_title_fragment(title):
                    indices.append(i)
        elif strategy.heading_pattern == "same_line_number_title":
            if _same_line_number_title_parts(line) is not None:
                indices.append(i)
        elif strategy.heading_pattern == "chinese_numbered":
            if re.match(r'^\s*第\s*[0-9一二三四五六七八九十百千零两〇]+\s*[章回节卷篇部集]', line or ''):
                indices.append(i)

    return indices


def _strategy_heading_title(lines: List[str], line_no: int, strategy: BookStructureStrategy) -> str:
    line = lines[line_no].strip()
    number = _heading_number_at(lines, line_no)

    if strategy.title_mode == "heading_line":
        return _heading_title(lines, line_no)

    title_parts: List[str] = []
    following_lines_to_collect = strategy.title_lines_after_heading + strategy.subtitle_lines_after_title

    english = re.match(
        r'^\s*(chapter|part|book)\s+([0-9]+|[ivxlcdm]+)\b[\s.:\-–—]*(.*)$',
        line,
        re.IGNORECASE,
    )
    if english:
        rest = _clean_title_candidate(english.group(3))
        if rest and _is_chapter_title_fragment(rest):
            title_parts.append(rest)
            following_lines_to_collect = strategy.subtitle_lines_after_title

    same_line = _same_line_number_title_parts(line)
    if same_line and strategy.title_mode in {"auto", "same_line_after_number"}:
        title_parts.append(same_line[1])
        following_lines_to_collect = strategy.subtitle_lines_after_title

    if following_lines_to_collect:
        if title_parts:
            title_parts.extend(_collect_structured_title_parts_after(lines, line_no + 1, 0, following_lines_to_collect))
        else:
            title_parts.extend(
                _collect_structured_title_parts_after(
                    lines,
                    line_no + 1,
                    strategy.title_lines_after_heading,
                    strategy.subtitle_lines_after_title,
                )
            )

    if title_parts:
        prefix = f"Chapter {number}" if number is not None else _heading_title(lines, line_no)
        return f"{prefix} — {' — '.join(title_parts)}"

    return _heading_title(lines, line_no)


def _split_by_structure_strategy(text: str, strategy: BookStructureStrategy) -> List[Dict[str, Any]]:
    if strategy.confidence < _LLM_STRUCTURE_MIN_CONFIDENCE or strategy.heading_pattern == "unknown":
        return []

    lines = text.split('\n')
    offsets = _line_offsets(lines)
    heading_indices = _strategy_heading_indices(lines, strategy)
    heading_indices = _select_heading_indices(heading_indices, lines, offsets, text)

    return _build_episodes_from_headings(
        text,
        lines,
        offsets,
        heading_indices,
        lambda line_no: _strategy_heading_title(lines, line_no, strategy),
    )


def _split_by_headings(text: str) -> List[Dict[str, Any]]:
    """按章节标题切分。返回带 start_char/end_char/title 的段落列表；若标题过少返回空。"""
    lines = text.split('\n')
    offsets = _line_offsets(lines)

    chapter_marker_indices = _chapter_marker_indices(lines)
    semantic_heading_indices = [i for i, line in enumerate(lines) if _is_semantic_heading(line)]
    standalone_title_indices = _standalone_number_title_indices(lines)
    numeric_candidates = [
        (i, _numeric_heading_value(line))
        for i, line in enumerate(lines)
        if _numeric_heading_value(line) is not None
    ]
    title_for_line: Callable[[int], str] = lambda line_no: _heading_title(lines, line_no)

    if len(chapter_marker_indices) >= 2:
        heading_indices = chapter_marker_indices
    elif _looks_like_numbered_chapter_sequence(
        [value for value in (_numeric_heading_value(lines[i]) for i in standalone_title_indices) if value is not None],
        [offsets[i] for i in standalone_title_indices],
        text,
    ):
        heading_indices = standalone_title_indices
        title_for_line = lambda line_no: _numbered_heading_title(lines, line_no)
    elif len(semantic_heading_indices) >= 2:
        heading_indices = semantic_heading_indices
    else:
        numeric_indices = [i for i, _ in numeric_candidates]
        numeric_values = [v for _, v in numeric_candidates if v is not None]
        numeric_offsets = [offsets[i] for i in numeric_indices]
        if _looks_like_numbered_chapter_sequence(numeric_values, numeric_offsets, text):
            heading_indices = numeric_indices
        else:
            heading_indices = semantic_heading_indices

    heading_indices = _select_heading_indices(heading_indices, lines, offsets, text)

    # 标题太少，不足以形成章节结构
    if len(heading_indices) < 2:
        return []

    return _build_episodes_from_headings(text, lines, offsets, heading_indices, title_for_line)


def _default_preamble_title(preamble: str) -> str:
    """为前言段落生成标题"""
    # 简单判断语言
    if re.search(r'[\u4e00-\u9fff]', preamble):
        return "前言"
    return "Preface"


def _merge_tiny_episodes(text: str, episodes: List[Dict[str, Any]], min_len: int = 40) -> List[Dict[str, Any]]:
    """把过短的章节合并到前一章"""
    if not episodes:
        return episodes
    merged: List[Dict[str, Any]] = []
    for ep in episodes:
        content_len = len(text[ep["start_char"]:ep["end_char"]].strip())
        if merged and content_len < min_len:
            merged[-1]["end_char"] = ep["end_char"]
        else:
            merged.append(ep)
    return merged


def _split_fixed_size(text: str) -> List[Dict[str, Any]]:
    """无章节标题时的兜底：按固定大小在段落/句子边界切分"""
    episodes: List[Dict[str, Any]] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + _FALLBACK_SEGMENT_SIZE, n)
        if end < n:
            # 优先在段落边界切分，其次句子边界
            window = text[start:end]
            break_pos = -1
            for sep in ['\n\n', '。', '！', '？', '.\n', '!\n', '?\n', '. ', '! ', '? ', '\n']:
                cand = window.rfind(sep)
                if cand != -1 and cand > _FALLBACK_MIN_SIZE:
                    break_pos = cand + len(sep)
                    break
            if break_pos != -1:
                end = start + break_pos
        episodes.append({
            "title": None,  # 稍后统一编号
            "start_char": start,
            "end_char": end,
        })
        start = end
    return episodes


def _line_key(line: str) -> str:
    return re.sub(r'\s+', ' ', (line or '').strip()).lower()


def _common_short_lines(text: str) -> Set[str]:
    """找出 PDF 页眉/书名等重复短行，兜底命名时跳过。"""
    counts: Dict[str, int] = {}
    for raw in text.splitlines():
        line = re.sub(r'\s+', ' ', raw.strip())
        if not line or len(line) > 80:
            continue
        if _numeric_heading_value(line) is not None:
            continue
        if not re.search(r'[\w\u4e00-\u9fff]', line):
            continue
        key = _line_key(line)
        counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count >= 2}


def _clean_title_candidate(line: str) -> str:
    line = re.sub(r'\s+', ' ', (line or '').strip())
    line = re.sub(r'^[•\-–—*]+\s*', '', line)
    return line.strip(' "\'“”‘’')


def _is_useful_title_line(line: str, common_lines: Set[str]) -> bool:
    line = _clean_title_candidate(line)
    if not line:
        return False
    if _numeric_heading_value(line) is not None:
        return False
    key = _line_key(line)
    if key in common_lines or key in _BOILERPLATE_TITLE_LINES:
        return False
    if not re.search(r'[\w\u4e00-\u9fff]', line):
        return False
    if re.fullmatch(r'[ivxlcdmIVXLCDM]+', line):
        return False
    return True


def _shorten_title(line: str, max_len: int = _FALLBACK_TITLE_MAX_LEN) -> str:
    line = _clean_title_candidate(line)
    if len(line) <= max_len:
        return line
    cut = line[:max_len].rstrip()
    for sep in ['. ', '。', '！', '？', '? ', '! ', ': ', ' - ', ' — ', ', ', '，']:
        idx = cut.rfind(sep)
        if idx >= 24:
            cut = cut[:idx].rstrip()
            break
    return cut.rstrip('.,;:，。；：') + '...'


def _fallback_title(segment_text: str, index: int, is_cjk: bool, common_lines: Set[str]) -> str:
    """为固定大小兜底分段生成可读标题。"""
    useful_lines = []
    for raw in segment_text[:1600].splitlines():
        line = _clean_title_candidate(raw)
        if not _is_useful_title_line(line, common_lines):
            continue
        useful_lines.append(line)

    # 短行通常是章节/小节标题；固定分段可能从上一段正文尾部开始，
    # 所以优先寻找附近的标题行，再退回到正文摘句。
    for line in useful_lines:
        if len(line) <= _FALLBACK_TITLE_MAX_LEN and not re.search(r'[。！？.!?]\s*$', line):
            return _shorten_title(line)

    for line in useful_lines:
        return _shorten_title(line)

    return f"第 {index + 1} 节" if is_cjk else f"Section {index + 1}"


def _finalize_episodes(text: str, episodes: List[Dict[str, Any]], used_fallback: bool) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    is_cjk = bool(re.search(r'[\u4e00-\u9fff]', text[:2000]))
    common_lines = _common_short_lines(text) if used_fallback else set()
    for i, ep in enumerate(episodes):
        segment_text = text[ep["start_char"]:ep["end_char"]].strip()
        title = ep.get("title")
        if not title:
            title = _fallback_title(segment_text, i, is_cjk, common_lines)
        result.append({
            "index": i,
            "title": title,
            "start_char": ep["start_char"],
            "end_char": ep["end_char"],
            "char_count": len(segment_text),
            "text": segment_text,
        })

    return result


def _episode_validation_report(text: str, episodes: List[Dict[str, Any]]) -> tuple[bool, Dict[str, Any]]:
    if len(episodes) < 2:
        return False, {"reason": "too_few_episodes", "episodes": len(episodes)}

    body_episodes = [
        ep for ep in episodes
        if ep.get("title") not in {"Preface", "前言"}
    ]
    if len(body_episodes) < 2 or len(body_episodes) > 120:
        return False, {
            "reason": "implausible_body_episode_count",
            "episodes": len(episodes),
            "body_episodes": len(body_episodes),
        }

    token_spans = [
        _count_tokens(text[ep["start_char"]:ep["end_char"]].strip())
        for ep in body_episodes
    ]
    if not token_spans or max(token_spans) < 10:
        return False, {
            "reason": "tiny_max_token_span",
            "episodes": len(episodes),
            "body_episodes": len(body_episodes),
            "max_tokens": max(token_spans) if token_spans else 0,
        }

    median_tokens = median(token_spans)
    max_tokens = max(token_spans)
    report = {
        "reason": "ok",
        "episodes": len(episodes),
        "body_episodes": len(body_episodes),
        "median_tokens": int(median_tokens),
        "max_tokens": int(max_tokens),
    }
    if len(text) > 10000 and median_tokens < 80:
        report["reason"] = "median_token_span_too_small"
        return False, report

    return True, report


def _episodes_are_usable(text: str, episodes: List[Dict[str, Any]]) -> bool:
    usable, _ = _episode_validation_report(text, episodes)
    return usable

    return True


def segment_book(text: str) -> List[Dict[str, Any]]:
    """
    将书籍文本切分为有序章节。

    Args:
        text: 预处理后的完整书籍文本

    Returns:
        章节列表，每项包含 {index, title, start_char, end_char, char_count, text}
    """
    if not text or not text.strip():
        return []

    episodes = _split_by_headings(text)
    used_fallback = False
    if not episodes:
        episodes = _split_fixed_size(text)
        used_fallback = True

    return _finalize_episodes(text, episodes, used_fallback)


def segment_book_hybrid(text: str, llm_client: Optional[LLMClient] = None) -> List[Dict[str, Any]]:
    """
    Try LLM-guided structure detection first, then fall back to deterministic
    segmentation if the LLM is unavailable or its strategy does not validate.
    """
    if not text or not text.strip():
        return []

    strategy = analyze_book_structure(text, llm_client=llm_client)
    if strategy:
        episodes = _split_by_structure_strategy(text, strategy)
        usable, validation = _episode_validation_report(text, episodes)
        if usable:
            logger.info(
                "使用 LLM 分章结构策略: pattern=%s title_mode=%s confidence=%.2f episodes=%s body_episodes=%s median_tokens=%s max_tokens=%s",
                strategy.heading_pattern,
                strategy.title_mode,
                strategy.confidence,
                validation.get("episodes"),
                validation.get("body_episodes"),
                validation.get("median_tokens"),
                validation.get("max_tokens"),
            )
            return _finalize_episodes(text, episodes, used_fallback=False)
        logger.info(
            "LLM 分章结构策略未通过校验，回退到确定性分章: pattern=%s title_mode=%s confidence=%.2f reason=%s episodes=%s body_episodes=%s median_tokens=%s max_tokens=%s",
            strategy.heading_pattern,
            strategy.title_mode,
            strategy.confidence,
            validation.get("reason"),
            validation.get("episodes"),
            validation.get("body_episodes"),
            validation.get("median_tokens"),
            validation.get("max_tokens"),
        )

    fallback_episodes = segment_book(text)
    logger.info("确定性分章完成: episodes=%s", len(fallback_episodes))
    return fallback_episodes
