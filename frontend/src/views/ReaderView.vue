<template>
  <div class="reader">
    <!-- 顶部栏 -->
    <nav class="reader-nav">
      <div class="nav-left">
        <button class="back-btn" @click="goHome">← {{ $t('reader.backHome') }}</button>
        <span class="book-title">{{ bookName || $t('reader.untitled') }}</span>
        <span v-if="language" class="lang-badge">{{ language }}</span>
      </div>
      <div class="nav-right">
        <button v-if="phase === 'ready'" class="chapters-btn" @click="showChapters = !showChapters">
          ☰ {{ $t('reader.chapters') }}
        </button>
        <LanguageSwitcher />
      </div>
    </nav>

    <!-- 章节目录抽屉 -->
    <div v-if="showChapters" class="chapters-overlay" @click.self="showChapters = false">
      <div class="chapters-drawer">
        <div class="chapters-head">
          <span>{{ $t('reader.chapters') }}</span>
          <span class="chapters-progress">{{ $t('reader.chaptersRead', { read: readCount, total: episodes.length }) }}</span>
          <button class="detail-close" @click="showChapters = false">×</button>
        </div>
        <div class="chapters-list">
          <div
            v-for="(ep, i) in episodes"
            :key="i"
            class="chapter-item"
            :class="{ current: i === viewEpisode, read: isEpisodeRead(i) }"
            @click="jumpToChapter(i)"
          >
            <span class="chapter-check">{{ isEpisodeRead(i) ? '✓' : '' }}</span>
            <span class="chapter-title">{{ ep.title }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 启动/上传状态 -->
    <div v-if="phase !== 'ready'" class="status-screen">
      <div class="status-card">
        <div v-if="phase !== 'error'" class="loading-spinner"></div>
        <div class="status-message">{{ statusMessage }}</div>
        <div v-if="phase === 'error'" class="error-box">
          <div class="error-text">{{ errorText }}</div>
          <button class="retry-btn" @click="retry">{{ $t('reader.retry') }}</button>
        </div>
      </div>
    </div>

    <!-- 阅读主界面 -->
    <div v-else class="reader-body">
      <!-- 左：书籍面板 -->
      <div class="book-pane" ref="bookPane">
        <div class="episode-head">
          <div class="episode-title">{{ currentEpisodeTitle }}</div>
          <div class="episode-head-right">
            <button
              class="read-toggle"
              :class="{ read: isEpisodeRead(viewEpisode) }"
              @click="toggleChapterRead"
            >
              {{ isEpisodeRead(viewEpisode) ? '✓ ' + $t('reader.markRead') : $t('reader.markRead') }}
            </button>
            <div class="episode-counter">{{ viewEpisode + 1 }} / {{ episodes.length }}</div>
          </div>
        </div>

        <div class="book-text" ref="bookText" @scroll="onBookScroll">
          <p
            v-for="(para, i) in renderedParagraphs"
            :key="i"
            class="para"
          >
            <template v-for="(seg, j) in para" :key="j">
              <span
                v-if="seg.link"
                class="text-link"
                :class="{ 'quote-mark': seg.mark, 'link-edge': seg.link.type === 'edge' }"
                :title="linkTitle(seg.link)"
                @click="goToGraph(seg.link)"
              >{{ seg.text }}</span>
              <mark v-else-if="seg.mark" class="quote-mark">{{ seg.text }}</mark>
              <span v-else>{{ seg.text }}</span>
            </template>
          </p>
        </div>

        <!-- 章节导航 -->
        <div class="episode-nav">
          <button class="nav-arrow" :disabled="viewEpisode <= 0" @click="prevEpisode">‹ {{ $t('reader.prev') }}</button>
          <input
            class="episode-scrubber"
            type="range"
            min="0"
            :max="Math.max(episodes.length - 1, 0)"
            :value="viewEpisode"
            @input="onScrub"
          />
          <button class="nav-arrow" :disabled="viewEpisode >= episodes.length - 1" @click="nextEpisode">{{ $t('reader.next') }} ›</button>
        </div>
        <div class="reveal-note">
          {{ $t('reader.revealNote', { n: revealMax + 1 }) }} · {{ $t('reader.chaptersRead', { read: readCount, total: episodes.length }) }}
        </div>
      </div>

      <!-- 右：图谱面板 -->
      <div class="graph-pane">
        <GraphPanel
          :graph-data="graphData"
          :current-episode="revealMax"
          :episodes="episodes"
          :loading="graphLoading"
          :seen-nodes="seenNodesArr"
          :seen-edges="seenEdgesArr"
          :select-request="selectRequest"
          @refresh="loadGraph"
          @jump="onJump"
          @seen-node="id => markNodeSeen(id, true)"
          @seen-edge="id => markEdgeSeen(id, true)"
          @set-node-seen="({ id, value }) => markNodeSeen(id, value)"
          @set-edge-seen="({ id, value }) => markEdgeSeen(id, value)"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import GraphPanel from '../components/GraphPanel.vue'
import {
  uploadBook, ensureExtraction, getExtractStatus, getGraphData, getEpisode, getBook
} from '../api/book'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import { useReadingProgress } from '../composables/useReadingProgress'

const PREFETCH = 2

const props = defineProps({ projectId: String })
const router = useRouter()
const { t } = useI18n()

// 阅读进度（localStorage 持久化）
const {
  readEpisodes, seenNodes, seenEdges, revealMax, viewEpisode,
  load: loadProgress, markEpisodeRead, markNodeSeen, markEdgeSeen, isEpisodeRead
} = useReadingProgress()

const seenNodesArr = computed(() => [...seenNodes.value])
const seenEdgesArr = computed(() => [...seenEdges.value])
const readCount = computed(() => readEpisodes.value.size)
const showChapters = ref(false)

// 反向链接：请求图谱选中并居中某节点/关系
const selectRequest = ref(null)
const goToGraph = (link) => {
  selectRequest.value = { type: link.type, id: link.id, nonce: Date.now() }
}
const linkTitle = (link) => `${t('reader.viewInGraph')}: ${link.name}`

const phase = ref('loading') // loading | uploading | ready | error
const statusMessage = ref('')
const errorText = ref('')

const projectId = ref(props.projectId)
const bookName = ref('')
const language = ref('')
const episodes = ref([])

const graphData = ref({ nodes: [], edges: [] })

const episodeTextCache = new Map()
const currentText = ref('')
const highlightQuote = ref('')

// 增量抽取状态
const extractedUpto = ref(-1)
const extractRunning = ref(false)
// 正在读的章节图谱还没抽到时，显示"构建中"
const graphLoading = computed(() => revealMax.value > extractedUpto.value)

const currentEpisodeTitle = computed(() => {
  const ep = episodes.value[viewEpisode.value]
  return ep ? ep.title : ''
})

// 构建规范化文本并保留到原文位置的映射。
// stripPunct=true 时进一步忽略标点，仅保留字母/数字/文字，用于更宽松的匹配。
const buildNormalized = (text, stripPunct = false) => {
  let norm = ''
  const map = []
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (/\s/.test(ch)) continue
    if (stripPunct && !/[\p{L}\p{N}]/u.test(ch)) continue
    norm += ch
    map.push(i)
  }
  return { norm, map }
}

// 清理引用：去掉首尾引号/括号/省略号，便于匹配
const cleanQuote = (q) => {
  return (q || '')
    .trim()
    .replace(/^[\s"'“”‘’「」『』（(\[【]+/, '')
    .replace(/[\s"'“”‘’「」『』）)\]】]+$/, '')
    .replace(/^(?:\.{3,}|…+)/, '')
    .replace(/(?:\.{3,}|…+)$/, '')
    .trim()
}

// 在原文中定位引用，返回 {start, end}
// 依次尝试：忽略空白 -> 忽略空白+标点；每次先整体匹配，再用前缀兜底。
const findQuoteRange = (text, quote) => {
  const q = cleanQuote(quote)
  if (!text || !q) return null

  for (const stripPunct of [false, true]) {
    const { norm, map } = buildNormalized(text, stripPunct)
    const nq = buildNormalized(q, stripPunct).norm
    if (!nq) continue

    let idx = norm.indexOf(nq)
    if (idx !== -1) {
      return { start: map[idx], end: map[idx + nq.length - 1] + 1 }
    }

    // 兜底：匹配引用前缀（应对 LLM 引用非完全逐字的情况）
    const probeMax = Math.min(nq.length, 16)
    for (let len = probeMax; len >= 6; len -= 2) {
      const probe = nq.slice(0, len)
      idx = norm.indexOf(probe)
      if (idx !== -1) {
        return { start: map[idx], end: map[idx + len - 1] + 1 }
      }
    }
  }
  return null
}

const highlightRange = computed(() => {
  if (!highlightQuote.value) return null
  return findQuoteRange(currentText.value || '', highlightQuote.value)
})

// 反向链接：本章正文中与（已揭示的）节点/关系相关联的片段
const episodeLinks = computed(() => {
  const text = currentText.value || ''
  if (!text) return []
  const ep = viewEpisode.value
  const maxReveal = revealMax.value
  const g = graphData.value || {}
  const links = []
  const pushMentions = (item, type, name) => {
    if ((item.first_episode ?? 0) > maxReveal) return
    for (const m of (item.mentions || [])) {
      if (m.episode !== ep) continue
      const r = findQuoteRange(text, m.quote)
      if (r) links.push({ start: r.start, end: r.end, type, id: item.id, name })
    }
  }
  ;(g.nodes || []).forEach(n => pushMentions(n, 'node', n.name || ''))
  ;(g.edges || []).forEach(e => pushMentions(e, 'edge', e.label || ''))
  // 重叠时优先节点
  links.sort((a, b) => a.start - b.start || (a.type === b.type ? 0 : (a.type === 'node' ? -1 : 1)))
  return links
})

// 按段落渲染，叠加：跳转高亮(mark) + 反向链接(link)
const renderedParagraphs = computed(() => {
  const text = currentText.value || ''
  const range = highlightRange.value
  const links = episodeLinks.value
  const paras = []
  let offset = 0
  for (const line of text.split('\n')) {
    const pStart = offset
    const pEnd = offset + line.length
    offset = pEnd + 1 // 计入换行符
    if (line.trim().length === 0) continue
    const len = line.length

    // 本段内的链接区间（转为局部坐标）
    const local = []
    for (const lk of links) {
      if (lk.end > pStart && lk.start < pEnd) {
        local.push({ s: Math.max(lk.start, pStart) - pStart, e: Math.min(lk.end, pEnd) - pStart, link: lk })
      }
    }
    let hs = -1, he = -1
    if (range && range.end > pStart && range.start < pEnd) {
      hs = Math.max(range.start, pStart) - pStart
      he = Math.min(range.end, pEnd) - pStart
    }

    if (local.length === 0 && hs < 0) {
      paras.push([{ text: line, mark: false, link: null }])
      continue
    }

    // 生成切分边界
    const bounds = new Set([0, len])
    local.forEach(l => { bounds.add(l.s); bounds.add(l.e) })
    if (hs >= 0) { bounds.add(hs); bounds.add(he) }
    const pts = [...bounds].filter(p => p >= 0 && p <= len).sort((a, b) => a - b)

    const segs = []
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1]
      if (b <= a) continue
      const txt = line.slice(a, b)
      if (!txt) continue
      const mark = hs >= 0 && a >= hs && b <= he
      const cover = local.find(l => l.s <= a && l.e >= b)
      segs.push({ text: txt, mark, link: cover ? cover.link : null })
    }
    paras.push(segs)
  }
  return paras
})

// 滚动到高亮处并短暂闪烁提示
const flashTimers = []
const scrollToHighlight = () => {
  nextTick(() => {
    const el = document.querySelector('.book-text .quote-mark')
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.remove('flash')
    // 触发重排以重启动画
    void el.offsetWidth
    el.classList.add('flash')
    const timer = setTimeout(() => el.classList.remove('flash'), 1600)
    flashTimers.push(timer)
  })
}

const goHome = () => router.push({ name: 'Home' })

// ---------- 章节文本加载 ----------
const loadEpisodeText = async (idx) => {
  if (episodeTextCache.has(idx)) {
    currentText.value = episodeTextCache.get(idx)
    return
  }
  try {
    const res = await getEpisode(projectId.value, idx)
    if (res.success) {
      const text = res.data.text || ''
      episodeTextCache.set(idx, text)
      currentText.value = text
    }
  } catch (e) {
    currentText.value = ''
  }
}

const setViewEpisode = async (idx) => {
  idx = Math.max(0, Math.min(idx, episodes.value.length - 1))
  viewEpisode.value = idx
  if (idx > revealMax.value) revealMax.value = idx
  highlightQuote.value = ''
  await loadEpisodeText(idx)
  scrollBookTop()
  checkAutoRead()
  ensureAhead()
}

const scrollBookTop = () => {
  nextTick(() => {
    const el = document.querySelector('.book-text')
    if (el) el.scrollTop = 0
  })
}

// 章节较短（无需滚动）时，读到即视为已读
const checkAutoRead = () => {
  nextTick(() => {
    const el = document.querySelector('.book-text')
    if (el && el.scrollHeight <= el.clientHeight + 8) {
      markEpisodeRead(viewEpisode.value, true)
    }
  })
}

// 滚动到章节底部附近即自动标记为已读
const onBookScroll = (e) => {
  const el = e.target
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
    markEpisodeRead(viewEpisode.value, true)
  }
}

const toggleChapterRead = () => {
  markEpisodeRead(viewEpisode.value, !isEpisodeRead(viewEpisode.value))
}

const jumpToChapter = (i) => {
  showChapters.value = false
  setViewEpisode(i)
}

const prevEpisode = () => setViewEpisode(viewEpisode.value - 1)
const nextEpisode = () => setViewEpisode(viewEpisode.value + 1)
const onScrub = (e) => setViewEpisode(parseInt(e.target.value, 10))

// 从图谱跳转到原文
const onJump = async ({ episode, quote }) => {
  if (episode !== viewEpisode.value) {
    viewEpisode.value = Math.max(0, Math.min(episode, episodes.value.length - 1))
    if (viewEpisode.value > revealMax.value) revealMax.value = viewEpisode.value
    await loadEpisodeText(viewEpisode.value)
  }
  // 先清空再设置，保证即使重复点击同一引用也会重新触发滚动/高亮
  highlightQuote.value = ''
  await nextTick()
  highlightQuote.value = quote
  scrollToHighlight()
  ensureAhead()
}

// ---------- 图谱加载 ----------
const loadGraph = async () => {
  try {
    const res = await getGraphData(projectId.value)
    if (res.success) {
      graphData.value = res.data || { nodes: [], edges: [] }
    }
  } catch (e) {
    // ignore
  }
}

// ---------- 按需增量抽取 + 轮询 ----------
let pollTimer = null
let polling = false
let lastLoadedUpto = -1

const pollStatus = async () => {
  try {
    const res = await getExtractStatus(projectId.value)
    if (res.success) {
      const s = res.data
      extractedUpto.value = s.extracted_upto
      extractRunning.value = s.running
      if (s.extracted_upto > lastLoadedUpto) {
        lastLoadedUpto = s.extracted_upto
        await loadGraph()
      }
      if (s.running || revealMax.value > s.extracted_upto) {
        pollTimer = setTimeout(pollStatus, 1500)
        return
      }
    }
  } catch (e) {
    pollTimer = setTimeout(pollStatus, 2500)
    return
  }
  polling = false
}

const startPolling = () => {
  if (polling) return
  polling = true
  pollStatus()
}

// 确保抽取推进到"当前阅读位置 + 预取"的章节
const ensureAhead = async () => {
  if (!projectId.value || projectId.value === 'new' || !episodes.value.length) return
  const target = Math.min(viewEpisode.value + PREFETCH, episodes.value.length - 1)
  try {
    const res = await ensureExtraction(projectId.value, target)
    if (res.success) {
      extractedUpto.value = res.data.extracted_upto
      extractRunning.value = res.data.running
    }
  } catch (e) {
    // ignore transient errors
  }
  startPolling()
}

// ---------- 初始化 ----------
const applyBookMeta = (data) => {
  bookName.value = data.name || ''
  language.value = data.language || ''
  episodes.value = data.episodes || []
}

const initExisting = async () => {
  phase.value = 'loading'
  statusMessage.value = t('reader.loading')
  try {
    const res = await getBook(projectId.value)
    if (!res.success) {
      errorText.value = res.error || 'Book not found'
      phase.value = 'error'
      return
    }
    applyBookMeta(res.data)
    loadProgress(projectId.value)  // 恢复已读进度与阅读位置
    extractedUpto.value = typeof res.data.extracted_upto === 'number' ? res.data.extracted_upto : -1
    lastLoadedUpto = extractedUpto.value

    // 已抽取的部分立即加载
    if (extractedUpto.value >= 0) await loadGraph()

    // 立即进入阅读；回到上次阅读位置
    phase.value = 'ready'
    if (episodes.value.length) await setViewEpisode(viewEpisode.value || 0)
  } catch (e) {
    errorText.value = e.message || 'Failed to load book'
    phase.value = 'error'
  }
}

const initNew = async () => {
  const pending = getPendingUpload()
  if (!pending.isPending || !pending.files.length) {
    // 没有待上传数据，回首页
    goHome()
    return
  }
  phase.value = 'uploading'
  statusMessage.value = t('reader.uploading')
  const formData = new FormData()
  pending.files.forEach(f => formData.append('files', f))
  if (pending.bookName) formData.append('book_name', pending.bookName)

  try {
    const res = await uploadBook(formData)
    if (!res.success) {
      errorText.value = res.error || 'Upload failed'
      phase.value = 'error'
      return
    }
    clearPendingUpload()
    projectId.value = res.data.project_id
    applyBookMeta(res.data)
    loadProgress(projectId.value)  // 新书：初始化空进度并绑定 projectId
    extractedUpto.value = -1
    lastLoadedUpto = -1
    // 更新 URL 以便刷新/分享
    router.replace({ name: 'Reader', params: { projectId: projectId.value } })
    // 立即进入阅读；图谱按需在后台构建
    phase.value = 'ready'
    if (episodes.value.length) await setViewEpisode(0)
  } catch (e) {
    errorText.value = e.message || 'Upload failed'
    phase.value = 'error'
  }
}

const retry = () => {
  errorText.value = ''
  if (projectId.value && projectId.value !== 'new') {
    initExisting()
  } else {
    initNew()
  }
}

onMounted(() => {
  if (props.projectId === 'new') {
    initNew()
  } else {
    initExisting()
  }
})

onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
  flashTimers.forEach(clearTimeout)
})
</script>

<style scoped>
.reader { display: flex; flex-direction: column; height: 100vh; background: #fff; }

.reader-nav {
  height: 56px; flex-shrink: 0;
  background: #000; color: #fff;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px;
}
.nav-left { display: flex; align-items: center; gap: 16px; }
.back-btn {
  background: transparent; border: 1px solid rgba(255,255,255,0.3); color: #fff;
  padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;
}
.back-btn:hover { background: rgba(255,255,255,0.1); }
.nav-right { display: flex; align-items: center; gap: 12px; }
.book-title { font-weight: 600; font-size: 15px; }
.lang-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: #FF4500; color: #fff; font-weight: 600;
}
.chapters-btn {
  background: transparent; border: 1px solid rgba(255,255,255,0.3); color: #fff;
  padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;
}
.chapters-btn:hover { background: rgba(255,255,255,0.1); }

/* 章节目录抽屉 */
.chapters-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.35); z-index: 50;
  display: flex; justify-content: flex-end;
}
.chapters-drawer {
  width: 340px; max-width: 85vw; height: 100%; background: #fff;
  display: flex; flex-direction: column; box-shadow: -4px 0 24px rgba(0,0,0,0.15);
}
.chapters-head {
  display: flex; align-items: center; gap: 10px;
  padding: 16px 20px; border-bottom: 1px solid #eee; font-weight: 600; color: #111;
}
.chapters-progress { font-size: 12px; color: #FF4500; font-weight: 600; margin-left: auto; }
.chapters-list { flex: 1; overflow-y: auto; padding: 8px; }
.chapter-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border-radius: 6px; cursor: pointer; color: #333; font-size: 14px;
}
.chapter-item:hover { background: #f5f5f5; }
.chapter-item.current { background: #FFF3E0; font-weight: 600; }
.chapter-item.read { color: #888; }
.chapter-check { width: 16px; color: #FF4500; font-weight: 700; flex-shrink: 0; }
.chapter-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 状态屏 */
.status-screen { flex: 1; display: flex; align-items: center; justify-content: center; }
.status-card {
  width: 420px; max-width: 90vw; text-align: center;
  padding: 40px; border: 1px solid #eee; border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.05);
}
.loading-spinner {
  width: 44px; height: 44px; border: 3px solid #eee; border-top-color: #FF4500;
  border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 20px;
}
@keyframes spin { to { transform: rotate(360deg); } }
.status-message { font-size: 14px; color: #444; margin-bottom: 16px; min-height: 20px; }
.progress-bar { height: 8px; background: #eee; border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #FF4500, #FF8C42); transition: width 0.4s; }
.progress-sub { font-size: 12px; color: #999; margin-top: 10px; }
.error-box { margin-top: 16px; }
.error-text { color: #C5283D; font-size: 13px; margin-bottom: 12px; word-break: break-word; }
.retry-btn {
  background: #000; color: #fff; border: none; padding: 10px 20px;
  border-radius: 6px; cursor: pointer; font-weight: 600;
}
.retry-btn:hover { background: #FF4500; }

/* 阅读主体 */
.reader-body { flex: 1; display: flex; min-height: 0; }
.book-pane {
  width: 46%; min-width: 340px; display: flex; flex-direction: column;
  border-right: 1px solid #eee; min-height: 0;
}
.graph-pane { flex: 1; min-width: 0; }

.episode-head {
  display: flex; align-items: baseline; justify-content: space-between;
  padding: 18px 32px 10px; flex-shrink: 0; gap: 12px;
}
.episode-title { font-size: 20px; font-weight: 700; color: #111; }
.episode-head-right { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.episode-counter { font-size: 12px; color: #999; font-family: monospace; }
.read-toggle {
  border: 1px solid #ddd; background: #fff; color: #666;
  border-radius: 14px; padding: 4px 12px; font-size: 12px; font-weight: 600;
  cursor: pointer; white-space: nowrap; transition: all 0.15s;
}
.read-toggle:hover { border-color: #FF4500; color: #FF4500; }
.read-toggle.read { background: #FFF3E0; color: #FF4500; border-color: #FFCC80; }

/* detail-close 复用于抽屉 */
.detail-close {
  background: none; border: none; font-size: 20px; cursor: pointer;
  color: #999; line-height: 1; padding: 0;
}
.detail-close:hover { color: #333; }

.book-text {
  flex: 1; overflow-y: auto; padding: 8px 32px 24px;
  line-height: 1.9; font-size: 16px; color: #2b2b2b;
  font-family: 'Noto Serif SC', 'Georgia', serif;
}
.para { margin: 0 0 1.1em; text-align: justify; }
.text-link {
  border-bottom: 1px dotted #7B2D8E; cursor: pointer; transition: background 0.15s;
}
.text-link:hover { background: rgba(123,45,142,0.12); }
.text-link.link-edge { border-bottom-color: #E91E63; }
.text-link.link-edge:hover { background: rgba(233,30,99,0.12); }
.quote-mark { background: #FFECB3; padding: 1px 2px; border-radius: 3px; box-shadow: 0 0 0 2px #FFECB3; transition: background 0.3s; }
.quote-mark.flash { animation: quoteFlash 1.6s ease-out; }
@keyframes quoteFlash {
  0% { background: #FFC107; box-shadow: 0 0 0 3px #FFC107; }
  30% { background: #FFC107; box-shadow: 0 0 0 3px #FFC107; }
  100% { background: #FFECB3; box-shadow: 0 0 0 2px #FFECB3; }
}

.episode-nav {
  display: flex; align-items: center; gap: 16px;
  padding: 12px 32px; border-top: 1px solid #eee; flex-shrink: 0;
}
.nav-arrow {
  background: #fff; border: 1px solid #ddd; border-radius: 6px;
  padding: 8px 14px; cursor: pointer; font-size: 13px; color: #333; white-space: nowrap;
}
.nav-arrow:hover:not(:disabled) { background: #f5f5f5; border-color: #bbb; }
.nav-arrow:disabled { opacity: 0.4; cursor: not-allowed; }
.episode-scrubber { flex: 1; accent-color: #FF4500; cursor: pointer; }
.reveal-note {
  font-size: 11px; color: #aaa; text-align: center; padding: 0 32px 12px; flex-shrink: 0;
}
</style>
