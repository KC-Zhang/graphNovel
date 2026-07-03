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
