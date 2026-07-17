import app.services.graph_extractor as graph_extractor_module
from app.services.graph_extractor import GraphExtractor, _MAX_CHARS_PER_CALL


class RecordingLLM:
    def __init__(self):
        self.excerpts = []

    def chat_json(self, messages, **kwargs):
        content = messages[-1]["content"]
        excerpt = content.split('Book excerpt:\n"""', 1)[1].rsplit('"""', 1)[0].strip()
        self.excerpts.append(excerpt)
        return {
            "entities": [
                {
                    "name": f"Entity {len(self.excerpts)}",
                    "type": "Person",
                    "aliases": [],
                    "description": "Seen in this extraction chunk.",
                    "quote": excerpt[:80],
                }
            ],
            "relations": [],
        }


class FailingLLM:
    def chat_json(self, messages, **kwargs):
        raise RuntimeError("Access to model denied. Please make sure you are eligible for using the model.")


class UnexpectedFallbackLLM:
    def __init__(self):
        self.calls = 0

    def chat_json(self, messages, **kwargs):
        self.calls += 1
        raise AssertionError("fallback should only be called after primary failure")


class EntityTypeLLM:
    def __init__(self, entity_types):
        self.entity_types = iter(entity_types)
        self.calls = 0

    def chat_json(self, messages, **kwargs):
        self.calls += 1
        return {
            "entities": [{
                "name": f"Entity {self.calls}",
                "type": next(self.entity_types),
                "aliases": [],
                "description": "",
                "quote": "entity",
            }],
            "relations": [],
        }


def test_long_episode_is_extracted_in_small_section_sized_chunks():
    llm = RecordingLLM()
    extractor = GraphExtractor(llm_client=llm)
    paragraph = (
        "Alice met Bob at the station. Clara watched from the balcony while "
        "Daniel carried the old map across town.\n\n"
    )
    text = paragraph * 180

    extractor.extract_episode({"index": 4, "text": text}, "English")
    graph = extractor.to_graph()

    assert len(llm.excerpts) >= 3
    assert all(len(excerpt) <= _MAX_CHARS_PER_CALL for excerpt in llm.excerpts)
    assert {m["episode"] for node in graph["nodes"] for m in node["mentions"]} == {4}


def test_fully_failed_episode_reports_error_and_logs_it(caplog):
    extractor = GraphExtractor(llm_client=FailingLLM())

    with caplog.at_level("ERROR", logger="app.services.graph_extractor"):
        result = extractor.extract_episode({"index": 7, "text": "Some chapter text."}, "English")

    graph = extractor.to_graph()
    assert result["total_chunks"] == 1
    assert result["failed_chunks"] == 1
    assert "Access to model denied" in result["error"]
    assert graph["node_count"] == 0
    assert any(
        record.levelname == "ERROR" and "章节 7 抽取完全失败" in record.message
        for record in caplog.records
    )


def test_failed_primary_llm_uses_fallback_client():
    primary = FailingLLM()
    fallback = RecordingLLM()
    extractor = GraphExtractor(llm_client=primary, fallback_llm_client=fallback)

    result = extractor.extract_episode({"index": 3, "text": "Alice meets Bob."}, "English")
    graph = extractor.to_graph()

    assert result["total_chunks"] == 1
    assert result["failed_chunks"] == 0
    assert result["error"] is None
    assert len(fallback.excerpts) == 1
    assert graph["node_count"] == 1


def test_successful_primary_llm_does_not_call_fallback_client():
    primary = RecordingLLM()
    fallback = UnexpectedFallbackLLM()
    extractor = GraphExtractor(llm_client=primary, fallback_llm_client=fallback)

    result = extractor.extract_episode({"index": 5, "text": "Alice meets Bob."}, "English")
    graph = extractor.to_graph()

    assert result["total_chunks"] == 1
    assert result["failed_chunks"] == 0
    assert result["error"] is None
    assert len(primary.excerpts) == 1
    assert fallback.calls == 0
    assert graph["node_count"] == 1


def test_default_fallback_client_is_created_lazily(monkeypatch):
    created_fallbacks = []

    class FakeDefaultLLM(RecordingLLM):
        @classmethod
        def openrouter_fallback(cls):
            created_fallbacks.append(True)
            return UnexpectedFallbackLLM()

    monkeypatch.setattr(graph_extractor_module, "LLMClient", FakeDefaultLLM)
    extractor = GraphExtractor()

    result = extractor.extract_episode({"index": 6, "text": "Alice meets Bob."}, "English")

    assert result["total_chunks"] == 1
    assert result["failed_chunks"] == 0
    assert result["error"] is None
    assert created_fallbacks == []


def test_fresh_extraction_canonicalizes_entity_type_case_and_whitespace():
    llm = EntityTypeLLM(["Concept", " concept ", "CONCEPT"])
    extractor = GraphExtractor(llm_client=llm)

    for index in range(3):
        extractor.extract_episode({"index": index, "text": f"Entity {index}"}, "English")

    assert [node["type"] for node in extractor.to_graph()["nodes"]] == [
        "Concept", "Concept", "Concept"
    ]


def test_loaded_graph_and_later_extraction_share_first_seen_type_label():
    llm = EntityTypeLLM(["cOnCePt"])
    extractor = GraphExtractor(llm_client=llm)
    extractor.load_graph({
        "nodes": [
            {"id": "n1", "name": "A", "type": "concept"},
            {"id": "n2", "name": "B", "type": "Concept"},
            {"id": "n3", "name": "C", "type": " CONCEPT "},
        ],
        "edges": [],
    })

    extractor.extract_episode({"index": 3, "text": "Entity 4"}, "English")

    assert [node["type"] for node in extractor.to_graph()["nodes"]] == [
        "concept", "concept", "concept", "concept"
    ]


def test_entity_type_key_uses_collapsed_whitespace_and_unicode_casefold():
    assert GraphExtractor._normalize_type_key("  Data\t  Model ") == "data model"
    assert GraphExtractor._normalize_type_key("Straße") == "strasse"
    assert GraphExtractor._normalize_type_key("STRASSE") == "strasse"


def test_existing_item_tracks_later_metadata_update_without_a_quote():
    extractor = GraphExtractor(llm_client=UnexpectedFallbackLLM())
    node_id = extractor._get_or_create_node(
        name="Alice",
        episode_index=0,
        description="Short",
        quote="Alice arrived.",
    )

    extractor._get_or_create_node(
        name="Alice",
        episode_index=2,
        description="A longer updated description",
        quote="",
    )
    node = next(node for node in extractor.to_graph()["nodes"] if node["id"] == node_id)

    assert node["last_episode"] == 2
    assert node["description"] == "A longer updated description"
    assert node["mentions"] == [{"episode": 0, "quote": "Alice arrived."}]


def test_loading_legacy_graph_recovers_last_episode_from_mentions():
    extractor = GraphExtractor(llm_client=UnexpectedFallbackLLM())
    extractor.load_graph({
        "nodes": [{
            "id": "n1",
            "name": "Alice",
            "first_episode": 0,
            "mentions": [{"episode": 3, "quote": "Alice returned."}],
        }],
        "edges": [],
    })

    assert extractor.to_graph()["nodes"][0]["last_episode"] == 3
