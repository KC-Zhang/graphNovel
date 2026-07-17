"""
书籍图谱相关 API 路由
上传书籍 -> 分章 -> 逐章抽取知识图谱 -> 按阅读进度展开
采用项目上下文机制，服务端持久化状态
"""

import os
import re
import traceback
from flask import request, jsonify, send_file

from . import graph_bp
from ..config import Config
from ..services.book_segmenter import segment_book_hybrid
from ..services.document_classifier import classify_document
from ..services.graph_extractor import detect_language
from ..services.extraction_manager import ExtractionManager
from ..services.pdf_segmenter import (
    build_pdf_page_episodes,
    build_pdf_text,
    segment_pdf_chapters,
)
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..utils.locale import t, get_locale
from ..models.task import TaskManager
from ..models.project import ProjectManager, ProjectStatus

# 默认预取章节数（阅读位置之后额外抽取的章节数）
DEFAULT_PREFETCH = 2

logger = get_logger('bookmiro.api')


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


def _episode_meta(episodes):
    """从完整章节数据提取元数据（不含正文）"""
    optional_fields = (
        "unit_type",
        "page_number",
        "page_end",
        "page_label",
        "pdf_page_index",
        "image_count",
    )
    result = []
    for ep in episodes:
        item = {
            "index": ep["index"],
            "title": ep["title"],
            "start_char": ep.get("start_char", 0),
            "end_char": ep.get("end_char", 0),
            "char_count": ep.get("char_count", len(ep.get("text", ""))),
            "unit_type": ep.get("unit_type", "chapter"),
        }
        for field in optional_fields:
            if field in ep:
                item[field] = ep[field]
        result.append(item)
    return result


def _build_episodes_from_structured_files(structured_files):
    """用 EPUB 导航目录返回的章节正文重建完整文本和 offsets。"""
    full_parts = []
    episodes = []
    cursor = 0

    for file_episodes in structured_files:
        for source in file_episodes:
            text = TextProcessor.preprocess_text(source.get("text", ""))
            if not text:
                continue
            if full_parts:
                full_parts.append("\n\n")
                cursor += 2
            start = cursor
            full_parts.append(text)
            cursor += len(text)
            episodes.append({
                "index": len(episodes),
                "title": TextProcessor.preprocess_text(source.get("title", "")) or f"Section {len(episodes) + 1}",
                "start_char": start,
                "end_char": cursor,
                "char_count": len(text),
                "text": text,
                "unit_type": "chapter",
            })

    return "".join(full_parts), episodes


def _normalize_pdf_document(document):
    """对逐页文本做与旧上传链路一致的轻量预处理。"""
    for page in document.get("pages") or []:
        page["text"] = TextProcessor.preprocess_text(page.get("text", ""))
        for heading in page.get("headings") or []:
            heading["text"] = TextProcessor.preprocess_text(heading.get("text", ""))
    return document


def _set_project_episodes(project, episodes):
    ProjectManager.save_episodes(project.project_id, episodes)
    project.episodes = _episode_meta(episodes)


def _source_format(extensions):
    unique = {ext.lstrip('.').lower() for ext in extensions if ext}
    if len(unique) == 1:
        value = next(iter(unique))
        return "md" if value == "markdown" else value
    return "mixed"


def _safe_pdf_source(project):
    """Resolve a project's PDF without trusting paths supplied by the client or metadata."""
    if not re.fullmatch(r"proj_[0-9a-f]{12}", project.project_id or ""):
        return None

    projects_root = os.path.realpath(ProjectManager.PROJECTS_DIR)
    project_dir = os.path.realpath(ProjectManager._get_project_dir(project.project_id))
    files_dir = os.path.realpath(ProjectManager._get_project_files_dir(project.project_id))
    try:
        if os.path.commonpath([projects_root, project_dir]) != projects_root:
            return None
        if os.path.commonpath([project_dir, files_dir]) != project_dir:
            return None
    except ValueError:
        return None

    saved_names = [
        item.get("saved_filename")
        for item in project.files
        if item.get("saved_filename") and str(item.get("saved_filename")).lower().endswith(".pdf")
    ]
    candidates = [os.path.join(files_dir, os.path.basename(name)) for name in saved_names]
    if not candidates:
        candidates = [
            path for path in ProjectManager.get_project_files(project.project_id)
            if path.lower().endswith(".pdf")
        ]

    for candidate in candidates:
        resolved = os.path.realpath(candidate)
        try:
            inside_files = os.path.commonpath([files_dir, resolved]) == files_dir
        except ValueError:
            inside_files = False
        if inside_files and os.path.isfile(resolved) and resolved.lower().endswith(".pdf"):
            return resolved
    return None


def _pdf_project_data(project):
    """Use the regular project wire shape for upload and mode-switch responses."""
    return project.to_dict(include_episodes=True)


# ============== 项目（书籍）管理接口 ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """获取书籍项目详情"""
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/<project_id>/source', methods=['GET'])
def get_project_source(project_id: str):
    """流式返回原始 PDF，供 PDF.js 保留图片、字体和页面排版。"""
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404
    if project.source_format != "pdf":
        return jsonify({
            "success": False,
            "error": "Original source streaming is available for PDF projects only."
        }), 400

    source_path = _safe_pdf_source(project)
    if not source_path:
        return jsonify({
            "success": False,
            "error": t('api.textNotFound')
        }), 404

    original_name = next(
        (item.get("filename") for item in project.files if str(item.get("filename", "")).lower().endswith(".pdf")),
        f"{project.name}.pdf",
    )
    response = send_file(
        source_path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=original_name,
        conditional=True,
        etag=True,
        last_modified=os.path.getmtime(source_path),
    )
    response.headers["Access-Control-Expose-Headers"] = (
        "Accept-Ranges, Content-Length, Content-Range, ETag, Last-Modified"
    )
    return response


@graph_bp.route('/project/<project_id>/reading-mode', methods=['POST'])
def set_project_reading_mode(project_id: str):
    """Rebuild a new PDF project's episodes as chapters or physical pages."""
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404
    if project.source_format != "pdf":
        return jsonify({
            "success": False,
            "error": "Reading mode can only be changed for PDF projects."
        }), 400

    payload = request.get_json(silent=True) or {}
    mode = str(payload.get("mode", "")).strip().casefold()
    if mode not in {"chapter", "page"}:
        return jsonify({
            "success": False,
            "error": "mode must be 'chapter' or 'page'."
        }), 400

    extraction_status = ExtractionManager().status(project_id, len(project.episodes or []))
    extraction_started = (
        project.status != ProjectStatus.CREATED
        or project.extracted_upto != -1
        or project.extract_task_id is not None
        or extraction_status.get("running", False)
        or ProjectManager.get_graph(project_id) is not None
    )
    if extraction_started:
        return jsonify({
            "success": False,
            "error": "Reading mode cannot be changed after graph extraction has started."
        }), 409

    document = ProjectManager.get_pdf_document(project_id)
    if document is None:
        source_path = _safe_pdf_source(project)
        if not source_path:
            return jsonify({
                "success": False,
                "error": t('api.textNotFound')
            }), 404
        document = _normalize_pdf_document(FileParser.extract_pdf_document(source_path))
        full_text, _ = build_pdf_text(document)
        ProjectManager.save_pdf_document(project_id, document)
        ProjectManager.save_extracted_text(project_id, full_text)

    if mode == "page":
        episodes = build_pdf_page_episodes(document)
    else:
        try:
            episodes, chapter_status = segment_pdf_chapters(document)
        except Exception as exc:
            logger.warning(
                "PDF 分章重建失败 (error_type=%s)",
                type(exc).__name__,
            )
            episodes, chapter_status = [], "unreliable"
        project.chapter_detection_status = chapter_status

    project.reading_mode = mode
    project.page_count = len(document.get("pages") or [])
    _set_project_episodes(project, episodes)
    ExtractionManager().reset(project_id)
    ProjectManager.save_project(project)

    return jsonify({
        "success": True,
        "data": _pdf_project_data(project),
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """列出所有书籍项目"""
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)

    return jsonify({
        "success": True,
        "data": [p.to_dict(include_episodes=False) for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """删除书籍项目"""
    success = ProjectManager.delete_project(project_id)

    if not success:
        return jsonify({
            "success": False,
            "error": t('api.projectDeleteFailed', id=project_id)
        }), 404

    return jsonify({
        "success": True,
        "message": t('api.projectDeleted', id=project_id)
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """重置项目状态（用于重新抽取图谱）"""
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    project.status = ProjectStatus.CREATED
    project.extract_task_id = None
    project.extracted_upto = -1
    project.failed_episodes = []
    project.error = None
    ProjectManager.delete_graph(project_id)
    ExtractionManager().reset(project_id)
    ProjectManager.save_project(project)

    return jsonify({
        "success": True,
        "message": t('api.projectReset', id=project_id),
        "data": project.to_dict()
    })


@graph_bp.route('/project/<project_id>/repair', methods=['POST'])
def repair_project(project_id: str):
    """从已保存的提取文本重建章节元数据，并清空旧图谱以便重新抽取。"""
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    text = ProjectManager.get_extracted_text(project_id)
    if not text:
        return jsonify({
            "success": False,
            "error": t('api.textNotFound')
        }), 404

    episodes = segment_book_hybrid(text)
    if not episodes:
        return jsonify({
            "success": False,
            "error": t('api.noDocProcessed')
        }), 400

    for episode in episodes:
        episode.setdefault("unit_type", "chapter")
    ProjectManager.save_episodes(project_id, episodes)
    ProjectManager.delete_graph(project_id)
    ExtractionManager().reset(project_id)
    project.episodes = _episode_meta(episodes)
    project.status = ProjectStatus.CREATED
    project.extract_task_id = None
    project.extracted_upto = -1
    project.failed_episodes = []
    project.error = None
    ProjectManager.save_project(project)

    return jsonify({
        "success": True,
        "message": t('api.projectRepaired', id=project_id),
        "data": project.to_dict(include_episodes=False)
    })


# ============== 接口1：上传书籍并分章 ==============

@graph_bp.route('/upload', methods=['POST'])
def upload_book():
    """
    上传书籍文件（PDF/EPUB/TXT/MD），解析文本并切分为章节。

    请求方式：multipart/form-data
    参数：
        files: 上传的文件（可多个，会按顺序合并为一本书）
        book_name: 书名（可选）
    返回：
        {
          "success": true,
          "data": {
            "project_id": "...",
            "name": "...",
            "language": "Chinese",
            "episodes": [{index,title,start_char,end_char,char_count}, ...]
          }
        }
    """
    try:
        logger.info("=== 上传书籍并分章 ===")

        book_name = request.form.get('book_name') or request.form.get('project_name') or 'Untitled Book'

        uploaded_files = request.files.getlist('files')
        valid_files = [
            file for file in uploaded_files
            if file and file.filename and allowed_file(file.filename)
        ]
        if not valid_files:
            return jsonify({
                "success": False,
                "error": t('api.requireFileUpload')
            }), 400

        extensions = [os.path.splitext(file.filename)[1].lower() for file in valid_files]
        if '.pdf' in extensions and len(valid_files) != 1:
            return jsonify({
                "success": False,
                "error": "PDF reading modes require one PDF file per project."
            }), 400

        project = ProjectManager.create_project(name=book_name)
        logger.info(f"创建书籍项目: {project.project_id}")

        # PDF 使用逐页数据和原始文件的专用链路。
        if extensions == ['.pdf']:
            uploaded = valid_files[0]
            file_info = ProjectManager.save_file_to_project(
                project.project_id, uploaded, uploaded.filename
            )
            project.files.append({
                "filename": file_info["original_filename"],
                "size": file_info["size"],
            })

            document = _normalize_pdf_document(
                FileParser.extract_pdf_document(file_info["path"])
            )
            full_text, _ = build_pdf_text(document)
            classification = classify_document(full_text)
            page_episodes = build_pdf_page_episodes(document)
            try:
                chapter_episodes, chapter_status = segment_pdf_chapters(document)
            except Exception as exc:
                logger.warning(
                    "PDF 分章分析失败，仍可使用按页模式 (error_type=%s)",
                    type(exc).__name__,
                )
                chapter_episodes, chapter_status = [], "unreliable"

            if classification.kind == "textbook":
                reading_mode = "page"
                episodes = page_episodes
            elif classification.kind == "novel":
                reading_mode = "chapter"
                episodes = chapter_episodes
            else:
                reading_mode = None
                episodes = []

            project.source_format = "pdf"
            project.reading_mode = reading_mode
            project.document_kind = classification.kind
            project.classification_confidence = classification.confidence
            project.page_count = len(document.get("pages") or [])
            project.chapter_detection_status = chapter_status
            project.total_text_length = len(full_text)
            project.language = detect_language(full_text)
            project.status = ProjectStatus.CREATED

            ProjectManager.save_pdf_document(project.project_id, document)
            ProjectManager.save_extracted_text(project.project_id, full_text)
            _set_project_episodes(project, episodes)
            ProjectManager.save_project(project)

            logger.info(
                "=== PDF 处理完成 === 项目ID: %s, 页数: %s, 类型: %s, "
                "默认模式: %s, 分章状态: %s, episode数: %s",
                project.project_id,
                project.page_count,
                project.document_kind,
                project.reading_mode,
                project.chapter_detection_status,
                len(episodes),
            )
            return jsonify({"success": True, "data": _pdf_project_data(project)})

        text_parts = []
        structured_files = []
        all_files_structured = True
        for file in valid_files:
            file_info = ProjectManager.save_file_to_project(
                project.project_id, file, file.filename
            )
            project.files.append({
                "filename": file_info["original_filename"],
                "size": file_info["size"]
            })
            text = FileParser.extract_text(file_info["path"])
            text = TextProcessor.preprocess_text(text)
            text_parts.append(text)

            ext = os.path.splitext(file.filename)[1].lower()
            if ext == '.epub':
                structured_episodes = FileParser.extract_epub_episodes(file_info["path"])
                if structured_episodes:
                    structured_files.append(structured_episodes)
                else:
                    all_files_structured = False
            else:
                all_files_structured = False

        if not text_parts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": t('api.noDocProcessed')
            }), 400

        if all_files_structured and structured_files:
            full_text, episodes = _build_episodes_from_structured_files(structured_files)
            logger.info("使用 EPUB 结构化目录分章: episodes=%s", len(episodes))
        else:
            full_text = "\n\n".join(text_parts)
            episodes = segment_book_hybrid(full_text)

        if not episodes:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": t('api.noDocProcessed')
            }), 400

        project.total_text_length = len(full_text)
        project.source_format = _source_format(extensions)
        project.reading_mode = "chapter"
        project.document_kind = None
        project.classification_confidence = None
        project.page_count = 0
        project.chapter_detection_status = (
            "structured" if all_files_structured and structured_files else "text"
        )
        ProjectManager.save_extracted_text(project.project_id, full_text)
        for episode in episodes:
            episode.setdefault("unit_type", "chapter")
        _set_project_episodes(project, episodes)

        # 语言检测
        project.language = detect_language(full_text)
        project.status = ProjectStatus.CREATED
        ProjectManager.save_project(project)

        logger.info(
            f"=== 分章完成 === 项目ID: {project.project_id}, "
            f"章节数: {len(episodes)}, 语言: {project.language}"
        )

        return jsonify({"success": True, "data": project.to_dict(include_episodes=True)})

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 接口2：按需增量抽取知识图谱 ==============

@graph_bp.route('/extract', methods=['POST'])
def extract_graph():
    """
    确保章节 0..upto 已（或正在）被抽取。随阅读进度可重复调用以抬高目标。

    请求（JSON）：
        { "project_id": "...", "upto": N }   # upto 可选，默认预取前几章
    返回：
        { "success": true, "data": { extracted_upto, target, running, total } }
    """
    try:
        data = request.get_json() or {}
        project_id = data.get('project_id')

        if not project_id:
            return jsonify({
                "success": False,
                "error": t('api.requireProjectId')
            }), 400

        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t('api.projectNotFound', id=project_id)
            }), 404

        if project.source_format == "pdf" and project.reading_mode is None:
            return jsonify({
                "success": False,
                "error": "Choose chapter or page reading mode before starting graph extraction."
            }), 409

        episodes = ProjectManager.get_episodes(project_id)
        if not episodes:
            if (
                project.source_format == "pdf"
                and project.reading_mode == "chapter"
                and project.chapter_detection_status == "unreliable"
            ):
                return jsonify({
                    "success": False,
                    "error": "No reliable PDF chapters were detected. Switch to page mode."
                }), 409
            return jsonify({
                "success": False,
                "error": t('api.textNotFound')
            }), 400

        upto = data.get('upto')
        if upto is None:
            upto = DEFAULT_PREFETCH
        try:
            upto = int(upto)
        except (TypeError, ValueError):
            upto = DEFAULT_PREFETCH

        language = project.language or "the source language"

        status = ExtractionManager().ensure(
            project_id=project_id,
            upto=upto,
            language=language,
            episodes=episodes,
            locale=get_locale(),
        )

        return jsonify({
            "success": True,
            "data": {"project_id": project_id, **status}
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/status/<project_id>', methods=['GET'])
def get_extract_status(project_id: str):
    """查询某本书的增量抽取进度"""
    try:
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t('api.projectNotFound', id=project_id)
            }), 404

        total = len(project.episodes or [])
        status = ExtractionManager().status(project_id, total)

        return jsonify({
            "success": True,
            "data": {"project_id": project_id, **status}
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 任务查询接口 ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """查询任务状态"""
    task = TaskManager().get_task(task_id)

    if not task:
        return jsonify({
            "success": False,
            "error": t('api.taskNotFound', id=task_id)
        }), 404

    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """列出所有任务"""
    tasks = TaskManager().list_tasks()

    return jsonify({
        "success": True,
        "data": tasks,
        "count": len(tasks)
    })


# ============== 图谱与章节数据接口 ==============

@graph_bp.route('/data/<project_id>', methods=['GET'])
def get_graph_data(project_id: str):
    """
    获取图谱数据（节点和边，含 first_episode 与 mentions）。
    前端按阅读进度过滤，实现逐章展开。
    """
    try:
        graph = ProjectManager.get_graph(project_id)
        if graph is None:
            return jsonify({
                "success": True,
                "data": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}
            })

        return jsonify({
            "success": True,
            "data": graph
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/episode/<project_id>/<int:idx>', methods=['GET'])
def get_episode(project_id: str, idx: int):
    """获取单个章节的正文（用于阅读面板）"""
    try:
        episodes = ProjectManager.get_episodes(project_id)
        if not episodes:
            return jsonify({
                "success": False,
                "error": t('api.textNotFound')
            }), 404

        if idx < 0 or idx >= len(episodes):
            return jsonify({
                "success": False,
                "error": t('api.textNotFound')
            }), 404

        return jsonify({
            "success": True,
            "data": episodes[idx]
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
