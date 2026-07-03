"""
按需增量抽取管理器
每本书维护一个后台 worker，按阅读进度逐章抽取知识图谱：
- 阅读器可随时抬高目标章节（target），worker 会持续推进
- 每抽完一章就落盘 graph.json 与 project.extracted_upto，实现流式展开
- 抽取按章节顺序进行，保留跨章节实体消解的上下文依赖
"""

import threading
import traceback
from typing import Dict, Any, List, Optional

from .graph_extractor import GraphExtractor
from ..models.project import ProjectManager, ProjectStatus
from ..utils.logger import get_logger
from ..utils.locale import set_locale

logger = get_logger('bookmiro.extract')


class _ProjectState:
    """单本书的抽取状态"""

    def __init__(self, upto: int):
        self.target: int = upto          # 期望抽取到的章节索引
        self.upto: int = upto            # 已抽取到的章节索引（-1 表示还没开始）
        self.running: bool = False
        self.error: Optional[str] = None
        self.thread: Optional[threading.Thread] = None


class ExtractionManager:
    """按项目管理增量抽取的单例"""

    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._states: Dict[str, _ProjectState] = {}
                    cls._instance._lock = threading.Lock()
        return cls._instance

    def ensure(
        self,
        project_id: str,
        upto: int,
        language: str,
        episodes: List[Dict[str, Any]],
        locale: str = 'zh',
    ) -> Dict[str, Any]:
        """
        确保章节 0..upto 已（或正在）被抽取。可重复调用以抬高目标。

        Returns: 当前状态 dict
        """
        total = len(episodes)
        upto = max(0, min(upto, total - 1)) if total > 0 else -1

        with self._lock:
            state = self._states.get(project_id)
            if state is None:
                project = ProjectManager.get_project(project_id)
                persisted = project.extracted_upto if project else -1
                state = _ProjectState(upto=persisted)
                self._states[project_id] = state

            if upto > state.target:
                state.target = upto

            if not state.running and state.upto < state.target:
                state.running = True
                state.error = None
                state.thread = threading.Thread(
                    target=self._run,
                    args=(project_id, language, episodes, locale),
                    daemon=True,
                )
                state.thread.start()

            return self._status_locked(project_id, total)

    def _run(self, project_id: str, language: str, episodes: List[Dict[str, Any]], locale: str) -> None:
        set_locale(locale)
        try:
            extractor = GraphExtractor()
            extractor.load_graph(ProjectManager.get_graph(project_id))

            project = ProjectManager.get_project(project_id)
            if project:
                project.status = ProjectStatus.GRAPH_BUILDING
                project.error = None
                ProjectManager.save_project(project)

            while True:
                with self._lock:
                    state = self._states.get(project_id)
                    if not state or state.upto >= state.target:
                        if state:
                            state.running = False
                        break
                    next_idx = state.upto + 1

                if next_idx >= len(episodes):
                    with self._lock:
                        state = self._states.get(project_id)
                        if state:
                            state.upto = len(episodes) - 1
                            state.running = False
                    break

                logger.info(f"[{project_id}] 抽取章节 {next_idx + 1}/{len(episodes)}")
                extractor.extract_episode(episodes[next_idx], language)

                # 落盘
                ProjectManager.save_graph(project_id, extractor.to_graph())
                fresh = ProjectManager.get_project(project_id)
                if fresh:
                    fresh.extracted_upto = next_idx
                    if next_idx >= len(episodes) - 1:
                        fresh.status = ProjectStatus.GRAPH_COMPLETED
                    ProjectManager.save_project(fresh)

                with self._lock:
                    state = self._states.get(project_id)
                    if state:
                        state.upto = next_idx

        except Exception as e:
            logger.error(f"[{project_id}] 抽取失败: {e}")
            logger.debug(traceback.format_exc())
            with self._lock:
                state = self._states.get(project_id)
                if state:
                    state.error = str(e)
                    state.running = False
            fresh = ProjectManager.get_project(project_id)
            if fresh:
                fresh.error = str(e)
                # 已抽取的部分仍可用，不整体置为 FAILED，除非一章都没有
                if fresh.extracted_upto < 0:
                    fresh.status = ProjectStatus.FAILED
                ProjectManager.save_project(fresh)

    def _status_locked(self, project_id: str, total: int) -> Dict[str, Any]:
        state = self._states.get(project_id)
        if state is None:
            project = ProjectManager.get_project(project_id)
            upto = project.extracted_upto if project else -1
            return {
                "extracted_upto": upto,
                "target": upto,
                "running": False,
                "error": None,
                "total": total,
            }
        return {
            "extracted_upto": state.upto,
            "target": state.target,
            "running": state.running,
            "error": state.error,
            "total": total,
        }

    def status(self, project_id: str, total: int) -> Dict[str, Any]:
        with self._lock:
            return self._status_locked(project_id, total)

    def reset(self, project_id: str) -> None:
        """清除内存中的抽取状态，使下一次 ensure 从持久化状态重新开始。"""
        with self._lock:
            self._states.pop(project_id, None)
