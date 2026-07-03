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

    def __init__(self, upto: int, failed: Optional[set] = None):
        self.target: int = upto          # 期望抽取到的章节索引
        self.upto: int = upto            # 已抽取到的章节索引（-1 表示还没开始）
        self.running: bool = False
        self.error: Optional[str] = None
        # 完全抽取失败、待重试的章节索引集合（如 LLM 故障恢复后自动重跑）
        self.failed: set = set(failed or ())
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
                persisted_failed = project.failed_episodes if project else []
                state = _ProjectState(upto=persisted, failed=persisted_failed)
                self._states[project_id] = state

            if upto > state.target:
                state.target = upto

            # 有失败章节待重试，或还有正常进度要推进时，都需要唤起 worker。
            # 只重试已进入阅读范围（<= target）的失败章节，避免超前抽取。
            has_pending_retry = any(i <= state.target for i in state.failed)
            if not state.running and (state.upto < state.target or has_pending_retry):
                state.running = True
                if not has_pending_retry:
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
        # 每次 worker 运行内，每个章节最多尝试一次，避免对持续失败的章节死循环。
        attempted_this_run: set = set()
        try:
            extractor = GraphExtractor()
            extractor.load_graph(ProjectManager.get_graph(project_id))

            project = ProjectManager.get_project(project_id)
            if project:
                project.status = ProjectStatus.GRAPH_BUILDING
                ProjectManager.save_project(project)

            while True:
                with self._lock:
                    state = self._states.get(project_id)
                    if not state:
                        break
                    next_idx, is_forward = self._pick_next(state, len(episodes), attempted_this_run)
                    if next_idx is None:
                        # 没有可推进的正常章节，也没有可重试的失败章节
                        if state.upto < state.target and state.upto + 1 >= len(episodes):
                            state.upto = len(episodes) - 1
                        state.running = False
                        break

                attempted_this_run.add(next_idx)
                label = "重试" if not is_forward else "抽取"
                logger.info(f"[{project_id}] {label}章节 {next_idx + 1}/{len(episodes)}")
                result = extractor.extract_episode(episodes[next_idx], language)
                episode_failed = (
                    result["total_chunks"] > 0 and result["failed_chunks"] == result["total_chunks"]
                )

                # 更新内存状态：成功则从失败集合移除，失败则加入待重试集合。
                # 前进步无论成败都推进 upto，保证后续章节仍会被抽取。
                with self._lock:
                    state = self._states.get(project_id)
                    if state:
                        if is_forward:
                            state.upto = max(state.upto, next_idx)
                        if episode_failed:
                            state.failed.add(next_idx)
                            state.error = result["error"]
                        else:
                            state.failed.discard(next_idx)
                            if not state.failed:
                                state.error = None
                        failed_snapshot = sorted(state.failed)
                        error_snapshot = state.error
                        upto_snapshot = state.upto

                # 落盘（图谱 + 项目元数据）
                ProjectManager.save_graph(project_id, extractor.to_graph())
                fresh = ProjectManager.get_project(project_id)
                if fresh:
                    fresh.extracted_upto = upto_snapshot
                    fresh.failed_episodes = failed_snapshot
                    fresh.error = error_snapshot
                    if upto_snapshot >= len(episodes) - 1 and not failed_snapshot:
                        fresh.status = ProjectStatus.GRAPH_COMPLETED
                    ProjectManager.save_project(fresh)

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

    @staticmethod
    def _pick_next(state: "_ProjectState", total: int, attempted_this_run: set):
        """
        选择 worker 下一个要处理的章节。

        返回 (index, is_forward)；无可处理项时返回 (None, False)。
        - 优先推进正常阅读进度（is_forward=True）
        - 其次重试已进入阅读范围（<= target）的失败章节（is_forward=False）
        - 每个章节在单次 worker 运行内只处理一次，避免死循环
        """
        fwd = state.upto + 1
        if state.upto < state.target and fwd < total and fwd not in attempted_this_run:
            return fwd, True
        for idx in sorted(state.failed):
            if idx < total and idx <= state.target and idx not in attempted_this_run:
                return idx, False
        return None, False

    def _status_locked(self, project_id: str, total: int) -> Dict[str, Any]:
        state = self._states.get(project_id)
        if state is None:
            project = ProjectManager.get_project(project_id)
            upto = project.extracted_upto if project else -1
            failed = sorted(project.failed_episodes) if project else []
            return {
                "extracted_upto": upto,
                "target": upto,
                "running": False,
                "error": project.error if project else None,
                "failed_episodes": failed,
                "total": total,
            }
        return {
            "extracted_upto": state.upto,
            "target": state.target,
            "running": state.running,
            "error": state.error,
            "failed_episodes": sorted(state.failed),
            "total": total,
        }

    def status(self, project_id: str, total: int) -> Dict[str, Any]:
        with self._lock:
            return self._status_locked(project_id, total)

    def reset(self, project_id: str) -> None:
        """清除内存中的抽取状态，使下一次 ensure 从持久化状态重新开始。"""
        with self._lock:
            self._states.pop(project_id, None)
