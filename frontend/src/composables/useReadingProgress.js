/**
 * 阅读进度追踪
 * 记录（按书 projectId 存于 localStorage）：
 * - readEpisodes: 已读章节索引
 * - seenNodes / seenEdges: 已查看的节点 / 关系 id
 * - revealMax / viewEpisode: 阅读位置（用于回到上次进度）
 *
 * 说明：集合使用 ref(new Set())，变更时重新赋值一个新 Set 以触发 Vue 响应式。
 */
import { ref, watch } from 'vue'

const STORAGE_PREFIX = 'bookmiro:progress:'

const readEpisodes = ref(new Set())
const seenNodes = ref(new Set())
const seenEdges = ref(new Set())
const revealMax = ref(0)
const viewEpisode = ref(0)

let currentProjectId = null
let saveTimer = null

const storageKey = (id) => `${STORAGE_PREFIX}${id}`

const persist = () => {
  if (!currentProjectId) return
  const payload = {
    readEpisodes: [...readEpisodes.value],
    seenNodes: [...seenNodes.value],
    seenEdges: [...seenEdges.value],
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
watch([readEpisodes, seenNodes, seenEdges, revealMax, viewEpisode], schedulePersist, { deep: false })

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
    seenNodes.value = new Set(data?.seenNodes || [])
    seenEdges.value = new Set(data?.seenEdges || [])
    revealMax.value = data?.revealMax || 0
    viewEpisode.value = data?.viewEpisode || 0
  }

  const clear = (projectId) => {
    const id = projectId || currentProjectId
    if (id) {
      try { localStorage.removeItem(storageKey(id)) } catch (e) { /* ignore */ }
    }
    readEpisodes.value = new Set()
    seenNodes.value = new Set()
    seenEdges.value = new Set()
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
  const markNodeSeen = (id, val = true) => _toggle(seenNodes, id, val)
  const markEdgeSeen = (id, val = true) => _toggle(seenEdges, id, val)

  const isEpisodeRead = (i) => readEpisodes.value.has(i)
  const isNodeSeen = (id) => seenNodes.value.has(id)
  const isEdgeSeen = (id) => seenEdges.value.has(id)

  return {
    readEpisodes,
    seenNodes,
    seenEdges,
    revealMax,
    viewEpisode,
    load,
    clear,
    markEpisodeRead,
    markNodeSeen,
    markEdgeSeen,
    isEpisodeRead,
    isNodeSeen,
    isEdgeSeen,
  }
}
