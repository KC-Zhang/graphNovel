import zipfile

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
