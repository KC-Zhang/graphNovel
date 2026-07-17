"""
项目上下文管理
用于在服务端持久化项目状态，避免前端在接口间传递大量数据
"""

import os
import json
import uuid
import shutil
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass, field, asdict
from ..config import Config


class ProjectStatus(str, Enum):
    """项目（书籍）状态"""
    CREATED = "created"              # 刚创建，文件已上传并完成分章
    GRAPH_BUILDING = "graph_building"    # 图谱抽取中
    GRAPH_COMPLETED = "graph_completed"  # 图谱抽取完成
    FAILED = "failed"                # 失败


@dataclass
class Project:
    """项目数据模型"""
    project_id: str
    name: str
    status: ProjectStatus
    created_at: str
    updated_at: str
    
    # 文件信息
    files: List[Dict[str, str]] = field(default_factory=list)  # [{filename, path, size}]
    total_text_length: int = 0
    
    # 书籍信息
    language: Optional[str] = None  # 检测到的书籍语言（用于图谱语言锁定）
    episodes: List[Dict[str, Any]] = field(default_factory=list)  # 章节元数据（不含正文）
    # 源文档与阅读模式。旧项目缺少这些字段时保持可加载。
    source_format: Optional[str] = None
    reading_mode: Optional[str] = None  # chapter | page | None (待用户选择)
    document_kind: Optional[str] = None  # novel | textbook | uncertain
    classification_confidence: Optional[float] = None
    page_count: int = 0
    chapter_detection_status: Optional[str] = None
    
    # 图谱抽取信息
    extract_task_id: Optional[str] = None
    extracted_upto: int = -1  # 已抽取到的章节索引（-1 表示尚未抽取）
    # 完全抽取失败（如 LLM 报错）的章节索引集合；供后续在故障恢复后自动重试。
    failed_episodes: List[int] = field(default_factory=list)
    
    # 错误信息
    error: Optional[str] = None
    
    def to_dict(self, include_episodes: bool = True) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            "project_id": self.project_id,
            "name": self.name,
            "status": self.status.value if isinstance(self.status, ProjectStatus) else self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "files": self.files,
            "total_text_length": self.total_text_length,
            "language": self.language,
            "source_format": self.source_format,
            "reading_mode": self.reading_mode,
            "document_kind": self.document_kind,
            "classification_confidence": self.classification_confidence,
            "page_count": self.page_count,
            "chapter_detection_status": self.chapter_detection_status,
            "episode_count": len(self.episodes or []),
            "extract_task_id": self.extract_task_id,
            "extracted_upto": self.extracted_upto,
            "failed_episodes": self.failed_episodes,
            "error": self.error
        }
        if include_episodes:
            data["episodes"] = self.episodes
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """从字典创建"""
        status = data.get('status', 'created')
        if isinstance(status, str):
            status = ProjectStatus(status)
        
        return cls(
            project_id=data['project_id'],
            name=data.get('name', 'Unnamed Project'),
            status=status,
            created_at=data.get('created_at', ''),
            updated_at=data.get('updated_at', ''),
            files=data.get('files', []),
            total_text_length=data.get('total_text_length', 0),
            language=data.get('language'),
            episodes=data.get('episodes', []),
            source_format=data.get('source_format'),
            reading_mode=data.get('reading_mode'),
            document_kind=data.get('document_kind'),
            classification_confidence=data.get('classification_confidence'),
            page_count=data.get('page_count', 0),
            chapter_detection_status=data.get('chapter_detection_status'),
            extract_task_id=data.get('extract_task_id'),
            extracted_upto=data.get('extracted_upto', -1),
            failed_episodes=data.get('failed_episodes', []),
            error=data.get('error')
        )


class ProjectManager:
    """项目管理器 - 负责项目的持久化存储和检索"""
    
    # 项目存储根目录
    PROJECTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'projects')
    
    @classmethod
    def _ensure_projects_dir(cls):
        """确保项目目录存在"""
        os.makedirs(cls.PROJECTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_project_dir(cls, project_id: str) -> str:
        """获取项目目录路径"""
        return os.path.join(cls.PROJECTS_DIR, project_id)
    
    @classmethod
    def _get_project_meta_path(cls, project_id: str) -> str:
        """获取项目元数据文件路径"""
        return os.path.join(cls._get_project_dir(project_id), 'project.json')
    
    @classmethod
    def _get_project_files_dir(cls, project_id: str) -> str:
        """获取项目文件存储目录"""
        return os.path.join(cls._get_project_dir(project_id), 'files')
    
    @classmethod
    def _get_project_text_path(cls, project_id: str) -> str:
        """获取项目提取文本存储路径"""
        return os.path.join(cls._get_project_dir(project_id), 'extracted_text.txt')
    
    @classmethod
    def _get_episodes_path(cls, project_id: str) -> str:
        """获取章节数据（含正文）存储路径"""
        return os.path.join(cls._get_project_dir(project_id), 'episodes.json')

    @classmethod
    def _get_pdf_document_path(cls, project_id: str) -> str:
        """获取 PDF 逐页文本/版式元数据路径。"""
        return os.path.join(cls._get_project_dir(project_id), 'pdf_document.json')
    
    @classmethod
    def _get_graph_path(cls, project_id: str) -> str:
        """获取图谱数据存储路径"""
        return os.path.join(cls._get_project_dir(project_id), 'graph.json')
    
    @classmethod
    def create_project(cls, name: str = "Unnamed Project") -> Project:
        """
        创建新项目
        
        Args:
            name: 项目名称
            
        Returns:
            新创建的Project对象
        """
        cls._ensure_projects_dir()
        
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        
        project = Project(
            project_id=project_id,
            name=name,
            status=ProjectStatus.CREATED,
            created_at=now,
            updated_at=now
        )
        
        # 创建项目目录结构
        project_dir = cls._get_project_dir(project_id)
        files_dir = cls._get_project_files_dir(project_id)
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(files_dir, exist_ok=True)
        
        # 保存项目元数据
        cls.save_project(project)
        
        return project
    
    @classmethod
    def save_project(cls, project: Project) -> None:
        """保存项目元数据"""
        project.updated_at = datetime.now().isoformat()
        meta_path = cls._get_project_meta_path(project.project_id)
        
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(project.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_project(cls, project_id: str) -> Optional[Project]:
        """
        获取项目
        
        Args:
            project_id: 项目ID
            
        Returns:
            Project对象，如果不存在返回None
        """
        meta_path = cls._get_project_meta_path(project_id)
        
        if not os.path.exists(meta_path):
            return None
        
        with open(meta_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return Project.from_dict(data)
    
    @classmethod
    def list_projects(cls, limit: int = 50) -> List[Project]:
        """
        列出所有项目
        
        Args:
            limit: 返回数量限制
            
        Returns:
            项目列表，按创建时间倒序
        """
        cls._ensure_projects_dir()
        
        projects = []
        for project_id in os.listdir(cls.PROJECTS_DIR):
            project = cls.get_project(project_id)
            if project:
                projects.append(project)
        
        # 按创建时间倒序排序
        projects.sort(key=lambda p: p.created_at, reverse=True)
        
        return projects[:limit]
    
    @classmethod
    def delete_project(cls, project_id: str) -> bool:
        """
        删除项目及其所有文件
        
        Args:
            project_id: 项目ID
            
        Returns:
            是否删除成功
        """
        project_dir = cls._get_project_dir(project_id)
        
        if not os.path.exists(project_dir):
            return False
        
        shutil.rmtree(project_dir)
        return True
    
    @classmethod
    def save_file_to_project(cls, project_id: str, file_storage, original_filename: str) -> Dict[str, str]:
        """
        保存上传的文件到项目目录
        
        Args:
            project_id: 项目ID
            file_storage: Flask的FileStorage对象
            original_filename: 原始文件名
            
        Returns:
            文件信息字典 {filename, path, size}
        """
        files_dir = cls._get_project_files_dir(project_id)
        os.makedirs(files_dir, exist_ok=True)
        
        # 生成安全的文件名
        ext = os.path.splitext(original_filename)[1].lower()
        safe_filename = f"{uuid.uuid4().hex[:8]}{ext}"
        file_path = os.path.join(files_dir, safe_filename)
        
        # 保存文件
        file_storage.save(file_path)
        
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        
        return {
            "original_filename": original_filename,
            "saved_filename": safe_filename,
            "path": file_path,
            "size": file_size
        }
    
    @classmethod
    def save_extracted_text(cls, project_id: str, text: str) -> None:
        """保存提取的文本"""
        text_path = cls._get_project_text_path(project_id)
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text)
    
    @classmethod
    def get_extracted_text(cls, project_id: str) -> Optional[str]:
        """获取提取的文本"""
        text_path = cls._get_project_text_path(project_id)
        
        if not os.path.exists(text_path):
            return None
        
        with open(text_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    @classmethod
    def save_episodes(cls, project_id: str, episodes: List[Dict[str, Any]]) -> None:
        """保存章节数据（含正文）"""
        path = cls._get_episodes_path(project_id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(episodes, f, ensure_ascii=False)
    
    @classmethod
    def get_episodes(cls, project_id: str) -> Optional[List[Dict[str, Any]]]:
        """读取章节数据（含正文）"""
        path = cls._get_episodes_path(project_id)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @classmethod
    def save_pdf_document(cls, project_id: str, document: Dict[str, Any]) -> None:
        """保存 PDF 逐页文本和版式元数据；原始 PDF 仍保存在 files/ 中。"""
        path = cls._get_pdf_document_path(project_id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(document, f, ensure_ascii=False)

    @classmethod
    def get_pdf_document(cls, project_id: str) -> Optional[Dict[str, Any]]:
        """读取已持久化的 PDF 逐页元数据。"""
        path = cls._get_pdf_document_path(project_id)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def save_graph(cls, project_id: str, graph: Dict[str, Any]) -> None:
        """保存图谱数据"""
        path = cls._get_graph_path(project_id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(graph, f, ensure_ascii=False)
    
    @classmethod
    def get_graph(cls, project_id: str) -> Optional[Dict[str, Any]]:
        """读取图谱数据"""
        path = cls._get_graph_path(project_id)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @classmethod
    def delete_graph(cls, project_id: str) -> None:
        """删除已保存的图谱数据（如果存在）"""
        path = cls._get_graph_path(project_id)
        if os.path.exists(path):
            os.remove(path)
    
    @classmethod
    def get_project_files(cls, project_id: str) -> List[str]:
        """获取项目的所有文件路径"""
        files_dir = cls._get_project_files_dir(project_id)
        
        if not os.path.exists(files_dir):
            return []
        
        return [
            os.path.join(files_dir, f) 
            for f in os.listdir(files_dir) 
            if os.path.isfile(os.path.join(files_dir, f))
        ]
