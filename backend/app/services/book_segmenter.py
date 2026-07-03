"""
书籍分章服务
将整本书的文本切分为有序的"章节"（episode），用于按阅读进度逐步展开图谱。
"""

import re
from statistics import median
from typing import List, Dict, Any, Optional, Set


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

_BOILERPLATE_TITLE_LINES = {
    "contents",
    "table of contents",
    "copyright",
    "all rights reserved",
}


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


def _compact_alpha(line: str) -> str:
    return re.sub(r'[^A-Za-z]', '', line or '').lower()


def _is_chapter_marker_line(line: str) -> bool:
    """识别 PDF 中常见的独立章节标记，如 C H A P T E R。"""
    return _compact_alpha(line) == 'chapter'


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


def _looks_like_numbered_chapter_sequence(values: List[int], offsets: List[int], text_len: int) -> bool:
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
        (offsets[i + 1] if i + 1 < len(offsets) else text_len) - offsets[i]
        for i in range(len(offsets))
    ]
    return median(spans) >= 40


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
    if not re.match(r'^\s*(chapter|part|book)\s+', title, re.IGNORECASE):
        return title
    if line_no + 1 >= len(lines):
        return title
    next_line = lines[line_no + 1].strip()
    if not next_line or len(next_line) > _MAX_HEADING_LEN or _is_semantic_heading(next_line):
        return title
    if _numeric_heading_value(next_line) is not None:
        return title
    return f"{title} — {next_line}"


def _split_by_headings(text: str) -> List[Dict[str, Any]]:
    """按章节标题切分。返回带 start_char/end_char/title 的段落列表；若标题过少返回空。"""
    lines = text.split('\n')
    # 记录每行在原文中的起始偏移
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1  # +1 为换行符

    chapter_marker_indices = _chapter_marker_indices(lines)
    semantic_heading_indices = [i for i, line in enumerate(lines) if _is_semantic_heading(line)]
    numeric_candidates = [
        (i, _numeric_heading_value(line))
        for i, line in enumerate(lines)
        if _numeric_heading_value(line) is not None
    ]

    if len(chapter_marker_indices) >= 2:
        heading_indices = chapter_marker_indices
    elif len(semantic_heading_indices) >= 2:
        heading_indices = semantic_heading_indices
    else:
        numeric_indices = [i for i, _ in numeric_candidates]
        numeric_values = [v for _, v in numeric_candidates if v is not None]
        numeric_offsets = [offsets[i] for i in numeric_indices]
        if _looks_like_numbered_chapter_sequence(numeric_values, numeric_offsets, len(text)):
            heading_indices = numeric_indices
        else:
            heading_indices = semantic_heading_indices

    # 标题太少，不足以形成章节结构
    if len(heading_indices) < 2:
        return []

    episodes: List[Dict[str, Any]] = []

    # 第一个标题之前的内容作为"前言"章节（若有实质内容）
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
        title = _heading_title(lines, line_no)
        episodes.append({
            "title": title,
            "start_char": start,
            "end_char": end,
        })

    # 合并过短的章节到前一章，避免碎片
    episodes = _merge_tiny_episodes(text, episodes)
    return episodes


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
