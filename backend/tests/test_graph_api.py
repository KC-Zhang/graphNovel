import json
from pathlib import Path

import pytest

from app import create_app
from app.models.project import ProjectManager, ProjectStatus


@pytest.fixture()
def app_with_projects(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    app = create_app()
    app.config.update(TESTING=True)
    return app


def test_project_list_returns_compact_summaries(app_with_projects):
    project = ProjectManager.create_project("Large Book")
    project.status = ProjectStatus.GRAPH_COMPLETED
    project.episodes = [
        {"index": i, "title": f"Chapter {i}", "char_count": 100}
        for i in range(250)
    ]
    ProjectManager.save_project(project)

    res = app_with_projects.test_client().get("/api/graph/project/list")
    payload = res.get_json()

    assert res.status_code == 200
    assert payload["success"] is True
    assert payload["data"][0]["episode_count"] == 250
    assert "episodes" not in payload["data"][0]


def test_repair_project_rebuilds_missing_episode_metadata(app_with_projects):
    project = ProjectManager.create_project("Repair Me")
    ProjectManager.save_extracted_text(
        project.project_id,
        "1\n\nFirst repaired section has useful text.\n\n2\n\nSecond repaired section has useful text.",
    )
    project.status = ProjectStatus.GRAPH_COMPLETED
    project.episodes = []
    ProjectManager.save_project(project)

    res = app_with_projects.test_client().post(f"/api/graph/project/{project.project_id}/repair")
    payload = res.get_json()
    repaired = ProjectManager.get_project(project.project_id)
    episodes_path = Path(ProjectManager._get_episodes_path(project.project_id))

    assert res.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["episode_count"] == 2
    assert repaired.status == ProjectStatus.CREATED
    assert len(repaired.episodes) == 2
    assert episodes_path.exists()


def test_reset_project_clears_saved_graph(app_with_projects):
    project = ProjectManager.create_project("Reset Me")
    project.extracted_upto = 3
    ProjectManager.save_project(project)
    ProjectManager.save_graph(project.project_id, {"nodes": [{"id": "n1"}], "edges": []})

    res = app_with_projects.test_client().post(f"/api/graph/project/{project.project_id}/reset")
    payload = res.get_json()

    assert res.status_code == 200
    assert payload["success"] is True
    assert ProjectManager.get_graph(project.project_id) is None
    assert ProjectManager.get_project(project.project_id).extracted_upto == -1
