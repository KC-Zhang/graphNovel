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
        <div v-if="phase === 'ready'" class="reader-search" ref="searchBox">
          <div class="search-input-wrap" :class="{ active: searchOpen || searchQuery }">
            <span class="search-icon">⌕</span>
            <input
              v-model="searchQuery"
              class="search-input"
              type="search"
              :placeholder="$t('reader.searchPlaceholder')"
              @focus="openSearch"
              @keydown.enter.prevent="onSearchEnter"
              @keydown.esc.prevent="clearSearch"
            />
            <button
              v-if="searchQuery"
              class="search-clear"
              :title="$t('reader.searchClear')"
              @click="clearSearch"
            >
              ×
            </button>
          </div>
          <div v-if="searchQuery" class="search-controls">
            <button class="search-nav-btn" :disabled="!searchResults.length" :title="$t('reader.searchPrev')" @click="moveSearch(-1)">‹</button>
            <span class="search-count">
              {{ searchLoading ? $t('reader.searching') : $t('reader.searchCount', { count: searchResults.length }) }}
            </span>
            <button class="search-nav-btn" :disabled="!searchResults.length" :title="$t('reader.searchNext')" @click="moveSearch(1)">›</button>
          </div>
          <div v-if="searchOpen && searchQuery" class="search-results">
            <div v-if="searchLoading && !searchResults.length" class="search-empty">{{ $t('reader.searching') }}</div>
            <div v-else-if="!searchLoading && !searchResults.length" class="search-empty">{{ $t('reader.searchNoResults') }}</div>
            <button
              v-for="(result, i) in searchResults"
              :key="result.id"
              class="search-result"
              :class="[result.kind, { active: i === activeSearchIndex }]"
              @mousedown.prevent="selectSearchResult(result, i)"
            >
              <span class="search-result-kind">{{ searchKindLabel(result.kind) }}</span>
              <span class="search-result-main">
                <span class="search-result-title">{{ result.title }}</span>
                <span class="search-result-subtitle">{{ result.subtitle }}</span>
                <span v-if="result.snippet" class="search-result-snippet">{{ result.snippet }}</span>
              </span>
            </button>
          </div>
        </div>
        <LanguageSwitcher />
      </div>
    </nav>

    <!-- 章节目录抽屉 -->
    <div v-if="showChapters" class="chapters-overlay" @click.self="showChapters = false">
      <div class="chapters-drawer">
        <div class="chapters-head">
          <span>{{ episodeUnitLabel }}</span>
          <span class="chapters-progress">{{ episodeProgressLabel }}</span>
          <button class="detail-close" @click="showChapters = false">×</button>
        </div>
        <div class="chapters-list">
          <div
            v-for="(ep, i) in episodes"
            :key="i"
            class="chapter-item"
            :class="[chapterState(i), { current: i === viewEpisode }]"
            @click="jumpToChapter(i)"
          >
            <span class="chapter-check">{{ chapterState(i) === 'read' ? '✓' : (chapterState(i) === 'partial' ? '◐' : '') }}</span>
            <span class="chapter-title">{{ ep.title }}</span>
            <span class="chapter-pct">{{ chapterState(i) === 'read' ? '' : (chapterState(i) === 'partial' ? chapterPercent(i) + '%' : '') }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 启动/上传状态 -->
    <div v-if="phase !== 'ready'" class="status-screen">
      <div class="status-card" :class="{ wide: phase === 'review' }">
        <template v-if="phase === 'review'">
          <div class="review-head">
            <div class="review-title">{{ $t('reader.reviewStructure') }}</div>
            <div class="review-desc">{{ reviewDescription }}</div>
          </div>
          <div v-if="sourceFormat === 'pdf'" class="reading-mode-panel">
            <div class="reading-mode-heading">
              <span>{{ $t('reader.pdfReadingMode') }}</span>
              <span v-if="documentKind !== 'uncertain'" class="detection-badge">
                {{ $t('reader.detectedAs', { type: documentKindLabel }) }}
              </span>
              <span v-else class="detection-badge uncertain">{{ $t('reader.chooseModeRequired') }}</span>
            </div>
            <div class="reading-mode-switch" role="group" :aria-label="$t('reader.pdfReadingMode')">
              <button
                type="button"
                :class="{ active: readingMode === 'chapter' }"
                :disabled="modeChanging"
                @click="changeReadingMode('chapter')"
              >{{ $t('reader.byChapter') }}</button>
              <button
                type="button"
                :class="{ active: readingMode === 'page' }"
                :disabled="modeChanging"
                @click="changeReadingMode('page')"
              >{{ $t('reader.byPage') }}</button>
            </div>
            <p class="reading-mode-help">
              {{ readingMode === 'page' ? $t('reader.pageModeHelp') : $t('reader.chapterModeHelp') }}
            </p>
            <p v-if="['unavailable', 'unreliable'].includes(chapterDetectionStatus) && readingMode === 'chapter'" class="mode-warning">
              {{ $t('reader.chapterDetectionUnreliable') }}
            </p>
          </div>
          <div class="chapter-preview-list">
            <div v-if="modeChanging" class="chapter-preview-empty">{{ $t('reader.changingReadingMode') }}</div>
            <div v-else-if="!episodes.length" class="chapter-preview-empty">{{ $t('reader.chooseModeToPreview') }}</div>
            <div v-for="ep in chapterPreviewItems" :key="ep.index" class="chapter-preview-item">
              <span class="chapter-preview-index">{{ ep.index + 1 }}</span>
              <span class="chapter-preview-title">{{ ep.title }}</span>
              <span class="chapter-preview-count">{{ ep.char_count }}</span>
            </div>
            <div v-if="episodes.length > chapterPreviewItems.length" class="chapter-preview-more">
              {{ $t('reader.episodePreviewMore', { count: episodes.length - chapterPreviewItems.length }) }}
            </div>
          </div>
          <div class="review-actions">
            <button class="retry-btn secondary" @click="goHome">{{ $t('reader.chooseFiles') }}</button>
            <button class="retry-btn" :disabled="!canConfirmReview" @click="confirmChapterReview">{{ $t('reader.continueToReader') }}</button>
          </div>
        </template>
        <template v-else>
          <div v-if="phase !== 'error' && phase !== 'expired'" class="loading-spinner"></div>
          <div class="status-message">{{ statusMessage }}</div>
          <div v-if="phase === 'error' || phase === 'expired'" class="error-box">
            <div class="error-text">{{ errorText }}</div>
            <button class="retry-btn" @click="phase === 'expired' ? goHome() : retry()">
              {{ phase === 'expired' ? $t('reader.chooseFiles') : $t('reader.retry') }}
            </button>
          </div>
        </template>
      </div>
    </div>

    <!-- 阅读主界面 -->
    <div
      v-else
      class="reader-body"
      :class="{ 'graph-maximized': graphMaximized, 'single-pane': singlePane, 'showing-graph': activePane === 'graph' }"
      ref="readerBody"
    >
      <button
        v-if="navHistory.length"
        class="floating-reader-back"
        @click="goBack"
        :title="$t('reader.back')"
        :aria-label="$t('reader.back')"
      >
        <FontAwesomeIcon :icon="faArrowLeft" />
        <span class="floating-back-label">{{ $t('reader.back') }}</span>
        <span class="floating-back-depth">{{ navHistory.length }}</span>
      </button>

      <!-- 左：书籍面板 -->
      <div v-show="showBookPane" class="book-pane" ref="bookPane" :style="bookPaneStyle">
        <div class="episode-head">
          <div class="episode-title">{{ currentEpisodeTitle }}</div>
          <div class="episode-head-right">
            <button v-if="singlePane" class="pane-action" @click="showGraphPane">{{ $t('reader.openGraph') }}</button>
            <button
              class="read-ring"
              :class="{ done: isEpisodeRead(viewEpisode) }"
              @click="toggleChapterRead"
              :title="isEpisodeRead(viewEpisode) ? $t('reader.markRead') : $t('reader.readPercent', { pct: currentReadPct })"
            >
              <svg viewBox="0 0 36 36" class="read-ring-svg">
                <circle class="read-ring-track" cx="18" cy="18" r="15.5" />
                <circle
                  class="read-ring-fill"
                  cx="18" cy="18" r="15.5"
                  :stroke-dasharray="RING_CIRC"
                  :stroke-dashoffset="readRingOffset"
                />
              </svg>
              <span class="read-ring-text">{{ isEpisodeRead(viewEpisode) ? '✓' : currentReadPct }}</span>
            </button>
          </div>
        </div>

        <div class="book-scroll">
          <div class="book-text" ref="bookText" @scroll="onBookScroll">
            <PdfPageView
              v-if="isPdfPageMode"
              :source-url="pdfSourceUrl"
              :page-number="currentPageNumber"
              :highlight-text="currentHighlightText"
              :links="episodeLinks"
              @link-click="goToGraph"
              @rendered="checkAutoRead"
            />
            <p
              v-else
              v-for="(para, i) in renderedParagraphs"
              :key="i"
              class="para"
              :class="{ 'reader-heading': para.heading }"
            >
              <template v-for="(seg, j) in para.segments" :key="j">
                <span
                  v-if="seg.link"
                  class="text-link"
                  :class="{
                    'quote-mark': seg.mark,
                    'link-edge': seg.link.type === 'edge',
                    'link-seen': linkSeen(seg.link),
                    'link-unseen': !linkSeen(seg.link)
                  }"
                  :data-edge-id="seg.link.type === 'edge' ? seg.link.id : null"
                  :title="linkTitle(seg.link)"
                  @click="goToGraph(seg.link)"
                >{{ seg.text }}</span>
                <mark v-else-if="seg.mark" class="quote-mark">{{ seg.text }}</mark>
                <span v-else>{{ seg.text }}</span>
              </template>
            </p>
          </div>
          <!-- 阅读进度轨：已浏览段 + 当前视口标记（可点击/拖拽滚动） -->
          <div
            class="read-rail"
            :title="$t('reader.readPercent', { pct: chapterPercent(viewEpisode) })"
            @mousedown="onRailPointerDown"
          >
            <div
              v-for="(seg, i) in railSegments"
              :key="i"
              class="read-rail-seg"
              :style="{ top: seg.top + '%', height: seg.height + '%' }"
            ></div>
            <div
              class="read-rail-view"
              :style="{ top: viewportMarker.top + '%', height: viewportMarker.height + '%' }"
            ></div>
          </div>
        </div>

        <!-- 章节导航 -->
        <div class="episode-nav">
          <button class="chapters-btn-bottom" @click="showChapters = !showChapters">
            ☰
          </button>
          <button class="nav-arrow" :disabled="viewEpisode <= 0" @click="jumpToChapter(0)" :title="$t('reader.jumpFirst')">«</button>
          <button class="nav-arrow" :disabled="viewEpisode <= 0" @click="prevEpisode" :title="$t('reader.prev')">‹</button>
          <div class="chapter-scrubber">
            <div class="chapter-scrubber-meta">
              <span class="chapter-scrubber-index">
                {{ positionLabel }}
              </span>
              <span class="chapter-scrubber-title" :title="chapterSliderTitle">
                {{ chapterSliderTitle }}
              </span>
              <span v-if="chapterSliderPercent > 0" class="chapter-scrubber-pct">
                {{ chapterSliderPercent }}%
              </span>
            </div>
            <input
              class="chapter-slider"
              type="range"
              min="1"
              :max="Math.max(episodes.length, 1)"
              :value="chapterSliderValue"
              :disabled="episodes.length <= 1"
              :aria-label="$t('reader.chapterSlider')"
              @input="onChapterSliderInput"
              @change="commitChapterSlider"
            />
          </div>
          <button class="nav-arrow" :disabled="viewEpisode >= episodes.length - 1" @click="nextEpisode" :title="$t('reader.next')">›</button>
          <button class="nav-arrow" :disabled="viewEpisode >= episodes.length - 1" @click="jumpToChapter(episodes.length - 1)" :title="$t('reader.jumpLast')">»</button>
        </div>
      </div>

      <!-- 拖拽调整左右比例 -->
      <div v-show="showResizer" class="pane-resizer" @mousedown="startResize"></div>

      <!-- 右：图谱面板 -->
      <div v-show="showGraph" class="graph-pane">
        <GraphPanel
          :graph-data="graphData"
          :view-episode="viewEpisode"
          :graph-scope="graphScope"
          :episodes="episodes"
          :loading="graphLoading"
          :extract-progress="extractProgress"
          :seen-edges="seenEdgesArr"
          :select-request="selectRequest"
          :latest-read-episode="latestReadEpisode"
          @toggle-maximize="toggleGraphMaximized"
          @jump="onJump"
          @seen-edge="id => markEdgeSeen(id, true)"
          @set-edge-seen="({ id, value }) => markEdgeSeen(id, value)"
          @set-graph-scope="setGraphScope"
          @select-change="onGraphSelectChange"
          @retry-extraction="retryExtraction"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import {
  ref, shallowRef, markRaw, computed, defineAsyncComponent,
  onMounted, onUnmounted, nextTick, watch,
} from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { faArrowLeft } from '@fortawesome/free-solid-svg-icons'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import {
  uploadBook, ensureExtraction, getExtractStatus, getGraphData, getEpisode, getBook,
  getPdfSourceUrl, searchBook, setReadingMode
} from '../api/book'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import { useReadingProgress } from '../composables/useReadingProgress'
import {
  GRAPH_SCOPES,
  createMentionIndex,
  createQuoteMatcher,
  findQuoteRange,
  normalizeGraphScope,
  scopeAllowsMention,
  scopeEpisodeLimit,
} from '../utils/readerLinks'
import { visibleInterval, isRangeCovered } from '../utils/readProgress'
import { mergeGraphPayload } from '../utils/graphDelta'
import { readerTextBlocks } from '../utils/readerText'
import { clampRevealMax, latestReadableEpisode } from '../utils/revealProgress'
import {
  normalizeSearchQuery,
  orderSearchResults,
  searchGraphData,
} from '../utils/readerSearch'

const GraphPanel = defineAsyncComponent(() => import('../components/GraphPanel.vue'))
const PdfPageView = defineAsyncComponent(() => import('../components/PdfPageView.vue'))

const SEARCH_DEBOUNCE_MS = 220
const MAX_SEARCH_RESULTS = 300
const EXTRACTION_PREFETCH_EPISODES = 2
const EPISODE_TEXT_CACHE_LIMIT = 20

const props = defineProps({ projectId: String })
const router = useRouter()
const { t } = useI18n()

// 阅读进度（localStorage 持久化）
const {
  readEpisodes, seenEdges, episodeRanges, revealMax, viewEpisode,
  load: loadProgress, clear: clearProgress, markEpisodeRead, markEdgeSeen, isEpisodeRead,
  getEpisodeRanges, addEpisodeRange, episodeCoverage
} = useReadingProgress()

const seenEdgesArr = computed(() => [...seenEdges.value])
const readCount = computed(() => readEpisodes.value.size)
// 当前视口区间（用于阅读进度轨的视口标记）
const viewportInterval = ref([0, 0])

// 当前章节已浏览区间 -> 阅读进度轨的填充段
const railSegments = computed(() =>
  (episodeRanges.value[viewEpisode.value] || []).map(([s, e]) => ({
    top: s * 100,
    height: Math.max(0, (e - s) * 100),
  }))
)
const viewportMarker = computed(() => {
  const [s, e] = viewportInterval.value
  return { top: s * 100, height: Math.max(1, (e - s) * 100) }
})

// 每章覆盖率（用于章节滑杆轨与目录状态）
const chapterProgress = computed(() =>
  episodes.value.map((_, i) => episodeCoverage(i))
)
const chapterState = (i) => {
  if (isEpisodeRead(i)) return 'read'
  return (chapterProgress.value[i] || 0) > 0.001 ? 'partial' : 'unread'
}
const chapterPercent = (i) => Math.round((chapterProgress.value[i] || 0) * 100)
// 当前章节已读进度环
const RING_CIRC = 2 * Math.PI * 15.5
const currentReadPct = computed(() => chapterPercent(viewEpisode.value))
const readRingOffset = computed(() => {
  const pct = isEpisodeRead(viewEpisode.value) ? 100 : currentReadPct.value
  return RING_CIRC * (1 - Math.min(100, Math.max(0, pct)) / 100)
})
const showChapters = ref(false)
const graphMaximized = ref(false)
const compactViewport = ref(window.innerWidth < 640)
const activePane = ref('reader')
const latestReachedEpisode = ref(0)
const latestReadEpisode = computed(() => latestReadableEpisode({
  viewEpisode: viewEpisode.value,
  readEpisodes: readEpisodes.value,
  episodeRanges: episodeRanges.value,
  total: episodes.value.length,
  extraEpisodes: [latestReachedEpisode.value],
}))

// 左右分栏比例（书籍面板宽度百分比），可拖拽调整并持久化
const SPLIT_KEY = 'bookmiro:splitPct'
const splitPct = ref(Number(localStorage.getItem(SPLIT_KEY)) || 46)
const readerBody = ref(null)
const READER_MIN_WIDTH = 320
const GRAPH_MIN_WIDTH = 320
const COMPACT_BREAKPOINT = 640
const singlePane = computed(() => compactViewport.value)
const showBookPane = computed(() => !graphMaximized.value && (!singlePane.value || activePane.value === 'reader'))
const showGraph = computed(() => graphMaximized.value || !singlePane.value || activePane.value === 'graph')
const showResizer = computed(() => !graphMaximized.value && !singlePane.value)
const bookPaneStyle = computed(() => singlePane.value ? { width: '100%' } : { width: `${splitPct.value}%` })

const updateResponsiveLayout = () => {
  const width = readerBody.value?.getBoundingClientRect().width || window.innerWidth
  const nextCompact = width < COMPACT_BREAKPOINT
  const enteringCompact = nextCompact && !compactViewport.value
  compactViewport.value = nextCompact
  if (enteringCompact) activePane.value = 'reader'
}

const showGraphPane = () => {
  activePane.value = 'graph'
  nextTick(() => window.dispatchEvent(new Event('resize')))
}

const startResize = (e) => {
  e.preventDefault()
  const body = readerBody.value
  if (!body) return
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  const onMove = (ev) => {
    const rect = body.getBoundingClientRect()
    const proposedWidth = ev.clientX - rect.left
    const maxReaderWidth = Math.max(READER_MIN_WIDTH, rect.width - GRAPH_MIN_WIDTH - 6)
    const clampedWidth = Math.max(READER_MIN_WIDTH, Math.min(maxReaderWidth, proposedWidth))
    splitPct.value = (clampedWidth / rect.width) * 100
  }
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    try { localStorage.setItem(SPLIT_KEY, String(Math.round(splitPct.value))) } catch (e) { /* ignore */ }
    window.dispatchEvent(new Event('resize')) // 通知图谱重排
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

// 反向链接：请求图谱选中并居中某节点/关系
const selectRequest = ref(null)
// 图谱当前选中项（由 GraphPanel 通过 select-change 同步，用于导航历史快照）
const currentGraphSelection = ref(null)
const onGraphSelectChange = (sel) => {
  currentGraphSelection.value = sel ? { type: sel.type, id: sel.id } : null
}

// 导航历史栈：跳转前记录当前状态，供“返回”按钮恢复
const NAV_HISTORY_MAX = 50
const navHistory = ref([])
let isRestoring = false
const snapshotNavState = () => {
  const el = document.querySelector('.book-text')
  return {
    viewEpisode: viewEpisode.value,
    scrollTop: el ? el.scrollTop : 0,
    highlightQuote: highlightQuote.value,
    selection: currentGraphSelection.value ? { ...currentGraphSelection.value } : null,
  }
}
const pushNavSnapshot = () => {
  if (isRestoring) return
  navHistory.value.push(snapshotNavState())
  if (navHistory.value.length > NAV_HISTORY_MAX) navHistory.value.shift()
}

const goToGraph = (link) => {
  pushNavSnapshot()
  selectRequest.value = { type: link.type, id: link.id, nonce: Date.now() }
  if (singlePane.value) showGraphPane()
}
const linkTitle = (link) => `${t('reader.viewInGraph')}: ${link.name}`
// 节点已读状态由其（已揭示的）关系派生：无关系视为已读；所有关系已读则已读
const nodeSeen = (nodeId) => {
  const edges = (graphData.value?.edges || [])
  let has = false
  for (const e of edges) {
    if (graphScope.value === GRAPH_SCOPES.CURRENT) {
      if (!(e.mentions || []).some(m => scopeAllowsMention(m.episode, {
        scope: graphScope.value,
        viewEpisode: viewEpisode.value,
        total: episodes.value.length,
      }))) continue
    } else if (graphScope.value === GRAPH_SCOPES.UPTO && (e.first_episode ?? 0) > graphScopeLimit.value) {
      continue
    }
    if (e.source !== nodeId && e.target !== nodeId) continue
    has = true
    if (!seenEdges.value.has(e.id)) return false
  }
  return true
}
// 该关联项是否已读（用于正文内区分已读/未读）
const linkSeen = (link) => link.type === 'node'
  ? nodeSeen(link.id)
  : seenEdges.value.has(link.id)

const phase = ref('loading') // loading | uploading | review | ready | expired | error
const statusMessage = ref('')
const errorText = ref('')

const projectId = ref(props.projectId)
const bookName = ref('')
const language = ref('')
const episodes = ref([])
const sourceFormat = ref('')
const readingMode = ref(null)
const documentKind = ref('uncertain')
const classificationConfidence = ref(0)
const pageCount = ref(0)
const chapterDetectionStatus = ref('')
const modeChanging = ref(false)
const isPdfPageMode = computed(() => sourceFormat.value === 'pdf' && readingMode.value === 'page')
const pdfSourceUrl = computed(() => projectId.value && projectId.value !== 'new' ? getPdfSourceUrl(projectId.value) : '')
const currentPageNumber = computed(() => episodes.value[viewEpisode.value]?.page_number || viewEpisode.value + 1)
const documentKindLabel = computed(() => t(`reader.documentKind.${documentKind.value || 'uncertain'}`))
const episodeUnitLabel = computed(() => isPdfPageMode.value ? t('reader.pages') : t('reader.chapters'))
const episodeProgressLabel = computed(() => isPdfPageMode.value
  ? t('reader.pagesRead', { read: readCount.value, total: episodes.value.length })
  : t('reader.chaptersRead', { read: readCount.value, total: episodes.value.length }))
const positionLabel = computed(() => isPdfPageMode.value
  ? t('reader.pagePosition', { current: chapterSliderDisplay.value, total: episodes.value.length })
  : t('reader.chapterPosition', { current: chapterSliderDisplay.value, total: episodes.value.length }))
const reviewDescription = computed(() => {
  if (!readingMode.value) return t('reader.chooseModeToContinue')
  return isPdfPageMode.value
    ? t('reader.reviewPagesDesc', { count: episodes.value.length })
    : t('reader.reviewChaptersDesc', { count: episodes.value.length })
})
const canConfirmReview = computed(() =>
  !!readingMode.value && episodes.value.length > 0 && !modeChanging.value &&
  !(readingMode.value === 'chapter' && ['unavailable', 'unreliable'].includes(chapterDetectionStatus.value))
)

const graphData = shallowRef(markRaw({ nodes: [], edges: [] }))

const episodeTextCache = new Map()
const currentText = ref('')
const highlightQuote = ref('')
const searchBox = ref(null)
const searchQuery = ref('')
const searchOpen = ref(false)
const searchLoading = ref(false)
const searchResults = ref([])
const activeSearchIndex = ref(-1)
const searchHighlightRange = ref(null)
let searchTimer = null
let searchNonce = 0
let searchAbortController = null

// 增量抽取状态
const extractedUpto = ref(-1)
const extractRunning = ref(false)
const extractError = ref('')
const extractRetrying = ref(false)
const graphScope = ref(GRAPH_SCOPES.CURRENT)
const graphScopeLimit = computed(() => scopeEpisodeLimit({
  scope: graphScope.value,
  viewEpisode: viewEpisode.value,
  total: episodes.value.length,
}))
const setGraphScope = (scope) => {
  graphScope.value = normalizeGraphScope(scope)
  if (graphScope.value === GRAPH_SCOPES.ALL) ensureAhead()
}
// 当前图谱范围还没抽到时，显示"构建中"
const graphLoading = computed(() => graphScopeLimit.value > extractedUpto.value)
// Keep LLM extraction near the reading position so a new upload does not
// compete with the reader for server, network, and graph-rendering resources.
const desiredExtractUpto = computed(() => {
  const total = episodes.value.length
  if (!total) return -1
  if (graphScope.value === GRAPH_SCOPES.ALL) return total - 1
  const reached = Math.max(viewEpisode.value, latestReadEpisode.value, revealMax.value)
  return Math.min(total - 1, reached + EXTRACTION_PREFETCH_EPISODES)
})
const extractProgress = computed(() => {
  const total = episodes.value.length
  return {
    extracted: Math.max(0, extractedUpto.value + 1),
    target: total ? Math.min(total, desiredExtractUpto.value + 1) : 0,
    total,
    running: extractRunning.value,
    retrying: extractRetrying.value,
    error: extractRetrying.value ? '' : extractError.value,
  }
})

const currentEpisodeTitle = computed(() => {
  const ep = episodes.value[viewEpisode.value]
  return ep ? ep.title : ''
})

const chapterSliderValue = ref(1)
const chapterSliderIndex = computed(() =>
  clampRevealMax(Number(chapterSliderValue.value) - 1, episodes.value.length)
)
const chapterSliderDisplay = computed(() => episodes.value.length ? chapterSliderIndex.value + 1 : 0)
const chapterSliderTitle = computed(() => episodes.value[chapterSliderIndex.value]?.title || '')
const chapterSliderPercent = computed(() => chapterPercent(chapterSliderIndex.value))
const syncChapterSliderToView = () => {
  chapterSliderValue.value = episodes.value.length ? viewEpisode.value + 1 : 1
}
const onChapterSliderInput = (e) => {
  chapterSliderValue.value = Number(e.target.value) || 1
}
const commitChapterSlider = () => {
  jumpToChapter(chapterSliderIndex.value)
}

const chapterPreviewItems = computed(() => episodes.value.slice(0, 30))

const highlightRange = computed(() => {
  const searchRange = searchHighlightRange.value
  if (searchRange && searchRange.episode === viewEpisode.value) {
    return { start: searchRange.start, end: searchRange.end }
  }
  if (!highlightQuote.value) return null
  return findQuoteRange(currentText.value || '', highlightQuote.value)
})
const currentHighlightText = computed(() => {
  const range = highlightRange.value
  if (range && range.end > range.start) return currentText.value.slice(range.start, range.end)
  return highlightQuote.value || ''
})

// Build once per graph payload. Episode navigation then becomes a Map lookup
// instead of rescanning every node, edge, and mention.
const graphMentionIndex = computed(() => createMentionIndex(graphData.value, {
  scope: GRAPH_SCOPES.ALL,
  viewEpisode: 0,
  total: episodes.value.length,
}))

// 反向链接：本章正文中与（已揭示的）节点/关系相关联的片段
const episodeLinks = computed(() => {
  const text = currentText.value || ''
  if (!text) return []
  const ep = viewEpisode.value
  const links = []
  const findInText = createQuoteMatcher(text)
  for (const item of graphMentionIndex.value.get(ep) || []) {
    const range = findInText(item.quote)
    if (range) {
      links.push({
        start: range.start,
        end: range.end,
        type: item.type,
        id: item.id,
        name: item.name,
        quote: item.quote,
        seen: linkSeen(item),
      })
    }
  }
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
  const blocks = readerTextBlocks(text, {
    reflow: sourceFormat.value === 'pdf' && readingMode.value === 'chapter',
  })
  for (const block of blocks) {
    const line = block.text
    const pStart = block.start
    const pEnd = block.end
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
      paras.push({ heading: block.heading, segments: [{ text: line, mark: false, link: null }] })
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
    paras.push({ heading: block.heading, segments: segs })
  }
  return paras
})

// 滚动到高亮处并短暂闪烁提示
const flashTimers = []
const scrollToHighlight = () => {
  nextTick(() => {
    const el = document.querySelector('.book-text .quote-mark')
    if (!el) return
    beginJumpScroll()
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

const toggleGraphMaximized = () => {
  if (singlePane.value) {
    activePane.value = activePane.value === 'graph' ? 'reader' : 'graph'
    nextTick(() => window.dispatchEvent(new Event('resize')))
    return
  }
  graphMaximized.value = !graphMaximized.value
  nextTick(() => window.dispatchEvent(new Event('resize')))
}

const openSearch = () => {
  searchOpen.value = true
}

const confirmChapterReview = async () => {
  if (!canConfirmReview.value) {
    errorText.value = t('reader.noEpisodes')
    return
  }
  phase.value = 'ready'
  await setViewEpisode(0)
  // Prime a small extraction window without making the reader compete with
  // a full-book background job.
  ensureAhead()
}

const changeReadingMode = async (mode) => {
  if (sourceFormat.value !== 'pdf' || modeChanging.value || readingMode.value === mode) return
  modeChanging.value = true
  errorText.value = ''
  try {
    const res = await setReadingMode(projectId.value, mode)
    const data = res.data || {}
    readingMode.value = data.reading_mode || mode
    chapterDetectionStatus.value = data.chapter_detection_status || ''
    episodes.value = data.episodes || []
    pageCount.value = data.page_count || pageCount.value
    episodeTextCache.clear()
    currentText.value = ''
    clearProgress(projectId.value)
    syncChapterSliderToView()
  } catch (e) {
    errorText.value = e.message || t('reader.modeChangeFailed')
  } finally {
    modeChanging.value = false
  }
}

// ---------- 章节文本加载 ----------
const fetchEpisodeText = async (idx) => {
  if (episodeTextCache.has(idx)) {
    const cached = episodeTextCache.get(idx)
    episodeTextCache.delete(idx)
    episodeTextCache.set(idx, cached)
    return cached
  }
  try {
    const res = await getEpisode(projectId.value, idx)
    if (res.success) {
      const text = res.data.text || ''
      episodeTextCache.set(idx, text)
      while (episodeTextCache.size > EPISODE_TEXT_CACHE_LIMIT) {
        episodeTextCache.delete(episodeTextCache.keys().next().value)
      }
      return text
    }
  } catch (e) {
    // ignore transient fetch errors while searching
  }
  return ''
}

const loadEpisodeText = async (idx) => {
  currentText.value = await fetchEpisodeText(idx)
}

const recordReachedEpisode = (idx) => {
  latestReachedEpisode.value = Math.max(
    latestReachedEpisode.value,
    clampRevealMax(idx, episodes.value.length)
  )
}

const syncLatestReachedFromProgress = () => {
  latestReachedEpisode.value = latestReadableEpisode({
    viewEpisode: viewEpisode.value,
    readEpisodes: readEpisodes.value,
    episodeRanges: episodeRanges.value,
    total: episodes.value.length,
    extraEpisodes: [revealMax.value],
  })
}

const setViewEpisode = async (idx) => {
  idx = Math.max(0, Math.min(idx, episodes.value.length - 1))
  cancelDwell()
  const previousEpisode = viewEpisode.value
  viewEpisode.value = idx
  recordReachedEpisode(idx)
  if (idx > previousEpisode && idx > revealMax.value) revealMax.value = idx
  highlightQuote.value = ''
  searchHighlightRange.value = null
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

// “已读”需要停留：只有在某屏停留超过 DWELL_READ_MS 才计入覆盖，
// 这样快速划过（casual scroll）不会被误标为已读。
const DWELL_READ_MS = 1200
let dwellTimer = null

// 刷新视口标记（跟随滚动，便于看到当前所在位置）
const refreshViewportMarker = (el) => {
  if (!el) return
  viewportInterval.value = visibleInterval(el.scrollTop, el.clientHeight, el.scrollHeight)
}

// 停留计时：DWELL_READ_MS 内不再滚动，则把当前屏记入已读覆盖
const scheduleDwellRecord = () => {
  if (dwellTimer) clearTimeout(dwellTimer)
  dwellTimer = setTimeout(() => {
    dwellTimer = null
    const el = document.querySelector('.book-text')
    if (el) commitReadCoverage(el)
  }, DWELL_READ_MS)
}
const cancelDwell = () => {
  if (dwellTimer) { clearTimeout(dwellTimer); dwellTimer = null }
}

// 把当前视口区间并入本章覆盖，并推进链接已读状态（节点已读由此派生）
const commitReadCoverage = (el) => {
  if (!el) return
  const iv = visibleInterval(el.scrollTop, el.clientHeight, el.scrollHeight)
  addEpisodeRange(viewEpisode.value, iv)
  markCoveredEdges(el)
}

// 章节打开时：更新标记并开始停留计时（短章停留后由 visibleInterval 返回 [0,1] 记为整章已读）
const checkAutoRead = () => {
  nextTick(() => {
    const el = document.querySelector('.book-text')
    if (!el) return
    refreshViewportMarker(el)
    scheduleDwellRecord()
  })
}

// 程序化跳转（点击链接平滑滚动）期间，中间经过的位置不应记为已读；
// 抑制覆盖累计，待滚动停止后仍需在落点停留 DWELL_READ_MS 才计入。
let coverageSuppressed = false
let jumpSettleTimer = null
const beginJumpScroll = () => {
  coverageSuppressed = true
  if (scrollRaf) { cancelAnimationFrame(scrollRaf); scrollRaf = null }
  cancelDwell()
  scheduleJumpSettle()
}
const scheduleJumpSettle = () => {
  if (jumpSettleTimer) clearTimeout(jumpSettleTimer)
  jumpSettleTimer = setTimeout(() => {
    jumpSettleTimer = null
    coverageSuppressed = false
    scheduleDwellRecord()
  }, 250)
}

// 滚动时仅更新视口标记并重置停留计时；覆盖只在停留后累计
let scrollRaf = null
const onBookScroll = (e) => {
  const el = e.target
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  scrollRaf = requestAnimationFrame(() => refreshViewportMarker(el))
  if (coverageSuppressed) {
    scheduleJumpSettle()
    return
  }
  scheduleDwellRecord()
}

// 点击/拖拽阅读进度轨即滚动到对应位置（充当自定义滚动条）
const scrollBookToClientY = (rail, clientY) => {
  const el = document.querySelector('.book-text')
  if (!el || !rail) return
  const rect = rail.getBoundingClientRect()
  const ratio = (clientY - rect.top) / rect.height
  const max = el.scrollHeight - el.clientHeight
  const target = ratio * el.scrollHeight - el.clientHeight / 2
  el.scrollTop = Math.max(0, Math.min(max, target))
}
const onRailPointerDown = (e) => {
  const rail = e.currentTarget
  e.preventDefault()
  scrollBookToClientY(rail, e.clientY)
  const onMove = (ev) => scrollBookToClientY(rail, ev.clientY)
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

// 关系链接只有当其自身竖向范围完整落入本章已浏览区间时才标为已读；
// 这样中途被链接跳入章节时，上方未浏览的链接不会被误清。
const markCoveredEdges = (el) => {
  const h = el.scrollHeight
  if (!h) return
  const ranges = getEpisodeRanges(viewEpisode.value)
  el.querySelectorAll('.text-link.link-edge, .pdf-text-link.pdf-link-edge').forEach(node => {
    const id = node.getAttribute('data-edge-id')
    if (!id || seenEdges.value.has(id)) return
    const top = node.offsetTop / h
    const bottom = (node.offsetTop + node.offsetHeight) / h
    if (isRangeCovered(ranges, [top, bottom])) {
      markEdgeSeen(id, true)
    }
  })
}

const toggleChapterRead = () => {
  markEpisodeRead(viewEpisode.value, !isEpisodeRead(viewEpisode.value))
}

const jumpToChapter = (i) => {
  showChapters.value = false
  setViewEpisode(i)
}

const prevEpisode = () => setViewEpisode(viewEpisode.value - 1)
const nextEpisode = () => {
  setViewEpisode(viewEpisode.value + 1)
}

watch(viewEpisode, syncChapterSliderToView)
watch(() => episodes.value.length, syncChapterSliderToView)

// 返回：弹出上一个快照并恢复章节 / 滚动位置 / 高亮 / 图谱选中；不降低 revealMax
const goBack = async () => {
  if (!navHistory.value.length) return
  const snap = navHistory.value.pop()
  isRestoring = true
  try {
    if (singlePane.value) activePane.value = 'reader'
    if (snap.viewEpisode !== viewEpisode.value) {
      cancelDwell()
      viewEpisode.value = Math.max(0, Math.min(snap.viewEpisode, episodes.value.length - 1))
      recordReachedEpisode(viewEpisode.value)
      await loadEpisodeText(viewEpisode.value)
    }
    highlightQuote.value = snap.highlightQuote || ''
    searchHighlightRange.value = null
    await nextTick()
    beginJumpScroll()
    const el = document.querySelector('.book-text')
    if (el) el.scrollTop = snap.scrollTop || 0
    refreshViewportMarker(el)
    selectRequest.value = snap.selection
      ? { type: snap.selection.type, id: snap.selection.id, nonce: Date.now() }
      : { type: null, id: null, nonce: Date.now() }
  } finally {
    isRestoring = false
  }
}

const searchKindLabel = (kind) => {
  const map = {
    node: t('reader.searchKindNode'),
    edge: t('reader.searchKindEdge'),
    body: t('reader.searchKindBody'),
  }
  return map[kind] || kind
}

const runSearch = async () => {
  const query = normalizeSearchQuery(searchQuery.value)
  const nonce = ++searchNonce
  if (!query) {
    searchResults.value = []
    activeSearchIndex.value = -1
    searchLoading.value = false
    return
  }

  searchLoading.value = true
  const graphResults = searchGraphData(graphData.value, query)
  searchResults.value = orderSearchResults(graphResults).slice(0, MAX_SEARCH_RESULTS)
  searchAbortController?.abort()
  searchAbortController = new AbortController()
  try {
    const response = await searchBook(projectId.value, query, {
      limit: MAX_SEARCH_RESULTS,
      signal: searchAbortController.signal,
    })
    if (nonce !== searchNonce) return
    const bodyResults = response.data?.results || []
    searchResults.value = orderSearchResults([...graphResults, ...bodyResults]).slice(0, MAX_SEARCH_RESULTS)
    activeSearchIndex.value = searchResults.value.length
      ? Math.min(activeSearchIndex.value, searchResults.value.length - 1)
      : -1
  } catch (error) {
    if (error?.code !== 'ERR_CANCELED' && nonce === searchNonce) {
      searchResults.value = orderSearchResults(graphResults).slice(0, MAX_SEARCH_RESULTS)
    }
  } finally {
    if (nonce === searchNonce) searchLoading.value = false
  }
}

const scheduleSearch = () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(runSearch, SEARCH_DEBOUNCE_MS)
}

const clearSearch = () => {
  if (searchTimer) { clearTimeout(searchTimer); searchTimer = null }
  searchNonce += 1
  searchAbortController?.abort()
  searchAbortController = null
  searchQuery.value = ''
  searchOpen.value = false
  searchLoading.value = false
  searchResults.value = []
  activeSearchIndex.value = -1
  searchHighlightRange.value = null
}

const selectSearchResult = async (result, index = searchResults.value.indexOf(result)) => {
  if (!result) return
  pushNavSnapshot()
  activeSearchIndex.value = index
  searchOpen.value = false

  if (result.kind === 'node' || result.kind === 'edge') {
    searchHighlightRange.value = null
    highlightQuote.value = ''
    if (Number.isFinite(result.episode) && result.episode > graphScopeLimit.value) {
      setGraphScope(GRAPH_SCOPES.ALL)
      await nextTick()
    }
    selectRequest.value = { type: result.kind, id: result.id, nonce: Date.now() }
    return
  }

  if (result.kind === 'body') {
    if (graphMaximized.value) toggleGraphMaximized()
    if (singlePane.value) activePane.value = 'reader'
    highlightQuote.value = ''
    if (result.episode !== viewEpisode.value) {
      await setViewEpisode(result.episode)
    }
    searchHighlightRange.value = { episode: result.episode, start: result.start, end: result.end }
    await nextTick()
    scrollToHighlight()
  }
}

const moveSearch = async (delta) => {
  if (!searchResults.value.length) return
  const length = searchResults.value.length
  const base = activeSearchIndex.value >= 0 ? activeSearchIndex.value : (delta > 0 ? -1 : 0)
  const nextIndex = (base + delta + length) % length
  await selectSearchResult(searchResults.value[nextIndex], nextIndex)
}

const onSearchEnter = (e) => {
  moveSearch(e.shiftKey ? -1 : 1)
}

const onSearchDocumentMouseDown = (e) => {
  if (!searchOpen.value) return
  if (searchBox.value && searchBox.value.contains(e.target)) return
  searchOpen.value = false
}

// 从图谱跳转到原文
const onJump = async ({ episode, quote }) => {
  pushNavSnapshot()
  if (singlePane.value) activePane.value = 'reader'
  if (graphMaximized.value) graphMaximized.value = false
  if (episode !== viewEpisode.value) {
    const previousEpisode = viewEpisode.value
    viewEpisode.value = Math.max(0, Math.min(episode, episodes.value.length - 1))
    recordReachedEpisode(viewEpisode.value)
    if (viewEpisode.value > previousEpisode && viewEpisode.value > revealMax.value) revealMax.value = viewEpisode.value
    await loadEpisodeText(viewEpisode.value)
  }
  // 先清空再设置，保证即使重复点击同一引用也会重新触发滚动/高亮
  highlightQuote.value = ''
  searchHighlightRange.value = null
  await nextTick()
  highlightQuote.value = quote
  scrollToHighlight()
  ensureAhead()
}

// ---------- 图谱加载 ----------
let lastGraphEpisode = -1

const loadGraph = async ({ forceFull = false } = {}) => {
  try {
    const canUseDelta = !forceFull && lastGraphEpisode >= 0 && graphData.value.nodes.length > 0
    const res = await getGraphData(projectId.value, {
      sinceEpisode: canUseDelta ? lastGraphEpisode : null,
    })
    if (res.success) {
      const payload = res.data || { nodes: [], edges: [] }
      graphData.value = markRaw(mergeGraphPayload(graphData.value, payload))
      if (Number.isInteger(payload.revision_episode)) {
        lastGraphEpisode = payload.mode === 'full'
          ? payload.revision_episode
          : Math.max(lastGraphEpisode, payload.revision_episode)
      }
    }
  } catch (e) {
    // ignore
  }
}

// ---------- 按需增量抽取 + 轮询 ----------
let pollTimer = null
let polling = false
let lastLoadedUpto = -1
// 上一次已知的失败章节签名：失败章节被重试成功后（extracted_upto 不变但图谱新增节点），
// 据此触发图谱重新加载。
let lastFailedKey = ''

const pollStatus = async () => {
  try {
    const res = await getExtractStatus(projectId.value)
    if (res.success) {
      const s = res.data
      extractedUpto.value = s.extracted_upto
      extractRunning.value = s.running
      if (extractRetrying.value && s.running) {
        extractError.value = ''
      } else {
        extractRetrying.value = false
        extractError.value = s.error || ''
      }
      // 失败章节集合变化（多为重试成功）也意味着图谱数据有更新，需要重新拉取。
      const failedKey = (s.failed_episodes || []).join(',')
      const failedChanged = failedKey !== lastFailedKey
      lastFailedKey = failedKey
      if (s.extracted_upto > lastLoadedUpto || failedChanged) {
        lastLoadedUpto = Math.max(lastLoadedUpto, s.extracted_upto)
        await loadGraph({ forceFull: failedChanged })
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
const ensureAhead = async ({ suppressRunningError = false, surfaceRequestError = false } = {}) => {
  if (!projectId.value || projectId.value === 'new' || !episodes.value.length) return
  const target = desiredExtractUpto.value
  if (target < 0) return
  try {
    const res = await ensureExtraction(projectId.value, target)
    if (res.success) {
      extractedUpto.value = res.data.extracted_upto
      extractRunning.value = res.data.running
      if (suppressRunningError && res.data.running) {
        extractError.value = ''
      } else {
        extractError.value = res.data.error || ''
      }
      if (!res.data.running) extractRetrying.value = false
    }
  } catch (e) {
    if (surfaceRequestError) {
      extractRetrying.value = false
      extractError.value = e.message || 'Retry failed'
    }
  }
  startPolling()
}

const retryExtraction = async () => {
  if (extractRetrying.value) return
  extractRetrying.value = true
  extractError.value = ''
  await ensureAhead({ suppressRunningError: true, surfaceRequestError: true })
  if (!extractRunning.value) extractRetrying.value = false
}

// ---------- 初始化 ----------
const applyBookMeta = (data) => {
  bookName.value = data.name || ''
  language.value = data.language || ''
  episodes.value = data.episodes || []
  sourceFormat.value = data.source_format || inferSourceFormat(data.files)
  readingMode.value = data.reading_mode || (sourceFormat.value === 'pdf' && !(data.episodes || []).length ? null : 'chapter')
  documentKind.value = data.document_kind || 'uncertain'
  classificationConfidence.value = Number(data.classification_confidence) || 0
  pageCount.value = Number(data.page_count) || 0
  chapterDetectionStatus.value = data.chapter_detection_status || ''
}

const inferSourceFormat = (files = []) => {
  const filename = files?.[0]?.filename || ''
  return filename.includes('.') ? filename.split('.').pop().toLowerCase() : ''
}

const initExisting = async () => {
  phase.value = 'loading'
  statusMessage.value = t('reader.loading')
  try {
    lastGraphEpisode = -1
    const res = await getBook(projectId.value)
    if (!res.success) {
      errorText.value = res.error || 'Book not found'
      phase.value = 'error'
      return
    }
    applyBookMeta(res.data)
    if (!episodes.value.length && !(
      sourceFormat.value === 'pdf' &&
      (!readingMode.value || ['unavailable', 'unreliable'].includes(chapterDetectionStatus.value))
    )) {
      errorText.value = t('reader.noEpisodes')
      phase.value = 'error'
      return
    }
    if (!episodes.value.length && sourceFormat.value === 'pdf') {
      phase.value = 'review'
      statusMessage.value = t('reader.reviewStructure')
      return
    }
    loadProgress(projectId.value)  // 恢复已读进度与阅读位置
    syncLatestReachedFromProgress()
    extractedUpto.value = typeof res.data.extracted_upto === 'number' ? res.data.extracted_upto : -1
    lastLoadedUpto = extractedUpto.value

    // 已抽取的部分立即加载
    if (extractedUpto.value >= 0) await loadGraph()

    // 立即进入阅读；回到上次阅读位置
    phase.value = 'ready'
    if (episodes.value.length) await setViewEpisode(viewEpisode.value || 0)
    // Resume extraction only around the restored reading position.
    ensureAhead()
  } catch (e) {
    errorText.value = e.message || 'Failed to load book'
    phase.value = 'error'
  }
}

const initNew = async () => {
  const pending = getPendingUpload()
  if (!pending.isPending || !pending.files.length) {
    statusMessage.value = t('reader.uploadExpired')
    errorText.value = t('reader.uploadExpired')
    phase.value = 'expired'
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
    if (!episodes.value.length && !(
      sourceFormat.value === 'pdf' &&
      (!readingMode.value || ['unavailable', 'unreliable'].includes(chapterDetectionStatus.value))
    )) {
      errorText.value = t('reader.noEpisodes')
      phase.value = 'error'
      return
    }
    loadProgress(projectId.value)  // 新书：初始化空进度并绑定 projectId
    syncLatestReachedFromProgress()
    extractedUpto.value = -1
    lastLoadedUpto = -1
    lastGraphEpisode = -1
    // 更新 URL 以便刷新/分享
    router.replace({ name: 'Reader', params: { projectId: projectId.value } })
    phase.value = 'review'
    statusMessage.value = t('reader.reviewChapters')
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

watch(searchQuery, () => {
  const query = normalizeSearchQuery(searchQuery.value)
  activeSearchIndex.value = -1
  searchHighlightRange.value = null
  if (!query) {
    searchNonce += 1
    searchAbortController?.abort()
    searchAbortController = null
    searchOpen.value = false
    searchResults.value = []
    searchLoading.value = false
    return
  }
  searchOpen.value = true
  scheduleSearch()
})

watch(() => graphData.value, () => {
  if (normalizeSearchQuery(searchQuery.value)) scheduleSearch()
}, { deep: false })

watch(phase, async (value) => {
  if (value !== 'ready') return
  await nextTick()
  updateResponsiveLayout()
})

onMounted(() => {
  document.addEventListener('mousedown', onSearchDocumentMouseDown)
  window.addEventListener('resize', updateResponsiveLayout)
  if (props.projectId === 'new') {
    initNew()
  } else {
    initExisting()
  }
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onSearchDocumentMouseDown)
  window.removeEventListener('resize', updateResponsiveLayout)
  if (searchTimer) clearTimeout(searchTimer)
  searchAbortController?.abort()
  if (pollTimer) clearTimeout(pollTimer)
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  if (jumpSettleTimer) clearTimeout(jumpSettleTimer)
  cancelDwell()
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
.nav-left { display: flex; align-items: center; gap: 16px; min-width: 0; }
.back-btn {
  background: transparent; border: 1px solid rgba(255,255,255,0.3); color: #fff;
  padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;
  flex-shrink: 0;
}
.back-btn:hover { background: rgba(255,255,255,0.1); }
.nav-right { display: flex; align-items: center; gap: 12px; }
/* 深色顶栏上的语言切换按钮：提高对比度 */
.reader-nav :deep(.switcher-trigger) {
  color: #fff; border-color: rgba(255,255,255,0.3);
}
.reader-nav :deep(.switcher-trigger:hover) {
  border-color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.1);
}
.book-title { font-weight: 600; font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lang-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: #FF4500; color: #fff; font-weight: 600;
  flex-shrink: 0;
}
.reader-search {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
}
.search-input-wrap {
  width: 260px; height: 32px; display: flex; align-items: center; gap: 6px;
  padding: 0 8px; border: 1px solid rgba(255,255,255,0.24); border-radius: 6px;
  background: rgba(255,255,255,0.08); color: #fff; transition: all 0.15s;
}
.search-input-wrap.active,
.search-input-wrap:focus-within {
  border-color: rgba(255,255,255,0.55); background: rgba(255,255,255,0.14);
}
.search-icon { color: rgba(255,255,255,0.7); font-size: 14px; line-height: 1; }
.search-input {
  min-width: 0; flex: 1; border: none; outline: none; background: transparent;
  color: #fff; font-size: 13px;
}
.search-input::placeholder { color: rgba(255,255,255,0.58); }
.search-input::-webkit-search-cancel-button { display: none; }
.search-clear {
  width: 20px; height: 20px; border: none; border-radius: 50%; background: rgba(255,255,255,0.16);
  color: rgba(255,255,255,0.86); cursor: pointer; line-height: 1; font-size: 16px;
}
.search-clear:hover { background: rgba(255,255,255,0.28); color: #fff; }
.search-controls { display: flex; align-items: center; gap: 6px; color: rgba(255,255,255,0.78); }
.search-nav-btn {
  width: 24px; height: 24px; border: 1px solid rgba(255,255,255,0.22); border-radius: 5px;
  background: transparent; color: #fff; cursor: pointer; font-size: 16px; line-height: 1;
}
.search-nav-btn:hover:not(:disabled) { background: rgba(255,255,255,0.12); }
.search-nav-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.search-count { min-width: 66px; font-size: 11px; font-family: monospace; text-align: center; }
.search-results {
  position: absolute; top: calc(100% + 8px); right: 0; width: 430px; max-height: 420px;
  overflow-y: auto; background: #fff; border: 1px solid #E0E0E0; border-radius: 8px;
  box-shadow: 0 14px 36px rgba(0,0,0,0.2); z-index: 80; padding: 6px;
}
.search-empty {
  padding: 18px 14px; color: #777; font-size: 13px; text-align: center;
}
.search-result {
  width: 100%; display: flex; gap: 10px; padding: 10px; border: none; border-radius: 6px;
  background: transparent; text-align: left; cursor: pointer; color: #222;
}
.search-result:hover,
.search-result.active { background: #F8F8F8; }
.search-result-kind {
  flex: 0 0 46px; align-self: flex-start; padding: 3px 5px; border-radius: 4px;
  font-size: 10px; font-weight: 700; text-align: center; text-transform: uppercase;
}
.search-result.node .search-result-kind { color: #7B2D8E; background: #F5EAF8; }
.search-result.edge .search-result-kind { color: #E91E63; background: #FCE4EC; }
.search-result.body .search-result-kind { color: #FF4500; background: #FFF3E0; }
.search-result-main { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.search-result-title { font-size: 13px; font-weight: 700; color: #222; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search-result-subtitle { font-size: 11px; color: #777; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search-result-snippet { font-size: 12px; color: #555; line-height: 1.45; }

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
.chapter-item.partial { color: #444; }
.chapter-check { width: 16px; color: #FF4500; font-weight: 700; flex-shrink: 0; }
.chapter-item.partial .chapter-check { color: #FFB74D; }
.chapter-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chapter-pct { flex-shrink: 0; font-size: 11px; color: #FFB74D; font-weight: 600; font-family: monospace; }

/* 状态屏 */
.status-screen { flex: 1; display: flex; align-items: center; justify-content: center; }
.status-card {
  width: 420px; max-width: 90vw; text-align: center;
  padding: 40px; border: 1px solid #eee; border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.05);
}
.status-card.wide { width: 720px; text-align: left; }
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
.retry-btn:disabled { opacity: 0.45; cursor: not-allowed; background: #777; }
.retry-btn.secondary { background: #fff; color: #333; border: 1px solid #ddd; }
.retry-btn.secondary:hover { border-color: #FF4500; color: #FF4500; }

.review-head { margin-bottom: 18px; }
.review-title { font-size: 20px; font-weight: 700; color: #111; margin-bottom: 6px; }
.review-desc { font-size: 13px; color: #666; line-height: 1.6; }
.reading-mode-panel {
  margin-bottom: 16px; padding: 14px; border: 1px solid #e5e5e5;
  border-radius: 9px; background: #fff;
}
.reading-mode-heading { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 700; }
.detection-badge {
  margin-left: auto; padding: 3px 8px; border-radius: 999px;
  color: #1A6B3C; background: #E9F7EF; font-size: 11px; font-weight: 600;
}
.detection-badge.uncertain { color: #8A4B08; background: #FFF3E0; }
.reading-mode-switch { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 12px; }
.reading-mode-switch button {
  height: 38px; border: 1px solid #ddd; border-radius: 7px;
  background: #fafafa; color: #444; cursor: pointer; font-weight: 700;
}
.reading-mode-switch button.active { border-color: #FF4500; background: #FFF3E0; color: #C53600; }
.reading-mode-switch button:disabled { opacity: 0.55; cursor: wait; }
.reading-mode-help { margin: 9px 0 0; color: #777; font-size: 12px; line-height: 1.5; }
.mode-warning { margin: 9px 0 0; color: #B3261E; font-size: 12px; font-weight: 600; }
.chapter-preview-list {
  max-height: 360px; overflow-y: auto; border: 1px solid #eee;
  border-radius: 8px; background: #fafafa;
}
.chapter-preview-item {
  display: grid; grid-template-columns: 44px 1fr 72px; align-items: center;
  gap: 12px; padding: 10px 12px; border-bottom: 1px solid #eee;
}
.chapter-preview-item:last-child { border-bottom: none; }
.chapter-preview-index {
  font-family: monospace; font-size: 12px; color: #FF4500; font-weight: 700;
}
.chapter-preview-title {
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 14px; color: #222; font-weight: 600;
}
.chapter-preview-count {
  justify-self: end; font-family: monospace; font-size: 11px; color: #999;
}
.chapter-preview-more {
  padding: 12px; text-align: center; font-size: 12px; color: #777;
  background: #fff;
}
.chapter-preview-empty { padding: 32px 16px; text-align: center; color: #777; font-size: 13px; }
.review-actions {
  display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px;
}

/* 阅读主体 */
.reader-body { position: relative; flex: 1; display: flex; min-height: 0; }
.reader-body.graph-maximized .graph-pane { flex: 1 1 100%; }
.floating-reader-back {
  position: absolute; top: 50%; left: 0; z-index: 45;
  width: 20px; min-height: 46px; padding: 0; border: none; border-radius: 0 14px 14px 0;
  display: inline-flex; align-items: center; gap: 8px;
  justify-content: center; overflow: visible;
  background: rgba(17,17,17,0.62); color: #fff; box-shadow: 0 3px 10px rgba(0,0,0,0.14);
  cursor: pointer; font-size: 11px; font-weight: 700;
  transform: translateY(-50%);
  transition: width 0.16s ease, min-height 0.16s ease, background 0.15s, box-shadow 0.15s, border-radius 0.15s;
}
.floating-reader-back:hover,
.floating-reader-back:focus-visible {
  width: 82px; min-height: 34px; padding: 0 12px; justify-content: flex-start;
  border-radius: 0 17px 17px 0; font-size: 13px;
  background: #111; box-shadow: 0 8px 22px rgba(0,0,0,0.22);
}
.floating-reader-back:hover { background: #FF4500; }
.floating-back-label {
  max-width: 0; opacity: 0; overflow: hidden; white-space: nowrap;
  transition: max-width 0.16s ease, opacity 0.12s ease;
}
.floating-reader-back:hover .floating-back-label,
.floating-reader-back:focus-visible .floating-back-label {
  max-width: 42px; opacity: 1;
}
.floating-back-depth {
  position: absolute; top: -5px; right: -5px;
  min-width: 18px; height: 17px; padding: 0 4px; border-radius: 9px;
  display: inline-flex; align-items: center; justify-content: center;
  background: #FF4500; color: #fff; border: 1px solid #fff;
  font-size: 10px; line-height: 1; opacity: 0; transform: scale(0.85);
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.floating-reader-back:hover .floating-back-depth,
.floating-reader-back:focus-visible .floating-back-depth {
  opacity: 1; transform: scale(1);
}
.book-pane {
  width: 46%; min-width: 320px; flex-shrink: 0; display: flex; flex-direction: column;
  min-height: 0;
}
.graph-pane { flex: 1; min-width: 0; }
.reader-body.single-pane .book-pane,
.reader-body.single-pane .graph-pane { width: 100%; min-width: 0; flex: 1 1 100%; }

/* 左右分栏拖拽手柄 */
.pane-resizer {
  flex: 0 0 6px; cursor: col-resize; background: #eee;
  transition: background 0.15s; position: relative; z-index: 5;
}
.pane-resizer:hover, .pane-resizer:active { background: #FF4500; }

.episode-head {
  display: flex; align-items: baseline; justify-content: space-between;
  padding: 18px 32px 10px; flex-shrink: 0; gap: 12px;
}
.episode-title { font-size: 20px; font-weight: 700; color: #111; }
.episode-head-right { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.pane-action {
  height: 30px; padding: 0 10px; border: none; border-radius: 6px;
  background: #111; color: #fff; cursor: pointer; font-size: 11px; font-weight: 700;
}
.pane-action:hover { background: #FF4500; }
.pane-action.secondary { color: #444; background: #f1f1f1; }
.pane-action.secondary:hover { color: #fff; background: #555; }
/* 当前章节已读进度环（点击可切换整章已读/未读） */
.read-ring {
  position: relative; width: 34px; height: 34px; padding: 0; border: none;
  background: none; cursor: pointer; flex-shrink: 0;
}
.read-ring-svg { width: 34px; height: 34px; transform: rotate(-90deg); }
.read-ring-track { fill: none; stroke: #eee; stroke-width: 3.2; }
.read-ring-fill {
  fill: none; stroke: #FF4500; stroke-width: 3.2; stroke-linecap: round;
  transition: stroke-dashoffset 0.3s ease;
}
.read-ring-text {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: #999; font-family: monospace;
}
.read-ring.done .read-ring-text { color: #FF4500; font-size: 15px; }
.read-ring:hover .read-ring-fill { stroke: #e63e00; }

/* detail-close 复用于抽屉 */
.detail-close {
  background: none; border: none; font-size: 20px; cursor: pointer;
  color: #999; line-height: 1; padding: 0;
}
.detail-close:hover { color: #333; }

.book-scroll { flex: 1; display: flex; min-height: 0; }
.book-text {
  flex: 1; overflow-y: auto; padding: 8px 32px 24px;
  line-height: 1.9; font-size: 16px; color: #2b2b2b;
  font-family: 'Noto Serif SC', 'Georgia', serif;
  scrollbar-width: none; -ms-overflow-style: none;
}
.book-text:has(.pdf-page-view) { padding: 8px 12px 24px; background: #e9e9e9; }
.book-text::-webkit-scrollbar { width: 0; height: 0; }
.chapter-item,
.search-result {
  content-visibility: auto;
  contain-intrinsic-size: auto 54px;
}

/* 阅读进度轨（“我读到哪了”，可点击/拖拽滚动） */
.read-rail {
  position: relative; flex: 0 0 10px; width: 10px; margin: 8px 6px 24px 0;
  background: #f0f0f0; border-radius: 5px; overflow: hidden;
  cursor: pointer; user-select: none;
}
.read-rail:hover { background: #e8e8e8; }
.read-rail-seg {
  position: absolute; left: 0; right: 0;
  background: #FFCC80; border-radius: 5px; pointer-events: none;
}
.read-rail-view {
  position: absolute; left: 0; right: 0;
  background: rgba(255,69,0,0.55); border-radius: 5px; pointer-events: none;
  transition: top 0.1s linear, height 0.1s linear;
}
.para { margin: 0 0 1.1em; text-align: justify; white-space: normal; overflow-wrap: break-word; }
.para.reader-heading { margin: 1.25em 0 0.7em; font-weight: 750; text-align: left; }
.text-link { cursor: pointer; border-radius: 2px; transition: background 0.15s; }
/* 未读：醒目（实线 + 淡色底），节点用紫色、关系用粉色 */
.text-link.link-unseen {
  border-bottom: 2px solid #7B2D8E; background: rgba(123,45,142,0.10); font-weight: 600;
}
.text-link.link-unseen.link-edge {
  border-bottom-color: #E91E63; background: rgba(233,30,99,0.10);
}
.text-link.link-unseen:hover { background: rgba(123,45,142,0.22); }
.text-link.link-unseen.link-edge:hover { background: rgba(233,30,99,0.22); }
/* 已读：弱化（灰色虚线） */
.text-link.link-seen {
  border-bottom: 1px dotted #bbb; color: inherit;
}
.text-link.link-seen:hover { background: rgba(0,0,0,0.05); }
.quote-mark { background: #FFECB3; padding: 1px 2px; border-radius: 3px; box-shadow: 0 0 0 2px #FFECB3; transition: background 0.3s; }
.quote-mark.flash { animation: quoteFlash 1.6s ease-out; }
@keyframes quoteFlash {
  0% { background: #FFC107; box-shadow: 0 0 0 3px #FFC107; }
  30% { background: #FFC107; box-shadow: 0 0 0 3px #FFC107; }
  100% { background: #FFECB3; box-shadow: 0 0 0 2px #FFECB3; }
}

.episode-nav {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 12px; border-top: 1px solid #eee; flex-shrink: 0;
}
.chapters-btn-bottom {
  background: transparent; border: none; color: #555;
  width: 30px; height: 30px; padding: 0; font-size: 18px; cursor: pointer; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.15s, color 0.15s; flex-shrink: 0;
}
.chapters-btn-bottom:hover { background: #eee; color: #111; }
.nav-arrow {
  background: #fff; border: 1px solid #ddd; border-radius: 6px;
  width: 30px; height: 30px; padding: 0; cursor: pointer; font-size: 13px; color: #333; white-space: nowrap;
  display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.nav-arrow:hover:not(:disabled) { background: #f5f5f5; border-color: #bbb; }
.nav-arrow:disabled { opacity: 0.4; cursor: not-allowed; }
.chapter-scrubber {
  flex: 1 1 84px; min-width: 84px; display: flex; flex-direction: column; gap: 5px;
  padding: 2px 4px 0;
}
.chapter-scrubber-meta {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center; gap: 8px; min-width: 0;
}
.chapter-scrubber-index {
  font-size: 11px; font-weight: 700; color: #FF4500; white-space: nowrap;
  font-family: monospace;
}
.chapter-scrubber-title {
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 12px; color: #333; font-weight: 600;
}
.chapter-scrubber-pct {
  font-size: 11px; color: #FFB74D; font-weight: 700; font-family: monospace; white-space: nowrap;
}
.chapter-slider {
  width: 100%; height: 16px; margin: 0; accent-color: #FF4500; cursor: pointer;
}
.chapter-slider:disabled { opacity: 0.45; cursor: not-allowed; }

@media (max-width: 639px) {
  .reader-nav { padding: 0 10px; }
  .lang-badge { display: none; }
  .search-input-wrap { width: min(220px, 38vw); }
  .episode-head { padding: 14px 16px 8px; align-items: center; }
  .episode-title { min-width: 0; font-size: 17px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .book-text { padding-left: 18px; padding-right: 18px; }
}
</style>
