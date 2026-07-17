"""Page-aware PDF episode construction and conservative chapter detection."""

import re
from bisect import bisect_right
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from .book_segmenter import segment_book_hybrid


_PACKAGING_TITLES = {
    "acknowledgements",
    "acknowledgments",
    "bibliography",
    "contents",
    "copyright",
    "cover",
    "table of contents",
    "title page",
}
_CHAPTER_RE = re.compile(
    r"^\s*(?:chapter|part|book)\s+([0-9]{1,3}|[ivxlcdm]+)\b",
    re.IGNORECASE,
)
_CHINESE_CHAPTER_RE = re.compile(
    r"^\s*第\s*([0-9一二三四五六七八九十百千零两〇]+)\s*[章回卷篇部]"
)
_TOP_LEVEL_SECTION_RE = re.compile(r"^\s*([1-9][0-9]{0,2})[.)]?\s+\S")
_STANDALONE_NUMBER_RE = re.compile(r"^\s*([1-9][0-9]{0,2})\s*$")
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman_to_int(value: str) -> Optional[int]:
    value = value.casefold()
    if not value or any(ch not in _ROMAN_VALUES for ch in value):
        return None
    total = 0
    previous = 0
    for ch in reversed(value):
        current = _ROMAN_VALUES[ch]
        total += -current if current < previous else current
        previous = max(previous, current)
    return total or None


def _chapter_number(title: str) -> Optional[int]:
    match = _CHAPTER_RE.match(title or "")
    if match:
        token = match.group(1)
        return int(token) if token.isdigit() else _roman_to_int(token)
    match = _TOP_LEVEL_SECTION_RE.match(title or "")
    if match:
        return int(match.group(1))
    match = _STANDALONE_NUMBER_RE.match(title or "")
    if match:
        return int(match.group(1))
    return None


def build_pdf_text(document: Dict[str, Any]) -> Tuple[str, List[Tuple[int, int]]]:
    """Build a stable full-text representation and one offset pair per physical page."""
    pages = document.get("pages") or []
    parts: List[str] = []
    bounds: List[Tuple[int, int]] = []
    cursor = 0
    for index, page in enumerate(pages):
        text = str(page.get("text", "") or "")
        start = cursor
        parts.append(text)
        cursor += len(text)
        bounds.append((start, cursor))
        if index < len(pages) - 1:
            parts.append("\n\n")
            cursor += 2
    return "".join(parts), bounds


def build_pdf_page_episodes(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create exactly one episode for every physical PDF page, including empty pages."""
    _, bounds = build_pdf_text(document)
    episodes: List[Dict[str, Any]] = []
    for index, page in enumerate(document.get("pages") or []):
        text = str(page.get("text", "") or "")
        start, end = bounds[index]
        episodes.append({
            "index": index,
            "title": f"Page {index + 1}",
            "start_char": start,
            "end_char": end,
            "char_count": len(text),
            "text": text,
            "unit_type": "page",
            "page_number": index + 1,
            "page_label": str(page.get("page_label") or index + 1),
            "pdf_page_index": index,
            "image_count": int(page.get("image_count", 0) or 0),
        })
    return episodes


def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", str(title or "")).strip()


def _is_packaging_title(title: str) -> bool:
    key = _clean_title(title).casefold().rstrip(".:")
    return key in _PACKAGING_TITLES


def _longest_contiguous_number_run(
    candidates: List[Tuple[int, str]],
) -> List[Tuple[int, str]]:
    """
    Keep the strongest contiguous numbered run when explicit numbers exist.

    This prevents isolated body citations such as ``Chapter 0`` or ``Chapter
    88`` from becoming document-level chapters.
    """
    numbered = [(item, _chapter_number(item[1])) for item in candidates]
    explicit = [(item, number) for item, number in numbered if number is not None]
    if not explicit:
        return candidates

    explicit = [(item, number) for item, number in explicit if number and number > 0]
    if len(explicit) < 2:
        return []

    # Dynamic programming permits unrelated outliers between real headings:
    # 1, (cited 88), 2 still yields the valid 1 -> 2 run.
    best_by_number: Dict[int, List[Tuple[int, str]]] = {}
    best: List[Tuple[int, str]] = []
    for item, number in explicit:
        run = [*best_by_number.get(number - 1, []), item]
        if len(run) > len(best_by_number.get(number, [])):
            best_by_number[number] = run
        if len(run) > len(best):
            best = run
    return best if len(best) >= 2 else []


def _outline_candidates(document: Dict[str, Any]) -> List[Tuple[int, str]]:
    outline = document.get("outline") or []
    levels = sorted({int(item.get("level", 1) or 1) for item in outline})
    page_count = int(document.get("page_count", 0) or len(document.get("pages") or []))
    for level in levels:
        candidates: List[Tuple[int, str]] = []
        seen_pages = set()
        for item in outline:
            if int(item.get("level", 1) or 1) != level:
                continue
            page_index = int(item.get("page_number", 0) or 0) - 1
            title = _clean_title(item.get("title", ""))
            if not title or _is_packaging_title(title) or page_index in seen_pages:
                continue
            if page_index < 0 or page_index >= page_count:
                continue
            if _CHAPTER_RE.match(title) and _chapter_number(title) in {0, None}:
                continue
            seen_pages.add(page_index)
            candidates.append((page_index, title))

        if len(candidates) < 2:
            continue
        # Only apply sequence filtering when outline items explicitly use chapter numbering.
        if sum(bool(_CHAPTER_RE.match(title)) for _, title in candidates) >= 2:
            candidates = _longest_contiguous_number_run(candidates)
        if len(candidates) >= 2:
            return candidates
    return []


def _layout_candidates(document: Dict[str, Any]) -> List[Tuple[int, str]]:
    body_size = float(document.get("body_font_size", 0.0) or 0.0)
    candidates: List[Tuple[int, str]] = []
    for page_index, page in enumerate(document.get("pages") or []):
        headings = page.get("headings") or []
        page_candidates: List[str] = []
        for heading_index, heading in enumerate(headings):
            title = _clean_title(heading.get("text", ""))
            if not title or _is_packaging_title(title):
                continue
            y_ratio = float(heading.get("y_ratio", 1.0) or 1.0)
            font_size = float(heading.get("font_size", 0.0) or 0.0)
            emphasized = bool(heading.get("bold")) or (body_size > 0 and font_size >= body_size * 1.18)
            semantic = bool(_CHAPTER_RE.match(title) or _CHINESE_CHAPTER_RE.match(title))
            top_level_section = bool(_TOP_LEVEL_SECTION_RE.match(title)) and emphasized

            # Handle PDFs that put CHAPTER and its number on adjacent lines.
            if title.casefold() in {"chapter", "part", "book"} and heading_index + 1 < len(headings):
                next_title = _clean_title(headings[heading_index + 1].get("text", ""))
                if _STANDALONE_NUMBER_RE.match(next_title):
                    title = f"{title.title()} {next_title}"
                    semantic = True

            if y_ratio <= 0.38 and (semantic or top_level_section):
                number = _chapter_number(title)
                if number == 0:
                    continue
                page_candidates.append(title)

        if page_candidates:
            candidates.append((page_index, page_candidates[0]))

    if len(candidates) < 2:
        return []
    # Numbered layout headings must form a plausible sequence. Unnumbered
    # prologue/epilogue markers are intentionally handled by text fallback.
    return _longest_contiguous_number_run(candidates)


def _page_for_offset(bounds: List[Tuple[int, int]], offset: int) -> int:
    starts = [start for start, _ in bounds]
    return max(0, min(len(bounds) - 1, bisect_right(starts, offset) - 1))


def _text_fallback(document: Dict[str, Any], llm_client=None) -> List[Dict[str, Any]]:
    full_text, bounds = build_pdf_text(document)
    episodes = segment_book_hybrid(full_text, llm_client=llm_client)
    if len(episodes) < 2:
        return []

    titles = [str(ep.get("title", "")) for ep in episodes]
    # Fixed-size fallback sections are not chapters and must not be presented as such.
    if any(re.match(r"^(?:Section \d+|第 \d+ 节)$", title) for title in titles):
        return []

    structural_titles = [
        title for title in titles
        if (
            _CHAPTER_RE.match(title)
            or _CHINESE_CHAPTER_RE.match(title)
            or _TOP_LEVEL_SECTION_RE.match(title)
            or _STANDALONE_NUMBER_RE.match(title)
        )
    ]
    # Meaningful titles generated by the fixed-size fallback are still not
    # chapter evidence. Require at least two actual structural markers.
    if len(structural_titles) < 2:
        return []

    numbered_titles = [title for title in structural_titles if _chapter_number(title) is not None]
    if numbered_titles:
        chapter_numbers = [_chapter_number(title) for title in numbered_titles]
        if any(number is None or number <= 0 for number in chapter_numbers):
            return []
        if any(right != left + 1 for left, right in zip(chapter_numbers, chapter_numbers[1:])):
            return []

    lengths = [max(1, int(ep.get("char_count", 0) or 0)) for ep in episodes]
    typical = median(lengths)
    if max(lengths) > max(60000, typical * 12):
        return []

    result: List[Dict[str, Any]] = []
    for index, episode in enumerate(episodes):
        start = int(episode.get("start_char", 0) or 0)
        end = int(episode.get("end_char", start) or start)
        start_page = _page_for_offset(bounds, start) if bounds else 0
        end_page = _page_for_offset(bounds, max(start, end - 1)) if bounds else start_page
        result.append({
            **episode,
            "index": index,
            "unit_type": "chapter",
            "page_number": start_page + 1,
            "page_end": end_page + 1,
        })
    return result


def _episodes_from_page_candidates(
    document: Dict[str, Any],
    candidates: List[Tuple[int, str]],
) -> List[Dict[str, Any]]:
    full_text, bounds = build_pdf_text(document)
    pages = document.get("pages") or []
    candidates = sorted(candidates, key=lambda item: item[0])
    episodes: List[Dict[str, Any]] = []

    if candidates and candidates[0][0] > 0:
        preamble_end_page = candidates[0][0] - 1
        start = bounds[0][0]
        end = bounds[preamble_end_page][1]
        text = full_text[start:end].strip()
        if text:
            episodes.append({
                "title": "Front Matter",
                "start_char": start,
                "end_char": end,
                "char_count": len(text),
                "text": text,
                "unit_type": "chapter",
                "page_number": 1,
                "page_end": preamble_end_page + 1,
            })

    for candidate_index, (start_page, title) in enumerate(candidates):
        end_page = (
            candidates[candidate_index + 1][0] - 1
            if candidate_index + 1 < len(candidates)
            else len(pages) - 1
        )
        start = bounds[start_page][0]
        end = bounds[end_page][1]
        text = full_text[start:end].strip()
        episodes.append({
            "title": title,
            "start_char": start,
            "end_char": end,
            "char_count": len(text),
            "text": text,
            "unit_type": "chapter",
            "page_number": start_page + 1,
            "page_end": end_page + 1,
        })

    for index, episode in enumerate(episodes):
        episode["index"] = index
    return episodes


def segment_pdf_chapters(
    document: Dict[str, Any],
    llm_client=None,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Return conservative PDF chapter episodes and their evidence source.

    Status is one of ``outline``, ``layout``, ``text``, or ``unreliable``.
    """
    if len(document.get("pages") or []) < 1:
        return [], "unreliable"

    candidates = _outline_candidates(document)
    if candidates:
        return _episodes_from_page_candidates(document, candidates), "outline"

    candidates = _layout_candidates(document)
    if candidates:
        return _episodes_from_page_candidates(document, candidates), "layout"

    episodes = _text_fallback(document, llm_client=llm_client)
    if episodes:
        return episodes, "text"
    return [], "unreliable"
