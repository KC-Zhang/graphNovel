import time

import pytest

from app.models.project import ProjectManager, ProjectStatus
from app.services.extraction_manager import ExtractionManager


def _wait_idle(mgr, project_id, total, timeout=5.0):
    """轮询等待 worker 线程结束（running 变为 False）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = mgr.status(project_id, total)
        if not status["running"]:
            return status
        time.sleep(0.02)
    raise AssertionError("extraction worker did not finish within timeout")


@pytest.fixture()
def isolated_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    mgr = ExtractionManager()
    mgr._states.clear()
    yield mgr
    mgr._states.clear()


def _make_project(episodes):
    project = ProjectManager.create_project("Retry Book")
    ProjectManager.save_episodes(project.project_id, episodes)
    project.episodes = [{"index": e["index"], "title": e["title"]} for e in episodes]
    project.language = "English"
    ProjectManager.save_project(project)
    return project


def test_failed_chapter_is_tracked_then_retried_after_api_recovers(isolated_projects, monkeypatch):
    mgr = isolated_projects
    # 共享开关：模拟先前接口故障（拒绝含 BROKEN 的章节），修复后放行。
    flags = {"allow_broken": False}

    class FlakyLLM:
        def __init__(self, *args, **kwargs):
            pass

        def chat_json(self, messages, **kwargs):
            content = messages[-1]["content"]
            if "BROKEN" in content and not flags["allow_broken"]:
                raise RuntimeError("Access to model denied. Please make sure you are eligible.")
            return {
                "entities": [
                    {"name": "Hero", "type": "Person", "aliases": [], "description": "", "quote": f"q{content[:1]}"}
                ],
                "relations": [],
            }

    monkeypatch.setattr("app.services.graph_extractor.LLMClient", FlakyLLM)

    episodes = [
        {"index": 0, "title": "c0", "text": "ok chapter zero"},
        {"index": 1, "title": "c1", "text": "BROKEN chapter one"},
        {"index": 2, "title": "c2", "text": "ok chapter two"},
    ]
    project = _make_project(episodes)

    # 第一次：章节 1 完全失败，但前进进度仍推进到最后一章
    mgr.ensure(project.project_id, upto=2, language="English", episodes=episodes, locale="en")
    _wait_idle(mgr, project.project_id, total=3)

    persisted = ProjectManager.get_project(project.project_id)
    assert persisted.failed_episodes == [1]
    assert persisted.extracted_upto == 2
    assert persisted.error and "denied" in persisted.error.lower()
    assert persisted.status != ProjectStatus.GRAPH_COMPLETED

    status = mgr.status(project.project_id, total=3)
    assert status["failed_episodes"] == [1]

    # 修复接口后再次触发：失败章节被自动重试并补齐
    flags["allow_broken"] = True
    mgr.ensure(project.project_id, upto=2, language="English", episodes=episodes, locale="en")
    _wait_idle(mgr, project.project_id, total=3)

    recovered = ProjectManager.get_project(project.project_id)
    assert recovered.failed_episodes == []
    assert recovered.error is None
    assert recovered.status == ProjectStatus.GRAPH_COMPLETED

    graph = ProjectManager.get_graph(project.project_id)
    episodes_with_mentions = {m["episode"] for node in graph["nodes"] for m in node["mentions"]}
    assert 1 in episodes_with_mentions


def test_persistently_failing_chapter_does_not_loop_forever(isolated_projects, monkeypatch):
    mgr = isolated_projects

    class AlwaysFailChapterOne:
        def __init__(self, *args, **kwargs):
            pass

        def chat_json(self, messages, **kwargs):
            content = messages[-1]["content"]
            if "BROKEN" in content:
                raise RuntimeError("still broken")
            return {"entities": [], "relations": []}

    monkeypatch.setattr("app.services.graph_extractor.LLMClient", AlwaysFailChapterOne)

    episodes = [
        {"index": 0, "title": "c0", "text": "ok chapter zero"},
        {"index": 1, "title": "c1", "text": "BROKEN chapter one"},
    ]
    project = _make_project(episodes)

    # worker 必须在有界时间内结束，不能因失败章节而死循环
    mgr.ensure(project.project_id, upto=1, language="English", episodes=episodes, locale="en")
    status = _wait_idle(mgr, project.project_id, total=2, timeout=5.0)

    assert status["running"] is False
    assert status["failed_episodes"] == [1]
    assert ProjectManager.get_project(project.project_id).extracted_upto == 1
