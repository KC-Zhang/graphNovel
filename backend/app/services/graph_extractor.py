"""
图谱抽取服务
逐章（episode）调用 LLM 从书籍文本中抽取实体与关系，构建随阅读进度展开的知识图谱。

关键点：
- 语言锁定：输出的实体名、类型、关系、描述均使用与原文相同的语言（修复中文书出现英文节点的问题）。
- 实体消解：跨章节复用已知实体的规范名，避免重复节点（如"宝玉"/"贾宝玉"）。
- 溯源：每个实体/关系记录首次出现的章节 first_episode 与原文引用 quote，供阅读器跳转上下文。
"""

import logging
import re
from typing import Dict, Any, List, Optional, Callable

from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

# 单次送入 LLM 的最大字符数（过长的章节会被拆分）
_MAX_CHARS_PER_CALL = 6000


def detect_language(text: str) -> str:
    """
    检测文本主要语言，返回用于提示词的语言名称（英文描述）。

    仅做轻量脚本检测，用于给 LLM 明确的语言指令；无论是否命中，
    抽取时都会附加"与原文语言一致"的硬性规则。
    """
    sample = text[:4000]
    if not sample.strip():
        return "the source language"

    # 统计各类脚本字符
    han = len(re.findall(r'[\u4e00-\u9fff]', sample))
    hiragana_katakana = len(re.findall(r'[\u3040-\u30ff]', sample))
    hangul = len(re.findall(r'[\uac00-\ud7a3]', sample))
    cyrillic = len(re.findall(r'[\u0400-\u04ff]', sample))
    latin = len(re.findall(r'[A-Za-z]', sample))

    if hangul > 20:
        return "Korean"
    if hiragana_katakana > 20:
        return "Japanese"
    if han > 30:
        return "Chinese"
    if cyrillic > 30:
        return "Russian"
    if latin > 30:
        return "English"
    return "the source language"


_SYSTEM_PROMPT_TEMPLATE = """You are a knowledge-graph extraction engine for reading books. \
From the given excerpt of a book, extract the important entities (characters, places, \
organizations, items, concepts) and the relationships between them.

CRITICAL LANGUAGE RULE:
- The book is written in {language}.
- You MUST write EVERY name, entity type label, relationship label, fact, and description \
in the SAME language as the book ({language}).
- NEVER translate proper nouns, names, or terms into English or any other language.
- Entity "type" and relationship "label" must also be common words in {language} \
(e.g. for a Chinese book use 人物/地点/组织, not Person/Location/Organization).

EXTRACTION RULES:
- Only extract entities and relationships that actually appear in THIS excerpt.
- Reuse the canonical names from the "Known entities" list when the same entity reappears, \
so we do not create duplicates (e.g. use the full canonical name for a character referred to by a nickname).
- For every entity and every relationship, include a short "quote": a VERBATIM snippet \
copied exactly from the excerpt (max ~120 characters) that supports it.
- Keep descriptions concise (one sentence).

Return ONLY valid JSON with this exact shape:
{{
  "entities": [
    {{"name": "...", "type": "...", "aliases": ["..."], "description": "...", "quote": "..."}}
  ],
  "relations": [
    {{"source": "...", "target": "...", "label": "...", "fact": "...", "quote": "..."}}
  ]
}}"""


class GraphExtractor:
    """逐章抽取实体与关系，构建知识图谱"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
        # 规范名 -> node dict
        self._nodes: Dict[str, Dict[str, Any]] = {}
        # 别名/名称（小写规范化）-> 规范名
        self._alias_index: Dict[str, str] = {}
        # 边去重: (source_id, target_id, label) -> edge dict
        self._edges: Dict[str, Dict[str, Any]] = {}
        self._node_counter = 0
        self._edge_counter = 0

    # ---------- 名称规范化与实体消解 ----------

    @staticmethod
    def _normalize(name: str) -> str:
        return re.sub(r'\s+', '', (name or '').strip().lower())

    def _resolve_node_id(self, name: str) -> Optional[str]:
        key = self._normalize(name)
        if not key:
            return None
        return self._alias_index.get(key)

    def _get_or_create_node(
        self,
        name: str,
        episode_index: int,
        node_type: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        description: str = "",
        quote: str = "",
    ) -> Optional[str]:
        name = (name or "").strip()
        if not name:
            return None

        node_id = self._resolve_node_id(name)
        if node_id is None:
            # 尝试用别名命中
            for alias in (aliases or []):
                node_id = self._resolve_node_id(alias)
                if node_id:
                    break

        if node_id is not None:
            node = self._nodes[node_id]
            # 补充别名
            for alias in (aliases or []) + [name]:
                self._register_alias(alias, node_id)
                if alias != node["name"] and alias not in node["aliases"]:
                    node["aliases"].append(alias)
            if node_type and not node.get("type"):
                node["type"] = node_type
            if description and len(description) > len(node.get("description", "")):
                node["description"] = description
            self._add_mention(node, episode_index, quote)
            return node_id

        # 新建节点
        self._node_counter += 1
        node_id = f"n{self._node_counter}"
        node = {
            "id": node_id,
            "name": name,
            "type": node_type or "",
            "aliases": [a for a in (aliases or []) if a and a != name],
            "description": description or "",
            "first_episode": episode_index,
            "mentions": [],
        }
        self._nodes[node_id] = node
        self._register_alias(name, node_id)
        for alias in (aliases or []):
            self._register_alias(alias, node_id)
        self._add_mention(node, episode_index, quote)
        return node_id

    def _register_alias(self, alias: str, node_id: str) -> None:
        key = self._normalize(alias)
        if key and key not in self._alias_index:
            self._alias_index[key] = node_id

    @staticmethod
    def _add_mention(node: Dict[str, Any], episode_index: int, quote: str) -> None:
        quote = (quote or "").strip()
        if not quote:
            return
        # 避免重复引用
        for m in node["mentions"]:
            if m["episode"] == episode_index and m["quote"] == quote:
                return
        node["mentions"].append({"episode": episode_index, "quote": quote})

    def _add_edge(
        self,
        source_id: str,
        target_id: str,
        label: str,
        fact: str,
        episode_index: int,
        quote: str,
    ) -> None:
        label = (label or "").strip() or "关联"
        key = f"{source_id}->{target_id}:{self._normalize(label)}"
        edge = self._edges.get(key)
        if edge is None:
            self._edge_counter += 1
            edge = {
                "id": f"e{self._edge_counter}",
                "source": source_id,
                "target": target_id,
                "label": label,
                "fact": fact or "",
                "first_episode": episode_index,
                "mentions": [],
            }
            self._edges[key] = edge
        else:
            if fact and len(fact) > len(edge.get("fact", "")):
                edge["fact"] = fact
        quote = (quote or "").strip()
        if quote and not any(
            m["episode"] == episode_index and m["quote"] == quote for m in edge["mentions"]
        ):
            edge["mentions"].append({"episode": episode_index, "quote": quote})

    # ---------- LLM 调用 ----------

    @staticmethod
    def _chunk_text(text: str) -> List[str]:
        if len(text) <= _MAX_CHARS_PER_CALL:
            return [text]
        chunks = []
        start = 0
        n = len(text)
        while start < n:
            end = min(start + _MAX_CHARS_PER_CALL, n)
            if end < n:
                window = text[start:end]
                for sep in ['\n\n', '。', '！', '？', '. ', '\n']:
                    cand = window.rfind(sep)
                    if cand != -1 and cand > _MAX_CHARS_PER_CALL * 0.5:
                        end = start + cand + len(sep)
                        break
            chunks.append(text[start:end])
            start = end
        return chunks

    def _known_entities_hint(self, limit: int = 60) -> str:
        if not self._nodes:
            return "(none yet)"
        items = []
        for node in list(self._nodes.values())[:limit]:
            label = node["name"]
            if node.get("type"):
                label += f" [{node['type']}]"
            items.append(label)
        return "; ".join(items)

    def _extract_from_chunk(self, chunk: str, language: str, episode_index: int) -> None:
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(language=language)
        user_message = (
            f"Known entities (reuse these canonical names when they reappear):\n"
            f"{self._known_entities_hint()}\n\n"
            f"Book excerpt:\n\"\"\"\n{chunk}\n\"\"\""
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            result = self.llm_client.chat_json(messages=messages, temperature=0.2, max_tokens=4096)
        except Exception as e:
            logger.warning(f"章节 {episode_index} 抽取失败（已跳过该片段）: {e}")
            return

        entities = result.get("entities") or []
        relations = result.get("relations") or []

        for ent in entities:
            if not isinstance(ent, dict):
                continue
            self._get_or_create_node(
                name=ent.get("name", ""),
                episode_index=episode_index,
                node_type=ent.get("type"),
                aliases=ent.get("aliases") if isinstance(ent.get("aliases"), list) else [],
                description=ent.get("description", ""),
                quote=ent.get("quote", ""),
            )

        for rel in relations:
            if not isinstance(rel, dict):
                continue
            source_name = rel.get("source", "")
            target_name = rel.get("target", "")
            if not source_name or not target_name:
                continue
            source_id = self._get_or_create_node(source_name, episode_index)
            target_id = self._get_or_create_node(target_name, episode_index)
            if not source_id or not target_id:
                continue
            self._add_edge(
                source_id=source_id,
                target_id=target_id,
                label=rel.get("label", ""),
                fact=rel.get("fact", ""),
                episode_index=episode_index,
                quote=rel.get("quote", ""),
            )

    # ---------- 状态加载 / 导出 ----------

    @staticmethod
    def _max_id_suffix(items: List[Dict[str, Any]], prefix: str) -> int:
        """从形如 n12 / e7 的 id 中取最大数字后缀，用于续接计数器"""
        max_n = 0
        for it in items:
            raw = str(it.get("id", ""))
            if raw.startswith(prefix):
                suffix = raw[len(prefix):]
                if suffix.isdigit():
                    max_n = max(max_n, int(suffix))
        return max_n

    def load_graph(self, graph: Optional[Dict[str, Any]]) -> None:
        """
        从已保存的图谱数据恢复抽取状态，使后续章节可以在此基础上继续消解合并。
        """
        if not graph:
            return
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []

        for node in nodes:
            node.setdefault("aliases", [])
            node.setdefault("mentions", [])
            node.setdefault("description", "")
            node.setdefault("type", "")
            node_id = node["id"]
            self._nodes[node_id] = node
            self._register_alias(node.get("name", ""), node_id)
            for alias in node.get("aliases", []):
                self._register_alias(alias, node_id)

        for edge in edges:
            edge.setdefault("mentions", [])
            edge.setdefault("fact", "")
            key = f"{edge['source']}->{edge['target']}:{self._normalize(edge.get('label', ''))}"
            self._edges[key] = edge

        self._node_counter = self._max_id_suffix(nodes, "n")
        self._edge_counter = self._max_id_suffix(edges, "e")

    def to_graph(self) -> Dict[str, Any]:
        """导出当前图谱数据"""
        nodes = list(self._nodes.values())
        edges = list(self._edges.values())
        return {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    # ---------- 对外主流程 ----------

    def extract_episode(self, episode: Dict[str, Any], language: str) -> None:
        """抽取单个章节，合并进当前状态。"""
        text = episode.get("text", "")
        if not text.strip():
            return
        episode_index = episode.get("index", 0)
        for chunk in self._chunk_text(text):
            self._extract_from_chunk(chunk, language, episode_index)

    def build(
        self,
        episodes: List[Dict[str, Any]],
        language: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> Dict[str, Any]:
        """
        逐章构建整本书图谱（用于一次性全量抽取）。

        Args:
            episodes: 章节列表（含 index, title, text）
            language: 书籍语言名称（用于语言锁定）
            progress_callback: (message, ratio) 进度回调，ratio 为 0~1

        Returns:
            {nodes, edges, node_count, edge_count}
        """
        total = len(episodes)
        for i, episode in enumerate(episodes):
            title = episode.get("title") or f"#{i + 1}"
            if progress_callback:
                progress_callback(f"抽取章节 {i + 1}/{total}: {title}", i / max(total, 1))
            self.extract_episode(episode, language)

        if progress_callback:
            progress_callback("整理图谱数据", 1.0)

        return self.to_graph()
