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
