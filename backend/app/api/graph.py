"""
书籍图谱相关 API 路由
上传书籍 -> 分章 -> 逐章抽取知识图谱 -> 按阅读进度展开
采用项目上下文机制，服务端持久化状态
"""

import os
import traceback
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.book_segmenter import segment_book_hybrid
from ..services.graph_extractor import detect_language
from ..services.extraction_manager import ExtractionManager
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
    return [
        {
            "index": ep["index"],
            "title": ep["title"],
            "start_char": ep["start_char"],
            "end_char": ep["end_char"],
            "char_count": ep["char_count"],
        }
        for ep in episodes
    ]


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
            })

    return "".join(full_parts), episodes


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
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": t('api.requireFileUpload')
            }), 400

        project = ProjectManager.create_project(name=book_name)
        logger.info(f"创建书籍项目: {project.project_id}")

        text_parts = []
        structured_files = []
        all_files_structured = True
        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
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
        ProjectManager.save_extracted_text(project.project_id, full_text)
        ProjectManager.save_episodes(project.project_id, episodes)

        # 语言检测
        project.language = detect_language(full_text)
        project.episodes = _episode_meta(episodes)
        project.status = ProjectStatus.CREATED
        ProjectManager.save_project(project)

        logger.info(
            f"=== 分章完成 === 项目ID: {project.project_id}, "
            f"章节数: {len(episodes)}, 语言: {project.language}"
        )

        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "name": project.name,
                "language": project.language,
                "episodes": project.episodes,
                "files": project.files,
                "total_text_length": project.total_text_length,
            }
        })

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

        episodes = ProjectManager.get_episodes(project_id)
        if not episodes:
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
