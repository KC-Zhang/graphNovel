import io
import json
from pathlib import Path

import fitz
import pytest

from app import create_app
from app.models.project import ProjectManager, ProjectStatus
from app.services.document_classifier import DocumentClassification


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


def _pdf_upload_bytes():
    document = fitz.open()
    first = document.new_page()
    first.insert_text((72, 72), "Chapter 1", fontsize=20)
    first.insert_text((72, 110), "Academic abstract and first-page text.", fontsize=11)

    image_page = document.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), False)
    pixmap.clear_with(0x224466)
    image_page.insert_image(fitz.Rect(72, 72, 144, 144), pixmap=pixmap)

    third = document.new_page()
    third.insert_text((72, 72), "Chapter 2", fontsize=20)
    third.insert_text((72, 110), "The final physical page.", fontsize=11)
    document.set_toc([[1, "Chapter 1", 1], [1, "Chapter 2", 3]])
    payload = document.tobytes()
    document.close()
    return payload


def _upload_pdf(client, pdf_bytes=None):
    return client.post(
        "/api/graph/upload",
        data={
            "book_name": "Academic Sample",
            "files": (io.BytesIO(pdf_bytes or _pdf_upload_bytes()), "sample.pdf"),
        },
        content_type="multipart/form-data",
    )


def test_textbook_pdf_defaults_to_physical_pages_and_persists_metadata(
    app_with_projects, monkeypatch
):
    monkeypatch.setattr(
        "app.api.graph.classify_document",
        lambda text: DocumentClassification("textbook", 0.96),
    )

    response = _upload_pdf(app_with_projects.test_client())
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    data = payload["data"]
    assert data["source_format"] == "pdf"
    assert data["document_kind"] == "textbook"
    assert data["classification_confidence"] == 0.96
    assert data["reading_mode"] == "page"
    assert data["page_count"] == 3
    assert data["episode_count"] == 3
    assert [episode["page_number"] for episode in data["episodes"]] == [1, 2, 3]
    assert data["episodes"][1]["char_count"] == 0
    assert data["episodes"][1]["image_count"] == 1
    assert data["chapter_detection_status"] == "outline"

    document = ProjectManager.get_pdf_document(data["project_id"])
    assert len(document["pages"]) == 3
    assert document["pages"][1]["image_count"] == 1


def test_novel_pdf_defaults_to_detected_chapters(app_with_projects, monkeypatch):
    monkeypatch.setattr(
        "app.api.graph.classify_document",
        lambda text: DocumentClassification("novel", 0.91),
    )

    response = _upload_pdf(app_with_projects.test_client())
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["reading_mode"] == "chapter"
    assert [episode["title"] for episode in data["episodes"]] == ["Chapter 1", "Chapter 2"]
    assert all(episode["unit_type"] == "chapter" for episode in data["episodes"])


def test_uncertain_pdf_requires_mode_before_extraction(app_with_projects, monkeypatch):
    monkeypatch.setattr(
        "app.api.graph.classify_document",
        lambda text: DocumentClassification("uncertain", 0.0),
    )
    client = app_with_projects.test_client()
    upload = _upload_pdf(client).get_json()["data"]

    assert upload["reading_mode"] is None
    assert upload["episodes"] == []
    blocked = client.post(
        "/api/graph/extract",
        json={"project_id": upload["project_id"], "upto": 0},
    )
    assert blocked.status_code == 409

    selected = client.post(
        f"/api/graph/project/{upload['project_id']}/reading-mode",
        json={"mode": "page"},
    )
    selected_data = selected.get_json()["data"]
    assert selected.status_code == 200
    assert selected_data["reading_mode"] == "page"
    assert selected_data["episode_count"] == 3


def test_pdf_mode_switch_rebuilds_episodes_but_is_locked_after_extraction(
    app_with_projects, monkeypatch
):
    monkeypatch.setattr(
        "app.api.graph.classify_document",
        lambda text: DocumentClassification("textbook", 0.9),
    )
    client = app_with_projects.test_client()
    upload = _upload_pdf(client).get_json()["data"]
    project_id = upload["project_id"]

    chapter_response = client.post(
        f"/api/graph/project/{project_id}/reading-mode",
        json={"mode": "chapter"},
    )
    chapter_data = chapter_response.get_json()["data"]
    assert chapter_response.status_code == 200
    assert chapter_data["reading_mode"] == "chapter"
    assert [episode["title"] for episode in chapter_data["episodes"]] == [
        "Chapter 1",
        "Chapter 2",
    ]

    project = ProjectManager.get_project(project_id)
    project.extracted_upto = 0
    ProjectManager.save_project(project)
    locked = client.post(
        f"/api/graph/project/{project_id}/reading-mode",
        json={"mode": "page"},
    )
    assert locked.status_code == 409


def test_pdf_source_supports_inline_range_requests(app_with_projects, monkeypatch):
    monkeypatch.setattr(
        "app.api.graph.classify_document",
        lambda text: DocumentClassification("textbook", 0.9),
    )
    client = app_with_projects.test_client()
    pdf_bytes = _pdf_upload_bytes()
    project = _upload_pdf(client, pdf_bytes).get_json()["data"]

    response = client.get(
        f"/api/graph/project/{project['project_id']}/source",
        headers={"Range": "bytes=0-15"},
    )

    assert response.status_code == 206
    assert response.mimetype == "application/pdf"
    assert response.headers["Accept-Ranges"] == "bytes"
    assert "Content-Range" in response.headers["Access-Control-Expose-Headers"]
    assert response.headers["Content-Range"].startswith(f"bytes 0-15/{len(pdf_bytes)}")
    assert response.data == pdf_bytes[:16]

    full_response = client.get(f"/api/graph/project/{project['project_id']}/source")
    etag = full_response.headers["ETag"]
    not_modified = client.get(
        f"/api/graph/project/{project['project_id']}/source",
        headers={"If-None-Match": etag},
    )
    assert full_response.status_code == 200
    assert full_response.headers["Content-Disposition"].startswith("inline;")
    assert not_modified.status_code == 304


def test_txt_upload_keeps_chapter_only_behavior(app_with_projects, monkeypatch):
    episodes = [
        {
            "index": 0,
            "title": "Chapter 1",
            "start_char": 0,
            "end_char": 18,
            "char_count": 18,
            "text": "Chapter 1\nA story",
        }
    ]
    monkeypatch.setattr("app.api.graph.segment_book_hybrid", lambda text: episodes)

    response = app_with_projects.test_client().post(
        "/api/graph/upload",
        data={
            "book_name": "Plain Text",
            "files": (io.BytesIO(b"Chapter 1\nA story"), "story.txt"),
        },
        content_type="multipart/form-data",
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["source_format"] == "txt"
    assert data["reading_mode"] == "chapter"
    assert data["document_kind"] is None
    assert data["page_count"] == 0
    assert data["episode_count"] == 1
    assert data["episodes"][0]["unit_type"] == "chapter"
