from app.services.document_classifier import classify_document, document_sample


class FakeClassifierLLM:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.messages = None

    def chat_json(self, messages, **kwargs):
        self.messages = messages
        if self.error:
            raise self.error
        return self.payload


def test_document_sample_skips_empty_prefix_and_is_bounded():
    sample = document_sample("\n \n" + ("Academic paper text " * 300), limit=2000)

    assert sample.startswith("Academic paper text")
    assert len(sample) == 2000


def test_academic_paper_alias_is_classified_as_textbook():
    llm = FakeClassifierLLM({"document_kind": "academic_paper", "confidence": 0.93})

    result = classify_document("Research abstract and methods.", llm_client=llm)

    assert result.kind == "textbook"
    assert result.confidence == 0.93
    assert "Research abstract and methods." in llm.messages[-1]["content"]


def test_classifier_failure_returns_uncertain_without_raising():
    result = classify_document(
        "Some readable content.",
        llm_client=FakeClassifierLLM(error=RuntimeError("provider unavailable")),
    )

    assert result.kind == "uncertain"
    assert result.confidence == 0.0

