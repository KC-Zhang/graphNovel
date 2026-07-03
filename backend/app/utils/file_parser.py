"""
文件解析工具
支持PDF、EPUB、Markdown、TXT文件的文本提取
"""

import html
import os
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import List
from urllib.parse import unquote
import xml.etree.ElementTree as ET


def _read_text_with_fallback(file_path: str) -> str:
    """
    读取文本文件，UTF-8失败时自动探测编码。
    
    采用多级回退策略：
    1. 首先尝试 UTF-8 解码
    2. 使用 charset_normalizer 检测编码
    3. 回退到 chardet 检测编码
    4. 最终使用 UTF-8 + errors='replace' 兜底
    
    Args:
        file_path: 文件路径
        
    Returns:
        解码后的文本内容
    """
    data = Path(file_path).read_bytes()
    
    # 首先尝试 UTF-8
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    
    # 尝试使用 charset_normalizer 检测编码
    encoding = None
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best and best.encoding:
            encoding = best.encoding
    except Exception:
        pass
    
    # 回退到 chardet
    if not encoding:
        try:
            import chardet
            result = chardet.detect(data)
            encoding = result.get('encoding') if result else None
        except Exception:
            pass
    
    # 最终兜底：使用 UTF-8 + replace
    if not encoding:
        encoding = 'utf-8'
    
    return data.decode(encoding, errors='replace')


def _local_name(tag: str) -> str:
    """Return an XML tag name without its namespace."""
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def _normalize_epub_path(path: str) -> str:
    """Normalize an internal EPUB ZIP path."""
    return posixpath.normpath(unquote(path).lstrip('/'))


def _resolve_epub_href(base_dir: str, href: str) -> str:
    """Resolve an OPF-relative href to an internal EPUB ZIP path."""
    clean_href = unquote(href.split('#', 1)[0])
    if not clean_href:
        return ''
    if clean_href.startswith('/'):
        return _normalize_epub_path(clean_href)
    return _normalize_epub_path(posixpath.join(base_dir, clean_href))


def _is_epub_text_item(path: str, media_type: str) -> bool:
    suffix = Path(path).suffix.lower()
    return media_type in {'application/xhtml+xml', 'text/html'} or suffix in {'.xhtml', '.html', '.htm'}


class _HTMLTextExtractor(HTMLParser):
    """Small dependency-free XHTML/HTML to plain-text extractor."""

    _BLOCK_TAGS = {
        'address', 'article', 'aside', 'blockquote', 'br', 'dd', 'div', 'dl', 'dt',
        'figcaption', 'figure', 'footer', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header',
        'hr', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section', 'table', 'tbody', 'td',
        'tfoot', 'th', 'thead', 'tr', 'ul',
    }
    _IGNORED_TAGS = {'head', 'script', 'style', 'svg'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._ignore_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._IGNORED_TAGS:
            self._ignore_depth += 1
        if self._ignore_depth == 0 and tag in self._BLOCK_TAGS:
            self._append_break()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._IGNORED_TAGS and self._ignore_depth:
            self._ignore_depth -= 1
        if self._ignore_depth == 0 and tag in self._BLOCK_TAGS:
            self._append_break()

    def handle_data(self, data):
        if self._ignore_depth:
            return
        text = html.unescape(data)
        if text.strip():
            self.parts.append(text)

    def _append_break(self):
        if self.parts and self.parts[-1] != '\n':
            self.parts.append('\n')

    def text(self) -> str:
        text = ''.join(self.parts)
        text = re.sub(r'[ \t\r\f\v]+', ' ', text)
        text = re.sub(r' *\n *', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def _html_to_text(source: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(source)
    parser.close()
    return parser.text()


class FileParser:
    """文件解析器"""
    
    SUPPORTED_EXTENSIONS = {'.pdf', '.epub', '.md', '.markdown', '.txt'}
    
    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        """
        检查文件是否为支持的格式
        
        Args:
            file_path: 文件路径
            
        Returns:
            如果文件格式受支持则返回 True
        """
        suffix = Path(file_path).suffix.lower()
        return suffix in cls.SUPPORTED_EXTENSIONS
    
    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """
        从文件中提取文本
        
        Args:
            file_path: 文件路径
            
        Returns:
            提取的文本内容
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        suffix = path.suffix.lower()
        
        if suffix not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {suffix}")
        
        if suffix == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif suffix == '.epub':
            return cls._extract_from_epub(file_path)
        elif suffix in {'.md', '.markdown'}:
            return cls._extract_from_md(file_path)
        elif suffix == '.txt':
            return cls._extract_from_txt(file_path)
        
        raise ValueError(f"无法处理的文件格式: {suffix}")
    
    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """从PDF提取文本"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("需要安装PyMuPDF: pip install PyMuPDF")
        
        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
        
        return "\n\n".join(text_parts)

    @staticmethod
    def _extract_from_epub(file_path: str) -> str:
        """从EPUB提取文本，按书籍 spine 顺序读取 XHTML/HTML 内容。"""
        try:
            with zipfile.ZipFile(file_path) as book:
                opf_path = FileParser._epub_rootfile_path(book)
                item_paths = FileParser._epub_spine_item_paths(book, opf_path)
                text_parts = []
                for item_path in item_paths:
                    try:
                        content = book.read(item_path)
                    except KeyError:
                        continue
                    text = _html_to_text(content.decode('utf-8', errors='replace'))
                    if text:
                        text_parts.append(text)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"无效的 EPUB 文件: {file_path}") from exc

        return "\n\n".join(text_parts)

    @staticmethod
    def _epub_rootfile_path(book: zipfile.ZipFile) -> str:
        """读取 EPUB container.xml 中声明的 OPF 路径。"""
        try:
            container = ET.fromstring(book.read('META-INF/container.xml'))
        except KeyError as exc:
            raise ValueError("EPUB 缺少 META-INF/container.xml") from exc
        except ET.ParseError as exc:
            raise ValueError("EPUB container.xml 无法解析") from exc

        for elem in container.iter():
            if _local_name(elem.tag) == 'rootfile':
                full_path = elem.attrib.get('full-path')
                if full_path:
                    return _normalize_epub_path(full_path)

        raise ValueError("EPUB container.xml 未声明 rootfile")

    @staticmethod
    def _epub_spine_item_paths(book: zipfile.ZipFile, opf_path: str) -> List[str]:
        """解析 OPF manifest/spine，返回阅读顺序中的 HTML 文档路径。"""
        try:
            package = ET.fromstring(book.read(opf_path))
        except KeyError as exc:
            raise ValueError(f"EPUB 缺少 OPF 文件: {opf_path}") from exc
        except ET.ParseError as exc:
            raise ValueError("EPUB OPF 文件无法解析") from exc

        opf_dir = posixpath.dirname(opf_path)
        manifest = {}
        for elem in package.iter():
            if _local_name(elem.tag) != 'item':
                continue
            item_id = elem.attrib.get('id')
            href = elem.attrib.get('href')
            media_type = elem.attrib.get('media-type', '')
            if item_id and href:
                manifest[item_id] = {
                    'path': _resolve_epub_href(opf_dir, href),
                    'media_type': media_type,
                }

        paths = []
        for elem in package.iter():
            if _local_name(elem.tag) != 'itemref':
                continue
            item = manifest.get(elem.attrib.get('idref'))
            if item and _is_epub_text_item(item['path'], item['media_type']):
                paths.append(item['path'])

        if paths:
            return paths

        return [
            item['path']
            for item in manifest.values()
            if _is_epub_text_item(item['path'], item['media_type'])
        ]
    
    @staticmethod
    def _extract_from_md(file_path: str) -> str:
        """从Markdown提取文本，支持自动编码检测"""
        return _read_text_with_fallback(file_path)
    
    @staticmethod
    def _extract_from_txt(file_path: str) -> str:
        """从TXT提取文本，支持自动编码检测"""
        return _read_text_with_fallback(file_path)
    
    @classmethod
    def extract_from_multiple(cls, file_paths: List[str]) -> str:
        """
        从多个文件提取文本并合并
        
        Args:
            file_paths: 文件路径列表
            
        Returns:
            合并后的文本
        """
        all_texts = []
        
        for i, file_path in enumerate(file_paths, 1):
            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                all_texts.append(f"=== 文档 {i}: {filename} ===\n{text}")
            except Exception as e:
                all_texts.append(f"=== 文档 {i}: {file_path} (提取失败: {str(e)}) ===")
        
        return "\n\n".join(all_texts)


def split_text_into_chunks(
    text: str, 
    chunk_size: int = 500, 
    overlap: int = 50
) -> List[str]:
    """
    将文本分割成小块
    
    Args:
        text: 原始文本
        chunk_size: 每块的字符数
        overlap: 重叠字符数
        
    Returns:
        文本块列表
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # 尝试在句子边界处分割
        if end < len(text):
            # 查找最近的句子结束符
            for sep in ['。', '！', '？', '.\n', '!\n', '?\n', '\n\n', '. ', '! ', '? ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1 and last_sep > chunk_size * 0.3:
                    end = start + last_sep + len(sep)
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # 下一个块从重叠位置开始
        start = end - overlap if end < len(text) else len(text)
    
    return chunks
