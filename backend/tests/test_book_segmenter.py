from app.services.book_segmenter import segment_book


def test_pdf_page_numbers_are_not_treated_as_chapters():
    text = """
Never Eat Alone

23

Copyright page and table of contents material.

56

Another short front-matter page.

128

Yet another page-number-looking heading.

1

This is the first real body section. It has enough prose to look like a
page from a PDF export, but the bare number above is still a page number,
not a chapter title.

4

This continues the same real section and should not become its own chapter
just because the PDF text extraction put a page number on a separate line.
""".strip()

    episodes = segment_book(text)

    assert len(episodes) < 4
    assert all(ep["title"] not in {"23", "56", "128", "4"} for ep in episodes)


def test_plausible_numbered_chapters_are_still_supported():
    text = """
1

Alice arrived at the station and met Bob. They discussed the map and the
old promise. This section has enough content to be a legitimate chapter.

2

Bob returned with Clara. The second chapter continues the story with a new
relationship and another scene.

3

Clara left a note for Alice. The third chapter completes the small sample.
""".strip()

    episodes = segment_book(text)

    assert [ep["title"] for ep in episodes] == ["1", "2", "3"]
    assert [ep["index"] for ep in episodes] == [0, 1, 2]


def test_fallback_sections_use_meaningful_text_titles():
    text = """
Never Eat Alone

12

Never Eat Alone

The Mind-Set

Becoming a member of the club starts with generosity and a clear mission.
This paragraph is long enough to force a fallback section in the test by
repeating useful prose. """ + ("Relationships grow through repeated generosity. " * 80) + """

24

Never Eat Alone

The Skill Set

Doing your homework before a meeting changes the quality of every
conversation. """ + ("Preparation makes a warmer call possible. " * 80)

    episodes = segment_book(text)

    assert len(episodes) >= 2
    assert not episodes[0]["title"].startswith("Section ")
    assert not episodes[1]["title"].startswith("Section ")
    assert "The Mind-Set" in episodes[0]["title"]
    assert "The Skill Set" in episodes[1]["title"]


def test_letter_spaced_pdf_chapter_markers_use_real_titles():
    text = """
Never Eat Alone

SECTION ONE
The Mind-Set

C H A P T E R
1
Becoming a Member of the Club

Relationships are all there is. Everything in the universe only exists
because it is in relationship to everything else.

C H A P T E R
2
Don't Keep Score

There is no such thing as a self-made person. We are made up of thousands
of others.
""".strip()

    episodes = segment_book(text)

    assert [ep["title"] for ep in episodes] == [
        "Chapter 1 — Becoming a Member of the Club",
        "Chapter 2 — Don't Keep Score",
    ]


def test_spaced_digit_pdf_chapter_numbers_continue_after_nine():
    text = """
C H A P T E R
9
Warming the Cold Call

Cold calls turn even the most competent of souls into nervous messes.
This chapter has enough text to stand alone.

C H A P T E R
1 0
Managing the Gatekeeper
Artfully

Having a list of names does not mean much if you cannot reach them.
This chapter should be detected even when the PDF inserts spaces inside
the chapter number.

CHAPTER
1 1
Never Eat Alone

The dynamics of a network are similar to visibility in Hollywood.
""".strip()

    episodes = segment_book(text)

    assert [ep["title"] for ep in episodes] == [
        "Chapter 9 — Warming the Cold Call",
        "Chapter 10 — Managing the Gatekeeper Artfully",
        "Chapter 11 — Never Eat Alone",
    ]


def test_dense_front_matter_heading_run_is_not_used_for_chapters():
    toc = "\n".join([
        "Chapter 1. Dawn",
        "Chapter 2. Road",
        "Chapter 3. Gate",
        "Chapter 4. Tower",
        "Chapter 5. River",
        "Chapter 6. Return",
    ])
    body = "\n\n".join(
        f"Chapter {i}. {title}\n"
        + ("This is the real body text for the chapter with enough prose to "
           "separate it from front matter. " * 35)
        for i, title in [
            (1, "Dawn"),
            (2, "Road"),
            (3, "Gate"),
            (4, "Tower"),
            (5, "River"),
            (6, "Return"),
        ]
    )
    text = f"""
Sample Book

Contents
{toc}

Introductory notes and publication material before the actual story.
This front matter is long enough to become preamble rather than a chapter.

{body}
""".strip()

    episodes = segment_book(text)
    chapter_titles = [ep["title"] for ep in episodes if ep["title"].startswith("Chapter ")]

    assert chapter_titles == [
        "Chapter 1. Dawn",
        "Chapter 2. Road",
        "Chapter 3. Gate",
        "Chapter 4. Tower",
        "Chapter 5. River",
        "Chapter 6. Return",
    ]
    assert all("real body text" in ep["text"] for ep in episodes if ep["title"].startswith("Chapter "))


def test_single_short_chapter_run_is_preserved():
    text = """
Chapter 1. One
Brief real chapter text with a little action.

Chapter 2. Two
Another compact chapter with enough narrative to read.

Chapter 3. Three
The final compact chapter resolves the scene.
""".strip()

    episodes = segment_book(text)

    assert [ep["title"] for ep in episodes] == [
        "Chapter 1. One",
        "Chapter 2. Two",
        "Chapter 3. Three",
    ]


def test_dense_chinese_front_matter_heading_run_is_not_used_for_chapters():
    toc = "\n".join([
        "第一章 清晨",
        "第二章 远行",
        "第三章 相逢",
    ])
    body = "\n\n".join(
        title + "\n" + ("这是章节正文，人物在场景中行动并产生新的关系。" * 80)
        for title in ["第一章 清晨", "第二章 远行", "第三章 相逢"]
    )
    text = f"""
样书

目录
{toc}

序言
这里是出版说明和前言文字，用来说明故事背景。

{body}
""".strip()

    episodes = segment_book(text)
    chapter_titles = [ep["title"] for ep in episodes if ep["title"].startswith("第")]

    assert chapter_titles == ["第一章 清晨", "第二章 远行", "第三章 相逢"]
    assert all("章节正文" in ep["text"] for ep in episodes if ep["title"].startswith("第"))
