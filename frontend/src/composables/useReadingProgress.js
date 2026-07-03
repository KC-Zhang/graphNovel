/**
 * 阅读进度追踪
 * 记录（按书 projectId 存于 localStorage）：
 * - readEpisodes: 已读章节索引
 * - seenEdges: 已查看的关系 id（节点已读状态由其关系派生，不单独记录）
 * - episodeRanges: 每章真正浏览过的归一化竖向区间（用于覆盖率/进度条）
 * - revealMax / viewEpisode: 阅读位置（用于回到上次进度）
 *
 * 说明：集合使用 ref(new Set())，变更时重新赋值一个新 Set 以触发 Vue 响应式；
 * episodeRanges 使用普通对象 ref，变更时重新赋值一个新对象以触发响应式。
 */
import { ref, watch } from 'vue'
import { addInterval, coverage, FULL_READ_COVERAGE } from '../utils/readProgress'

const STORAGE_PREFIX = 'bookmiro:progress:'

const readEpisodes = ref(new Set())
const seenEdges = ref(new Set())
const episodeRanges = ref({})
const revealMax = ref(0)
const viewEpisode = ref(0)

let currentProjectId = null
let saveTimer = null

const storageKey = (id) => `${STORAGE_PREFIX}${id}`

const persist = () => {
  if (!currentProjectId) return
  const payload = {
    readEpisodes: [...readEpisodes.value],
    seenEdges: [...seenEdges.value],
    episodeRanges: episodeRanges.value,
    revealMax: revealMax.value,
    viewEpisode: viewEpisode.value,
  }
  try {
    localStorage.setItem(storageKey(currentProjectId), JSON.stringify(payload))
  } catch (e) {
    // localStorage 不可用时静默忽略
  }
}

const schedulePersist = () => {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(persist, 300)
}

// 监听所有进度变化，自动保存
watch([readEpisodes, seenEdges, episodeRanges, revealMax, viewEpisode], schedulePersist, { deep: false })

export function useReadingProgress() {
  const load = (projectId) => {
    currentProjectId = projectId
    let data = null
    try {
      const raw = localStorage.getItem(storageKey(projectId))
      if (raw) data = JSON.parse(raw)
    } catch (e) {
      data = null
    }
    readEpisodes.value = new Set(data?.readEpisodes || [])
    seenEdges.value = new Set(data?.seenEdges || [])
    episodeRanges.value = data?.episodeRanges && typeof data.episodeRanges === 'object' ? { ...data.episodeRanges } : {}
    revealMax.value = data?.revealMax || 0
    viewEpisode.value = data?.viewEpisode || 0
  }

  const clear = (projectId) => {
    const id = projectId || currentProjectId
    if (id) {
      try { localStorage.removeItem(storageKey(id)) } catch (e) { /* ignore */ }
    }
    readEpisodes.value = new Set()
    seenEdges.value = new Set()
    episodeRanges.value = {}
    revealMax.value = 0
    viewEpisode.value = 0
  }

  const _toggle = (setRef, key, val) => {
    const next = new Set(setRef.value)
    const shouldAdd = val === undefined ? !next.has(key) : val
    if (shouldAdd) next.add(key)
    else next.delete(key)
    setRef.value = next
  }

  const markEpisodeRead = (i, val = true) => _toggle(readEpisodes, i, val)
  const markEdgeSeen = (id, val = true) => _toggle(seenEdges, id, val)

  const isEpisodeRead = (i) => readEpisodes.value.has(i)
  const isEdgeSeen = (id) => seenEdges.value.has(id)

  const getEpisodeRanges = (i) => episodeRanges.value[i] || []

  // 将当前视口区间并入某章覆盖集合；覆盖率达阈值时自动标记整章已读
  const addEpisodeRange = (i, interval) => {
    const merged = addInterval(episodeRanges.value[i], interval)
    episodeRanges.value = { ...episodeRanges.value, [i]: merged }
    if (coverage(merged) >= FULL_READ_COVERAGE) markEpisodeRead(i, true)
  }

  const episodeCoverage = (i) => coverage(episodeRanges.value[i])

  return {
    readEpisodes,
    seenEdges,
    episodeRanges,
    revealMax,
    viewEpisode,
    load,
    clear,
    markEpisodeRead,
    markEdgeSeen,
    isEpisodeRead,
    isEdgeSeen,
    getEpisodeRanges,
    addEpisodeRange,
    episodeCoverage,
  }
}
