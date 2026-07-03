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


def test_long_episode_is_extracted_in_small_section_sized_chunks():
    llm = RecordingLLM()
    extractor = GraphExtractor(llm_client=llm)
    paragraph = (
        "Alice met Bob at the station. Clara watched from the balcony while "
        "Daniel carried the old map across town.\n\n"
    )
    text = paragraph * 90

    extractor.extract_episode({"index": 4, "text": text}, "English")
    graph = extractor.to_graph()

    assert len(llm.excerpts) >= 3
    assert all(len(excerpt) <= _MAX_CHARS_PER_CALL for excerpt in llm.excerpts)
    assert {m["episode"] for node in graph["nodes"] for m in node["mentions"]} == {4}
