"""
书籍分章服务
将整本书的文本切分为有序的"章节"（episode），用于按阅读进度逐步展开图谱。
"""

import re
from typing import List, Dict, Any


# 章节标题识别的正则（按行匹配，行需较短）
_CHAPTER_PATTERNS = [
    # 中文：第X章 / 第X回 / 第X节 / 第X卷 / 第X部 / 第X篇
    re.compile(r'^\s*第\s*[0-9一二三四五六七八九十百千零两〇]+\s*[章回节卷篇部集]'),
    # 中文特殊章节
    re.compile(r'^\s*(序章|序言|序|楔子|引子|前言|后记|後記|尾声|尾聲|番外|终章|終章)\b'),
    # 英文：Chapter 1 / CHAPTER I / Prologue / Epilogue
    re.compile(r'^\s*(chapter|prologue|epilogue|part|book)\s+[0-9ivxlcdm]+', re.IGNORECASE),
    re.compile(r'^\s*(prologue|epilogue|preface|foreword|introduction)\s*$', re.IGNORECASE),
    # 纯数字章节标题（如 "1." "01"）
    re.compile(r'^\s*[0-9]{1,3}\s*[.、]?\s*$'),
]

# 章节标题行的最大长度（避免把正文误判为标题）
_MAX_HEADING_LEN = 40

# 无标题时的兜底分段大小（字符数）
_FALLBACK_SEGMENT_SIZE = 4000
_FALLBACK_MIN_SIZE = 1500


def _is_heading(line: str) -> bool:
    """判断一行是否为章节标题"""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_LEN:
        return False
    for pattern in _CHAPTER_PATTERNS:
        if pattern.match(stripped):
            return True
    return False


def _split_by_headings(text: str) -> List[Dict[str, Any]]:
    """按章节标题切分。返回带 start_char/end_char/title 的段落列表；若标题过少返回空。"""
    lines = text.split('\n')
    # 记录每行在原文中的起始偏移
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1  # +1 为换行符

    heading_indices = [i for i, line in enumerate(lines) if _is_heading(line)]

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
        title = lines[line_no].strip()
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
    for i, ep in enumerate(episodes):
        segment_text = text[ep["start_char"]:ep["end_char"]].strip()
        title = ep.get("title")
        if not title:
            # 兜底分段的默认标题
            if is_cjk:
                title = f"第 {i + 1} 节"
            else:
                title = f"Section {i + 1}"
        result.append({
            "index": i,
            "title": title,
            "start_char": ep["start_char"],
            "end_char": ep["end_char"],
            "char_count": len(segment_text),
            "text": segment_text,
        })

    return result
