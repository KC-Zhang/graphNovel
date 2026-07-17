import os
from pathlib import Path

import pytest

from app.services.pdf_segmenter import build_pdf_page_episodes, segment_pdf_chapters
from app.utils.file_parser import FileParser


def _page(number, text, heading=None, image_count=0):
    headings = []
    if heading:
        headings.append({
            "text": heading,
            "y_ratio": 0.08,
            "font_size": 20.0,
            "bold": True,
        })
    return {
        "page_number": number,
        "page_label": str(number),
        "text": text,
        "width": 612,
        "height": 792,
        "rotation": 0,
        "image_count": image_count,
        "headings": headings,
    }


def test_page_mode_creates_one_episode_per_physical_page_including_empty_page():
    document = {
        "page_count": 3,
        "pages": [
            _page(1, "First page"),
            _page(2, "", image_count=2),
            _page(3, "Third page"),
        ],
    }

    episodes = build_pdf_page_episodes(document)

    assert [episode["page_number"] for episode in episodes] == [1, 2, 3]
    assert [episode["unit_type"] for episode in episodes] == ["page"] * 3
    assert episodes[1]["text"] == ""
    assert episodes[1]["char_count"] == 0
    assert episodes[1]["image_count"] == 2


@pytest.mark.parametrize("evidence", ["outline", "layout"])
def test_false_cited_chapter_zero_and_eighty_eight_are_not_chapters(evidence):
    pages = [
        _page(1, "Chapter 1\nReal chapter body " * 20, "Chapter 1"),
        _page(2, "A discussion cites Chapter 0 of another book.", "Chapter 0"),
        _page(3, "A discussion cites Chapter 88 of another book.", "Chapter 88"),
        _page(4, "Chapter 2\nSecond real chapter body " * 20, "Chapter 2"),
    ]
    document = {"page_count": 4, "body_font_size": 11.0, "pages": pages, "outline": []}
    if evidence == "outline":
        document["outline"] = [
            {"level": 1, "title": "Chapter 1", "page_number": 1},
            {"level": 1, "title": "Chapter 0", "page_number": 2},
            {"level": 1, "title": "Chapter 88", "page_number": 3},
            {"level": 1, "title": "Chapter 2", "page_number": 4},
        ]
    else:
        document["outline"] = []

    episodes, status = segment_pdf_chapters(document)

    assert status == evidence
    assert [episode["title"] for episode in episodes] == ["Chapter 1", "Chapter 2"]
    assert episodes[0]["page_number"] == 1
    assert episodes[0]["page_end"] == 3
    assert episodes[1]["page_number"] == 4


def test_layoutless_prose_does_not_become_fixed_size_pseudo_chapters():
    class UnavailableLLM:
        def chat_json(self, messages, **kwargs):
            raise RuntimeError("classification unavailable")

    prose = "Continuous body prose without a structural heading. " * 250
    document = {
        "page_count": 3,
        "body_font_size": 11.0,
        "outline": [],
        "pages": [_page(1, prose), _page(2, prose), _page(3, prose)],
    }

    episodes, status = segment_pdf_chapters(document, llm_client=UnavailableLLM())

    assert episodes == []
    assert status == "unreliable"


def test_optional_academic_pdf_fixture_keeps_page_count_and_detects_outline():
    fixture = os.environ.get("BOOKMIRO_ACADEMIC_PDF")
    if not fixture or not Path(fixture).is_file():
        pytest.skip("set BOOKMIRO_ACADEMIC_PDF to run the real academic-PDF regression")

    document = FileParser.extract_pdf_document(fixture)
    page_episodes = build_pdf_page_episodes(document)
    chapter_episodes, status = segment_pdf_chapters(document)

    assert len(page_episodes) == document["page_count"]
    assert document["page_count"] > 1
    assert "Abstract" in page_episodes[0]["text"]
    assert status in {"outline", "layout"}
    assert len(chapter_episodes) >= 2
