import zipfile

import fitz

from app.config import Config
from app.utils.file_parser import FileParser


def _write_minimal_epub(path):
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("mimetype", "application/epub+zip")
        book.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        book.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <manifest>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="text/chapter2.xhtml" media-type="application/xhtml+xml"/>
    <item id="ignored" href="ignored.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="c1"/>
    <itemref idref="c2"/>
  </spine>
</package>
""",
        )
        book.writestr(
            "OEBPS/chapter1.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Hidden title</title><style>.x { color: red; }</style></head>
<body><h1>Chapter One</h1><p>Alice &amp; Bob meet.</p><script>ignoreMe()</script></body>
</html>
""",
        )
        book.writestr(
            "OEBPS/text/chapter2.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml">
<body><h1>Chapter Two</h1><p>Clara brings the map.</p></body>
</html>
""",
        )
        book.writestr(
            "OEBPS/ignored.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml"><body>Appendix should not appear.</body></html>""",
        )


def _write_epub_with_ncx(path):
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("mimetype", "application/epub+zip")
        book.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        book.writestr(
            "content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <manifest>
    <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="html_toc" href="OEBPS/toc.xhtml" media-type="application/xhtml+xml"/>
    <item id="c1" href="OEBPS/chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="OEBPS/chapter2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="toc">
    <itemref idref="html_toc"/>
    <itemref idref="c1"/>
    <itemref idref="c2"/>
  </spine>
</package>
""",
        )
        book.writestr(
            "toc.ncx",
            """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">
  <navMap>
    <navPoint id="toc" playOrder="1">
      <navLabel><text>Contents</text></navLabel>
      <content src="OEBPS/toc.xhtml"/>
    </navPoint>
    <navPoint id="c1" playOrder="2">
      <navLabel><text>Chapter One - The First Door</text></navLabel>
      <content src="OEBPS/chapter1.xhtml"/>
      <navPoint id="c1s1" playOrder="3">
        <navLabel><text>Nested Section</text></navLabel>
        <content src="OEBPS/chapter1.xhtml#section1"/>
      </navPoint>
    </navPoint>
    <navPoint id="c2" playOrder="4">
      <navLabel><text>Chapter Two - The Second Door</text></navLabel>
      <content src="OEBPS/chapter2.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
""",
        )
        book.writestr(
            "OEBPS/toc.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Contents</h1><p>Chapter One</p></body></html>""",
        )
        book.writestr(
            "OEBPS/chapter1.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>One</h1><p>""" + ("First chapter body. " * 12) + """</p></body></html>""",
        )
        book.writestr(
            "OEBPS/chapter2.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Two</h1><p>""" + ("Second chapter body. " * 12) + """</p></body></html>""",
        )


def test_epub_extension_is_supported():
    assert FileParser.is_supported("book.epub")
    assert "epub" in Config.ALLOWED_EXTENSIONS


def test_extract_from_epub_uses_spine_order_and_strips_markup(tmp_path):
    epub_path = tmp_path / "sample.epub"
    _write_minimal_epub(epub_path)

    text = FileParser.extract_text(str(epub_path))

    assert "Chapter One" in text
    assert "Alice & Bob meet." in text
    assert "Chapter Two" in text
    assert "Clara brings the map." in text
    assert text.index("Chapter One") < text.index("Chapter Two")
    assert "ignoreMe" not in text
    assert "Hidden title" not in text
    assert "Appendix should not appear" not in text


def test_extract_epub_episodes_uses_ncx_chapter_targets(tmp_path):
    epub_path = tmp_path / "sample_ncx.epub"
    _write_epub_with_ncx(epub_path)

    episodes = FileParser.extract_epub_episodes(str(epub_path))

    assert [ep["title"] for ep in episodes] == [
        "Chapter One - The First Door",
        "Chapter Two - The Second Door",
    ]
    assert [ep["source_path"] for ep in episodes] == [
        "OEBPS/chapter1.xhtml",
        "OEBPS/chapter2.xhtml",
    ]
    assert all("Nested Section" != ep["title"] for ep in episodes)
    assert all("Contents" != ep["title"] for ep in episodes)


def _write_pdf_with_text_image_and_outline(path):
    document = fitz.open()
    first = document.new_page()
    first.insert_text((72, 72), "Chapter 1", fontsize=20)
    first.insert_text((72, 110), "The first physical page has searchable text.", fontsize=11)

    image_page = document.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), False)
    pixmap.clear_with(0x336699)
    image_page.insert_image(fitz.Rect(72, 72, 144, 144), pixmap=pixmap)

    third = document.new_page()
    third.insert_text((72, 72), "Chapter 2", fontsize=20)
    third.insert_text((72, 110), "The final page completes the sample.", fontsize=11)
    document.set_toc([[1, "Chapter 1", 1], [1, "Chapter 2", 3]])
    document.save(path)
    document.close()


def test_extract_pdf_document_preserves_every_physical_page_and_layout_metadata(tmp_path):
    pdf_path = tmp_path / "page_aware.pdf"
    _write_pdf_with_text_image_and_outline(pdf_path)

    document = FileParser.extract_pdf_document(str(pdf_path))

    assert document["page_count"] == 3
    assert len(document["pages"]) == 3
    assert "Chapter 1" in document["pages"][0]["text"]
    assert document["pages"][1]["text"].strip() == ""
    assert document["pages"][1]["image_count"] == 1
    assert document["pages"][0]["width"] > 0
    assert document["pages"][0]["headings"][0]["font_size"] >= 20
    assert document["outline"] == [
        {"level": 1, "title": "Chapter 1", "page_number": 1},
        {"level": 1, "title": "Chapter 2", "page_number": 3},
    ]
