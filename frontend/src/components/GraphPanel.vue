<template>
  <div class="graph-panel">
    <div class="panel-header">
      <div class="header-left">
        <button
          v-if="historyDepth > 0"
          class="graph-history-back"
          @click="$emit('navigate-back')"
          :title="$t('reader.backToPrevious')"
          :aria-label="$t('reader.backToPrevious')"
        >
          <FontAwesomeIcon :icon="faArrowRotateLeft" />
          <span class="graph-history-depth">{{ historyDepth }}</span>
        </button>
        <span class="panel-title">{{ $t('graph.panelTitle') }}</span>
        <div class="graph-scope-control" :aria-label="$t('graph.scopeLabel')">
          <button
            v-for="mode in scopeModes"
            :key="mode.value"
            class="scope-mode-btn"
            :class="{ active: activeGraphScope === mode.value }"
            @click="setGraphScope(mode.value)"
            :title="$t(mode.titleKey)"
            :aria-label="$t(mode.titleKey)"
          >
            <FontAwesomeIcon :icon="mode.icon" />
          </button>
        </div>
      </div>
      <div class="header-tools">
        <button
          class="tool-btn"
          :class="{ active: showEdgeLabels }"
          @click="toggleEdgeLabels"
          :title="densityHint ? ($t('graph.showEdgeLabels') + ' · ' + $t('graph.denseGraphHint', { size: densityMessage })) : $t('graph.showEdgeLabels')"
        >
          <span>⤳</span>
          <span class="btn-text">{{ $t('graph.showEdgeLabels') }}</span>
        </button>
        <button
          class="tool-btn"
          :class="{ active: focusUnread }"
          @click="focusUnread = !focusUnread"
          :title="$t('graph.focusUnread')"
        >
          <span>◐</span>
          <span class="btn-text">{{ $t('graph.focusUnread') }}</span>
        </button>
        <div class="legend-control" ref="legendControl">
          <button
            class="tool-btn"
            :class="{ active: legendOpen }"
            :disabled="!entityTypes.length"
            @click.stop="legendOpen = !legendOpen"
            :title="$t('graph.entityTypes')"
          >
            <span>◧</span>
            <span class="btn-text">{{ $t('graph.entityTypes') }}</span>
          </button>
          <div v-if="legendOpen && entityTypes.length" class="legend-popover" @click.stop>
            <div class="legend-items">
              <div
                class="legend-item"
                v-for="type in entityTypes"
                :key="type.key"
                :class="{ active: activeType === type.key }"
                @click="highlightType(type.key)"
              >
                <span class="legend-dot" :style="{ background: type.color }"></span>
                <span class="legend-label">{{ type.name }}</span>
              </div>
            </div>
            <div class="legend-unread" v-if="unseenNodeCount || unseenEdgeCount">
              {{ $t('graph.unreadNodes', { n: unseenNodeCount }) }} · {{ $t('graph.unreadLinks', { n: unseenEdgeCount }) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="graph-container" ref="graphContainer">
      <div v-if="hasGraph" class="graph-view">
        <LargeGraphView
          v-if="useLargeGraphRenderer"
          :key="massiveGraphProfile ? 'massive' : 'standard'"
          ref="largeGraphView"
          :nodes="visibleNodes"
          :edges="visibleEdges"
          :selected-node-id="selectedNodeId"
          :selected-edge-id="selectedEdgeId"
          :type-colors="entityTypes"
          :seen-node-ids="seenNodeIds"
          :seen-edge-ids="focusUnread ? seenEdges : EMPTY_GRAPH_IDS"
          :focus-unread="focusUnread"
          :focused-node-ids="focusedNodeIds"
          :focused-edge-ids="focusedEdgeIds"
          :show-edge-labels="showEdgeLabels"
          :aria-label="$t('graph.panelTitle')"
          @select-node="selectNode"
          @select-edge="selectEdge"
          @renderer-error="handleLargeRendererError"
        />
        <svg v-else ref="graphSvg" class="graph-svg"></svg>

        <div v-if="loading || extractRetrying" class="graph-building-hint">
          <div class="memory-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="memory-icon">
              <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-4.04z" />
            </svg>
          </div>
          <span>{{ extractRetrying ? $t('graph.extractRetrying') : $t('graph.realtimeUpdating') }}</span>
          <span v-if="extractProgressText" class="graph-progress-text">{{ extractProgressText }}</span>
        </div>
        <div v-else-if="extractErrorText" class="graph-building-hint graph-error-hint" :title="extractErrorText">
          <span class="error-icon">⚠</span>
          <span>{{ $t('graph.extractError', { error: extractErrorText }) }}</span>
          <button class="extract-retry-btn" @click="$emit('retry-extraction')">
            {{ $t('reader.retry') }}
          </button>
        </div>

          <!-- 详情面板 -->
        <div v-if="selectedItem" class="detail-panel">
          <div class="detail-panel-header">
            <span class="detail-title">
              {{ selectedItem.type === 'node' ? $t('graph.nodeDetails') : $t('graph.relationship') }}
            </span>
            <span v-if="selectedItem.type === 'node'" class="detail-type-badge" :style="{ background: selectedItem.color }">
              {{ selectedItem.node.type || '—' }}
            </span>
            <button
              class="detail-seen-btn"
              :class="{ seen: selectedSeen }"
              @click="toggleSelectedSeen"
            >
              {{ selectedSeen ? '✓ ' + $t('graph.markUnread') : $t('graph.markRead') }}
            </button>
            <button class="detail-close" @click="closeDetailPanel">×</button>
          </div>

          <!-- 节点详情 + 关系走查 -->
          <div v-if="selectedItem.type === 'node'" class="detail-content" ref="detailContent" @scroll="onReelScroll">
            <div class="node-name">{{ selectedItem.node.name }}</div>
            <div class="node-aliases" v-if="selectedItem.node.aliases && selectedItem.node.aliases.length">
              {{ $t('graph.aliases') }}: {{ selectedItem.node.aliases.join('、') }}
            </div>
            <div class="node-desc" v-if="selectedItem.node.description">{{ selectedItem.node.description }}</div>

            <!-- 关系走查 Edge Reel -->
            <div class="edge-reel" v-if="nodeEdges.length">
              <div class="reel-header">
                <span class="section-title">{{ $t('graph.relationships') }} ({{ nodeEdges.length }})</span>
              </div>
              <div class="reel-hint">{{ $t('graph.reelHint') }}</div>
              <div class="reel-list" ref="reelList">
                <div
                  v-for="(er, i) in nodeEdges"
                  :key="er.edge.id"
                  class="reel-item"
                  :class="{ active: i === activeReelIndex }"
                  @mouseenter="setActiveReel(i, { scroll: false })"
                  @click="setActiveReel(i)"
                >
                  <div
                    class="relationship-statement compact"
                    role="group"
                    :aria-label="$t('graph.relationshipDirection', {
                      source: er.sourceName,
                      relationship: er.edge.label,
                      target: er.targetName,
                    })"
                  >
                    <span class="relationship-part endpoint source" data-relationship-role="source">
                      <strong>{{ er.sourceName }}</strong>
                    </span>
                    <span class="relationship-connector">
                      <span class="relationship-part predicate" data-relationship-role="predicate">
                        <strong>{{ er.edge.label }}</strong>
                      </span>
                      <span class="relationship-arrow" data-relationship-arrow aria-hidden="true"></span>
                    </span>
                    <span class="relationship-part endpoint target" data-relationship-role="target">
                      <strong>{{ er.targetName }}</strong>
                    </span>
                  </div>
                  <div class="reel-fact" v-if="er.edge.fact">{{ er.edge.fact }}</div>
                  <div
                    v-if="firstVisibleMention(er.edge)"
                    class="reel-quote"
                    @click.stop="jumpTo(firstVisibleMention(er.edge))"
                  >
                    <span class="reel-quote-text">“{{ firstVisibleMention(er.edge).quote }}”</span>
                    <span class="mention-jump">
                      <FontAwesomeIcon :icon="faBookOpenReader" />
                      {{ $t('graph.readInBook') }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div class="mentions book-mentions" v-if="selectedMentions.length">
              <button class="mentions-toggle" @click="bookMentionsOpen = !bookMentionsOpen">
                <span class="section-title">
                  <FontAwesomeIcon :icon="faBookOpenReader" />
                  {{ $t('graph.originalText') }} ({{ selectedMentions.length }})
                </span>
                <FontAwesomeIcon :icon="bookMentionsOpen ? faChevronUp : faChevronDown" />
              </button>
              <div v-if="bookMentionsOpen" class="mentions-list">
                <div
                  v-for="(m, i) in selectedMentions"
                  :key="'nm' + i"
                  class="mention-item"
                  @click="jumpTo(m)"
                >
                  <span class="mention-ep">{{ episodeTitle(m.episode) }}</span>
                  <span class="mention-quote">“{{ m.quote }}”</span>
                  <span class="mention-jump">
                    <FontAwesomeIcon :icon="faBookOpenReader" />
                    {{ $t('graph.readInBook') }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- 边详情 -->
          <div v-else class="detail-content">
            <div
              class="relationship-statement"
              role="group"
              :aria-label="$t('graph.relationshipDirection', {
                source: selectedItem.sourceName,
                relationship: selectedItem.edge.label,
                target: selectedItem.targetName,
              })"
            >
              <span class="relationship-part endpoint source" data-relationship-role="source">
                <strong>{{ selectedItem.sourceName }}</strong>
              </span>
              <span class="relationship-connector">
                <span class="relationship-part predicate" data-relationship-role="predicate">
                  <strong>{{ selectedItem.edge.label }}</strong>
                </span>
                <span class="relationship-arrow" data-relationship-arrow aria-hidden="true"></span>
              </span>
              <span class="relationship-part endpoint target" data-relationship-role="target">
                <strong>{{ selectedItem.targetName }}</strong>
              </span>
            </div>
            <div class="node-desc" v-if="selectedItem.edge.fact">{{ selectedItem.edge.fact }}</div>
            <div class="mentions book-mentions" v-if="selectedMentions.length">
              <button class="mentions-toggle" @click="bookMentionsOpen = !bookMentionsOpen">
                <span class="section-title">
                  <FontAwesomeIcon :icon="faBookOpenReader" />
                  {{ $t('graph.originalText') }} ({{ selectedMentions.length }})
                </span>
                <FontAwesomeIcon :icon="bookMentionsOpen ? faChevronUp : faChevronDown" />
              </button>
              <div v-if="bookMentionsOpen" class="mentions-list">
                <div
                  v-for="(m, i) in selectedMentions"
                  :key="'em' + i"
                  class="mention-item"
                  @click="jumpTo(m)"
                >
                  <span class="mention-ep">{{ episodeTitle(m.episode) }}</span>
                  <span class="mention-quote">“{{ m.quote }}”</span>
                  <span class="mention-jump">
                    <FontAwesomeIcon :icon="faBookOpenReader" />
                    {{ $t('graph.readInBook') }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="loading || extractRetrying" class="graph-state">
        <div class="loading-spinner"></div>
        <p>{{ extractRetrying ? $t('graph.extractRetrying') : $t('graph.graphDataLoading') }}</p>
      </div>

      <div v-else-if="extractErrorText" class="graph-state">
        <div class="empty-icon error-icon" :title="extractErrorText">⚠</div>
        <p class="empty-text">{{ $t('graph.extractError', { error: extractErrorText }) }}</p>
        <button class="extract-retry-btn state-retry-btn" @click="$emit('retry-extraction')">
          {{ $t('reader.retry') }}
        </button>
      </div>

      <div v-else class="graph-state">
        <div class="empty-icon">❖</div>
        <p class="empty-text">{{ $t('graph.emptyReveal') }}</p>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as d3 from 'd3'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import {
  faBookOpenReader,
  faArrowRotateLeft,
  faChevronDown,
  faChevronUp,
  faFileLines,
  faInfinity,
  faLayerGroup,
} from '@fortawesome/free-solid-svg-icons'
import {
  estimateEdgeLabelWidth,
  graphDensityMessage,
  shouldAutoHideEdgeLabels,
} from '../utils/graphPerformance'
import { GRAPH_SCOPES, normalizeGraphScope, scopeAllowsMention } from '../utils/readerLinks'
import { colorForEntityType, entityTypeKey, groupEntityTypes } from '../utils/entityTypes'
import LargeGraphView from './LargeGraphView.vue'
import { shouldUseLargeGraphRenderer, shouldUseMassiveGraphProfile } from '../utils/largeGraph'

const props = defineProps({
  graphData: Object,        // { nodes, edges }
  viewEpisode: Number,      // 当前正在阅读的章节（本章视图）
  graphScope: { type: String, default: GRAPH_SCOPES.UPTO },
  episodes: Array,          // 章节元数据（用于标题）
  loading: Boolean,
  extractProgress: { type: Object, default: null },
  seenEdges: { type: Array, default: () => [] },  // 已查看关系 id（节点已读由此派生）
  selectRequest: { type: Object, default: null },  // 外部请求选中 { type, id, nonce }
  latestReadEpisode: { type: Number, default: 0 },
  historyDepth: { type: Number, default: 0 },
})

const emit = defineEmits([
  'navigate-back', 'jump',
  'seen-edge', 'set-edge-seen', 'set-graph-scope', 'select-change', 'retry-extraction'
])

const graphContainer = ref(null)
const graphSvg = ref(null)
const largeGraphView = ref(null)
const largeRendererFailed = ref(false)
const reelList = ref(null)
const detailContent = ref(null)
const selectedItem = ref(null)
const showEdgeLabels = ref(true)
const edgeLabelsUserOverrode = ref(false)
const activeReelIndex = ref(0)
const focusUnread = ref(false)
const bookMentionsOpen = ref(false)
// 实体类型图例：以 header 弹层展示，点击某类型高亮该类全部实体
const legendOpen = ref(false)
const legendControl = ref(null)
const activeType = ref(null)

// 已查看集合（快速查询）
const seenEdgeSet = computed(() => new Set(props.seenEdges))

const COLORS = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C', '#3498db', '#9b59b6', '#27ae60', '#f39c12']
const EMPTY_GRAPH_IDS = Object.freeze([])

// 高亮配色：选中节点/相连边用 ACCENT，正在走查的边用 ACTIVE（更醒目）
const HL_ACCENT = '#E91E63'
const HL_ACTIVE = '#FF4500'

// 位置缓存，保证逐章展开时已有节点位置稳定
const positionCache = new Map()

const episodeCount = computed(() => props.episodes?.length || 0)
const activeGraphScope = computed(() => normalizeGraphScope(props.graphScope))
const scopeModes = [
  { value: GRAPH_SCOPES.CURRENT, icon: faFileLines, titleKey: 'graph.scopeCurrent' },
  { value: GRAPH_SCOPES.UPTO, icon: faLayerGroup, titleKey: 'graph.scopeUpto' },
  { value: GRAPH_SCOPES.ALL, icon: faInfinity, titleKey: 'graph.scopeAll' },
]

const setGraphScope = (scope) => {
  emit('set-graph-scope', normalizeGraphScope(scope))
}

// 向阅读面板同步当前选中项，供其导航历史快照/恢复使用
watch(() => selectedItem.value, (sel) => {
  bookMentionsOpen.value = false
  if (!sel) {
    emit('select-change', null)
  } else {
    emit('select-change', {
      type: sel.type,
      id: sel.type === 'node' ? sel.node.id : sel.edge.id,
    })
  }
})

// ---------- 可见子图（按阅读进度过滤） ----------
const mentionedIn = (item, ep) => (item.mentions || []).some(m => m.episode === ep)
const mentionScopeOptions = computed(() => ({
  scope: activeGraphScope.value,
  viewEpisode: props.viewEpisode ?? 0,
  total: episodeCount.value,
}))
const visibleMentions = (item) => (item?.mentions || [])
  .filter(m => scopeAllowsMention(m.episode, mentionScopeOptions.value))
const firstVisibleMention = (item) => visibleMentions(item)[0]

const visibleNodes = computed(() => {
  const nodes = props.graphData?.nodes || []
  if (activeGraphScope.value === GRAPH_SCOPES.ALL) return nodes
  if (activeGraphScope.value === GRAPH_SCOPES.CURRENT) {
    const ep = props.viewEpisode ?? 0
    const edges = props.graphData?.edges || []
    // 本章提及的实体 + 本章关系涉及的两端实体
    const keep = new Set()
    nodes.forEach(n => { if (mentionedIn(n, ep)) keep.add(n.id) })
    edges.forEach(e => {
      if (mentionedIn(e, ep)) { keep.add(e.source); keep.add(e.target) }
    })
    return nodes.filter(n => keep.has(n.id))
  }
  const upto = props.viewEpisode ?? 0
  return nodes.filter(n => (n.first_episode ?? 0) <= upto)
})

const visibleEdges = computed(() => {
  const edges = props.graphData?.edges || []
  // A persisted full graph already enforces valid endpoints, and the WebGL
  // synchronizer still validates defensively. Returning the source array here
  // avoids a redundant node Set plus a full edge copy on All Chapters.
  if (activeGraphScope.value === GRAPH_SCOPES.ALL) {
    return edges
  }
  const ids = new Set(visibleNodes.value.map(n => n.id))
  if (activeGraphScope.value === GRAPH_SCOPES.CURRENT) {
    const ep = props.viewEpisode ?? 0
    return edges.filter(e => mentionedIn(e, ep) && ids.has(e.source) && ids.has(e.target))
  }
  const upto = props.viewEpisode ?? 0
  return edges.filter(
    e => (e.first_episode ?? 0) <= upto && ids.has(e.source) && ids.has(e.target)
  )
})

// 节点已读状态：由其（可见）关系派生。无关系视为已读；所有关系已读则已读。
const nodeSeenSet = computed(() => {
  const unseen = new Set()
  visibleEdges.value.forEach(e => {
    if (!seenEdgeSet.value.has(e.id)) {
      unseen.add(e.source)
      unseen.add(e.target)
    }
  })
  const seen = new Set()
  visibleNodes.value.forEach(n => {
    if (!unseen.has(n.id)) seen.add(n.id)
  })
  return seen
})

const hasGraph = computed(() => visibleNodes.value.length > 0)
const useLargeGraphRenderer = computed(() => !largeRendererFailed.value && shouldUseLargeGraphRenderer({
  nodeCount: visibleNodes.value.length,
  edgeCount: visibleEdges.value.length,
}))
// Sigma's WebGL contexts and programs are fixed at construction time. Keying
// the profile makes a standard-large -> massive scope transition remount once
// instead of retaining native edge picking, z-index buffers and live layout.
const massiveGraphProfile = computed(() => shouldUseMassiveGraphProfile({
  nodeCount: visibleNodes.value.length,
  edgeCount: visibleEdges.value.length,
}))
const densityMessage = computed(() => graphDensityMessage({
  nodeCount: visibleNodes.value.length,
  edgeCount: visibleEdges.value.length,
}))
const densityHint = computed(() =>
  hasGraph.value && !showEdgeLabels.value && visibleEdges.value.length > 180
)
const extractProgressText = computed(() => {
  const progress = props.extractProgress
  if (!progress?.total) return ''
  const extracted = Math.min(progress.extracted || 0, progress.total)
  const target = Math.min(progress.target || progress.total, progress.total)
  return `${extracted}/${progress.total} · ${target}`
})
const extractErrorText = computed(() => props.extractProgress?.error || '')
const extractRetrying = computed(() => !!props.extractProgress?.retrying)

const nodeById = computed(() => {
  const m = {}
  visibleNodes.value.forEach(n => { m[n.id] = n })
  return m
})

const entityTypes = computed(() => groupEntityTypes(visibleNodes.value, COLORS))
const selectedNodeId = computed(() => selectedItem.value?.type === 'node' ? selectedItem.value.node.id : null)
const selectedEdgeId = computed(() => selectedItem.value?.type === 'edge' ? selectedItem.value.edge.id : null)
const seenNodeIds = computed(() => {
  // Large graphs only use these ids for the optional unread-focus reducer.
  // Leave the expensive edge-derived set lazy during ordinary exploration.
  if (useLargeGraphRenderer.value && !focusUnread.value) return EMPTY_GRAPH_IDS
  return [...nodeSeenSet.value]
})
const focusedNodeIds = computed(() => {
  if (!activeType.value) return []
  return visibleNodes.value
    .filter(node => entityTypeKey(node.type) === activeType.value)
    .map(node => node.id)
})
const focusedEdgeIds = computed(() => {
  if (!activeType.value) return []
  const nodeIds = new Set(focusedNodeIds.value)
  return visibleEdges.value
    .filter(edge => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .map(edge => edge.id)
})

const handleLargeRendererError = () => {
  largeRendererFailed.value = true
  nextTick(scheduleGraphRender)
}

const colorForType = (type) => colorForEntityType(type, entityTypes.value)

const toggleEdgeLabels = () => {
  showEdgeLabels.value = !showEdgeLabels.value
  edgeLabelsUserOverrode.value = true
}

// 当前可见范围内的未读数量
const unseenNodeCount = computed(() =>
  visibleNodes.value.filter(n => !nodeSeenSet.value.has(n.id)).length
)
const unseenEdgeCount = computed(() =>
  visibleEdges.value.filter(e => !seenEdgeSet.value.has(e.id)).length
)

// 当前选中项是否已读
const selectedSeen = computed(() => {
  if (!selectedItem.value) return false
  if (selectedItem.value.type === 'node') return nodeSeenSet.value.has(selectedItem.value.node.id)
  return seenEdgeSet.value.has(selectedItem.value.edge.id)
})

const selectedMentions = computed(() => {
  const sel = selectedItem.value
  if (!sel) return []
  return visibleMentions(sel.type === 'node' ? sel.node : sel.edge)
})

const toggleSelectedSeen = () => {
  if (!selectedItem.value) return
  const value = !selectedSeen.value
  if (selectedItem.value.type === 'node') {
    // 节点已读状态由其关系派生：批量标记该节点的所有可见关系
    const id = selectedItem.value.node.id
    visibleEdges.value.forEach(e => {
      if (e.source === id || e.target === id) emit('set-edge-seen', { id: e.id, value })
    })
  } else {
    emit('set-edge-seen', { id: selectedItem.value.edge.id, value })
  }
}

// 当前选中节点的所有关系（供 Edge Reel）
const nodeEdges = computed(() => {
  if (!selectedItem.value || selectedItem.value.type !== 'node') return []
  const nodeId = selectedItem.value.node.id
  const result = []
  visibleEdges.value.forEach(e => {
    if (e.source === nodeId || e.target === nodeId) {
      const outgoing = e.source === nodeId
      const neighborId = outgoing ? e.target : e.source
      result.push({
        edge: e,
        outgoing,
        neighborId,
        neighborName: nodeById.value[neighborId]?.name || '—',
        sourceName: nodeById.value[e.source]?.name || '—',
        targetName: nodeById.value[e.target]?.name || '—',
      })
    }
  })
  return result
})

const episodeTitle = (idx) => {
  const ep = (props.episodes || []).find(e => e.index === idx)
  return ep ? ep.title : `#${idx + 1}`
}

const jumpTo = (mention) => {
  if (!mention) return
  emit('jump', { episode: mention.episode, quote: mention.quote })
}

const closeDetailPanel = () => {
  selectedItem.value = null
  activeType.value = null
  clearGraphHighlight()
}

// ---------- d3 渲染 ----------
let simulation = null
let linkSel = null
let nodeSel = null
let nodeLabelSel = null
let linkLabelSel = null
let linkLabelBgSel = null
let linkLabelGroupSel = null
let svgSel = null
let zoomBehavior = null
let graphRootSel = null
let linkGroupSel = null
let linkLabelLayerSel = null
let nodeGroupSel = null
let rendererSvgElement = null
let resizeObserver = null
let graphRenderRaf = null
let graphResizeRaf = null
let lastZoomTransform = d3.zoomIdentity
let graphWidth = 1
let graphHeight = 1
let positionCacheTick = 0
let currentNodes = []
let currentEdges = []
let pendingCenterRequest = null

// Reuse the same mutable simulation records across graph updates. D3 stores
// velocity and positions on these objects, so replacing them makes an
// incremental chapter reveal look (and perform) like a brand-new layout.
const nodeStateById = new Map()
const edgeStateById = new Map()

// 当前选中项（及其相邻元素）不受"只看未读"淡化影响，保证正在查看的内容始终可见
const exemptIds = () => {
  const nodes = new Set()
  const edges = new Set()
  const sel = selectedItem.value
  if (sel?.type === 'node') {
    const id = sel.node.id
    nodes.add(id)
    visibleEdges.value.forEach(e => {
      if (e.source === id || e.target === id) {
        edges.add(e.id)
        nodes.add(e.source)
        nodes.add(e.target)
      }
    })
  } else if (sel?.type === 'edge') {
    edges.add(sel.edge.id)
    nodes.add(sel.edge.source)
    nodes.add(sel.edge.target)
  }
  return { nodes, edges }
}

// 根据已读状态更新节点/边样式（未读强调、已读弱化、专注未读时进一步淡化）
const applySeenStyles = () => {
  const { nodes: exNodes, edges: exEdges } = exemptIds()
  const dimNode = (id) => focusUnread.value && nodeSeenSet.value.has(id) && !exNodes.has(id)
  const dimEdge = (id) => focusUnread.value && seenEdgeSet.value.has(id) && !exEdges.has(id)
  if (nodeSel) {
    nodeSel
      .attr('r', d => nodeSeenSet.value.has(d.id) ? 9 : 12)
      .classed('node-unseen', d => !nodeSeenSet.value.has(d.id))
      .attr('opacity', d => dimNode(d.id) ? 0.2 : 1)
  }
  if (nodeLabelSel) {
    nodeLabelSel.attr('opacity', d => dimNode(d.id) ? 0.2 : 1)
  }
  if (linkSel) {
    linkSel
      .attr('stroke-dasharray', d => seenEdgeSet.value.has(d.data.id) ? null : '5,4')
      .attr('opacity', d => dimEdge(d.data.id) ? 0.15 : 1)
  }
  // 类型隔离时，透明度以隔离结果为准
  if (activeType.value) applyTypeHighlight()
}

const clearGraphHighlight = () => {
  if (nodeSel) nodeSel.attr('stroke', '#fff').attr('stroke-width', 2.5)
  if (linkSel) linkSel.attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
}

// 按实体类型隔离：只显示该类节点，其余（及其相连关系）淡出隐藏
const applyTypeHighlight = () => {
  if (!nodeSel || !activeType.value) return
  const matchIds = new Set(
    visibleNodes.value
      .filter(n => entityTypeKey(n.type) === activeType.value)
      .map(n => n.id)
  )
  const edgeVisible = (d) => matchIds.has(d.source.id) && matchIds.has(d.target.id)
  nodeSel.attr('opacity', d => matchIds.has(d.id) ? 1 : 0.06)
  if (nodeLabelSel) nodeLabelSel.attr('opacity', d => matchIds.has(d.id) ? 1 : 0)
  if (linkSel) linkSel.attr('opacity', d => edgeVisible(d) ? 1 : 0.04)
  if (linkLabelSel) linkLabelSel.attr('opacity', d => edgeVisible(d) ? 1 : 0)
  if (linkLabelBgSel) linkLabelBgSel.attr('opacity', d => edgeVisible(d) ? 1 : 0)
}

const highlightType = (typeName) => {
  if (activeType.value === typeName) {
    activeType.value = null
    clearGraphHighlight()
    applySeenStyles()
    return
  }
  // 类型高亮与选中详情互斥
  selectedItem.value = null
  activeType.value = typeName
  clearGraphHighlight()
  applyTypeHighlight()
}

const selectedItemVisible = () => {
  const sel = selectedItem.value
  if (!sel) return true
  if (sel.type === 'node') return visibleNodes.value.some(n => n.id === sel.node.id)
  if (sel.type === 'edge') return visibleEdges.value.some(e => e.id === sel.edge.id)
  return true
}

const highlightEdge = (edgeId) => {
  clearGraphHighlight()
  if (!linkSel) return
  linkSel.filter(d => d.data.id === edgeId)
    .attr('stroke', '#E91E63').attr('stroke-width', 3)
  const edge = visibleEdges.value.find(e => e.id === edgeId)
  if (edge && nodeSel) {
    nodeSel.filter(d => d.id === edge.source || d.id === edge.target)
      .attr('stroke', '#E91E63').attr('stroke-width', 4)
  }
}

const highlightNode = (nodeId, activeEdgeId = null) => {
  clearGraphHighlight()
  if (nodeSel) {
    nodeSel.filter(d => d.id === nodeId).attr('stroke', HL_ACCENT).attr('stroke-width', 4)
  }
  if (linkSel) {
    // 选中节点的所有相连边统一高亮
    linkSel.filter(d => d.data.source === nodeId || d.data.target === nodeId)
      .attr('stroke', HL_ACCENT).attr('stroke-width', 2.5)
    // 正在走查的边用更醒目的颜色/粗细区分
    if (activeEdgeId) {
      linkSel.filter(d => d.data.id === activeEdgeId)
        .attr('stroke', HL_ACTIVE).attr('stroke-width', 5)
      const edge = visibleEdges.value.find(e => e.id === activeEdgeId)
      if (edge && nodeSel) {
        const neighborId = edge.source === nodeId ? edge.target : edge.source
        nodeSel.filter(d => d.id === neighborId).attr('stroke', HL_ACTIVE).attr('stroke-width', 4)
      }
    }
  }
}

const selectNode = (node) => {
  selectedItem.value = {
    type: 'node',
    node,
    color: colorForType(node.type)
  }
  activeReelIndex.value = 0
  activeType.value = null
  highlightNode(node.id)
  nextTick(() => {
    if (nodeEdges.value.length) highlightActiveReel()
  })
}

const selectEdge = (edge) => {
  selectedItem.value = {
    type: 'edge',
    edge,
    sourceName: nodeById.value[edge.source]?.name || '—',
    targetName: nodeById.value[edge.target]?.name || '—'
  }
  activeType.value = null
  emit('seen-edge', edge.id)
  highlightEdge(edge.id)
}

// 将某点平移到视图中心（保持当前缩放）
const centerOnPoint = (x, y) => {
  if (!svgSel || !zoomBehavior || !graphContainer.value) return
  const width = graphContainer.value.clientWidth
  const height = graphContainer.value.clientHeight
  const current = d3.zoomTransform(svgSel.node())
  const k = current.k || 1
  const t = d3.zoomIdentity.translate(width / 2 - x * k, height / 2 - y * k).scale(k)
  svgSel.transition().duration(500).call(zoomBehavior.transform, t)
}

const centerOnNode = (id) => {
  if (useLargeGraphRenderer.value) {
    largeGraphView.value?.centerOnNode(id)
    return
  }
  const p = nodeStateById.get(id) || positionCache.get(id)
  if (p) centerOnPoint(p.x, p.y)
}

const centerOnEdge = (edge) => {
  if (useLargeGraphRenderer.value) {
    largeGraphView.value?.centerOnEdge(edge.id)
    return
  }
  const a = nodeStateById.get(edge.source) || positionCache.get(edge.source)
  const b = nodeStateById.get(edge.target) || positionCache.get(edge.target)
  if (a && b) centerOnPoint((a.x + b.x) / 2, (a.y + b.y) / 2)
  else if (a) centerOnPoint(a.x, a.y)
}

// 外部（阅读面板反向链接）请求选中并居中某节点/关系
watch(() => props.selectRequest, (req) => {
  if (!req) return
  if (!req.type || !req.id) {
    pendingCenterRequest = null
    closeDetailPanel()
    return
  }
  if (req.type === 'node') {
    const n = visibleNodes.value.find(x => x.id === req.id)
    if (n) {
      selectNode(n)
      if (useLargeGraphRenderer.value) nextTick(() => centerOnNode(n.id))
      else {
        pendingCenterRequest = { type: 'node', id: n.id }
        scheduleGraphRender()
      }
    }
  } else if (req.type === 'edge') {
    const e = visibleEdges.value.find(x => x.id === req.id)
    if (e) {
      selectEdge(e)
      if (useLargeGraphRenderer.value) nextTick(() => centerOnEdge(e))
      else {
        pendingCenterRequest = { type: 'edge', edge: e }
        scheduleGraphRender()
      }
    }
  }
})

const pointFor = (endpoint) => {
  if (endpoint && typeof endpoint === 'object') return endpoint
  return nodeStateById.get(endpoint) || { x: graphWidth / 2, y: graphHeight / 2 }
}

const getLinkPath = (d) => {
  const source = pointFor(d.source)
  const target = pointFor(d.target)
  const sx = source.x ?? graphWidth / 2
  const sy = source.y ?? graphHeight / 2
  const tx = target.x ?? graphWidth / 2
  const ty = target.y ?? graphHeight / 2
  if (d.selfLoop) {
    const r = 28
    return `M${sx + 8},${sy - 4} A${r},${r} 0 1,1 ${sx + 8},${sy + 4}`
  }
  if (d.curvature === 0) return `M${sx},${sy} L${tx},${ty}`
  const dx = tx - sx
  const dy = ty - sy
  const dist = Math.sqrt(dx * dx + dy * dy) || 1
  const off = Math.max(35, dist * 0.3)
  const cx = (sx + tx) / 2 + (-dy / dist) * d.curvature * off
  const cy = (sy + ty) / 2 + (dx / dist) * d.curvature * off
  return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`
}

const getLinkMidpoint = (d) => {
  const source = pointFor(d.source)
  const target = pointFor(d.target)
  const sx = source.x ?? graphWidth / 2
  const sy = source.y ?? graphHeight / 2
  const tx = target.x ?? graphWidth / 2
  const ty = target.y ?? graphHeight / 2
  if (d.selfLoop) return { x: sx + 60, y: sy }
  if (d.curvature === 0) return { x: (sx + tx) / 2, y: (sy + ty) / 2 }
  const dx = tx - sx
  const dy = ty - sy
  const dist = Math.sqrt(dx * dx + dy * dy) || 1
  const off = Math.max(35, dist * 0.3)
  const cx = (sx + tx) / 2 + (-dy / dist) * d.curvature * off
  const cy = (sy + ty) / 2 + (dx / dist) * d.curvature * off
  return {
    x: 0.25 * sx + 0.5 * cx + 0.25 * tx,
    y: 0.25 * sy + 0.5 * cy + 0.25 * ty,
  }
}

const persistPositions = () => {
  currentNodes.forEach(n => {
    if (Number.isFinite(n.x) && Number.isFinite(n.y)) {
      positionCache.set(n.id, { x: n.x, y: n.y })
    }
  })
}

const updateGraphPositions = () => {
  if (linkSel) linkSel.attr('d', getLinkPath)
  if (linkLabelGroupSel) {
    linkLabelGroupSel.attr('transform', d => {
      const mid = getLinkMidpoint(d)
      return `translate(${mid.x},${mid.y})`
    })
  }
  if (nodeSel) nodeSel.attr('cx', d => d.x).attr('cy', d => d.y)
  if (nodeLabelSel) nodeLabelSel.attr('x', d => d.x).attr('y', d => d.y)

  // The mutable node records already preserve live positions. The separate
  // cache is only needed when a node leaves and later re-enters the scope, so
  // copying every node on every animation tick is unnecessary work.
  positionCacheTick += 1
  if (positionCacheTick % 12 === 0) persistPositions()
}

const nodeDragBehavior = d3.drag()
  .on('start', (event, d) => {
    d.fx = d.x
    d.fy = d.y
    d._sx = event.x
    d._sy = event.y
    d._drag = false
  })
  .on('drag', (event, d) => {
    const dist = Math.hypot(event.x - d._sx, event.y - d._sy)
    if (!d._drag && dist > 3) {
      d._drag = true
      simulation?.alphaTarget(0.3).restart()
    }
    if (d._drag) {
      d.fx = event.x
      d.fy = event.y
    }
  })
  .on('end', (event, d) => {
    if (d._drag) simulation?.alphaTarget(0)
    d.fx = null
    d.fy = null
    d._drag = false
    positionCache.set(d.id, { x: d.x, y: d.y })
  })

const clearRendererReferences = () => {
  rendererSvgElement = null
  svgSel = null
  graphRootSel = null
  linkGroupSel = null
  linkLabelLayerSel = null
  nodeGroupSel = null
  linkSel = null
  linkLabelGroupSel = null
  linkLabelSel = null
  linkLabelBgSel = null
  nodeSel = null
  nodeLabelSel = null
  zoomBehavior = null
}

const suspendGraphRenderer = () => {
  persistPositions()
  simulation?.stop()
  clearRendererReferences()
}

const updateGraphSize = ({ reheat = true } = {}) => {
  if (!svgSel || !graphContainer.value) return
  const width = Math.max(1, graphContainer.value.clientWidth)
  const height = Math.max(1, graphContainer.value.clientHeight)
  const changed = width !== graphWidth || height !== graphHeight
  graphWidth = width
  graphHeight = height
  svgSel
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)
  zoomBehavior?.extent([[0, 0], [width, height]])

  if (!simulation || !changed) return
  simulation.force('center')?.x(width / 2).y(height / 2)
  simulation.force('x')?.x(width / 2)
  simulation.force('y')?.y(height / 2)
  if (reheat && currentNodes.length) {
    simulation.alpha(Math.max(simulation.alpha(), 0.12)).restart()
  }
}

const ensureRenderer = () => {
  if (!graphSvg.value || !graphContainer.value) return false
  if (rendererSvgElement === graphSvg.value && svgSel) return true

  simulation?.stop()
  clearRendererReferences()
  rendererSvgElement = graphSvg.value
  svgSel = d3.select(graphSvg.value)
  graphRootSel = svgSel.selectAll('g.graph-root').data([null]).join('g').attr('class', 'graph-root')
  linkGroupSel = graphRootSel.selectAll('g.links').data([null]).join('g').attr('class', 'links')
  linkLabelLayerSel = graphRootSel.selectAll('g.link-labels').data([null]).join('g').attr('class', 'link-labels')
  nodeGroupSel = graphRootSel.selectAll('g.nodes').data([null]).join('g').attr('class', 'nodes')

  zoomBehavior = d3.zoom()
    .scaleExtent([0.1, 4])
    .on('zoom.graph', (event) => {
      lastZoomTransform = event.transform
      graphRootSel?.attr('transform', event.transform)
    })
  svgSel.call(zoomBehavior)
  svgSel.on('click.graph-selection', () => { closeDetailPanel() })
  updateGraphSize({ reheat: false })
  if (lastZoomTransform !== d3.zoomIdentity) {
    svgSel.call(zoomBehavior.transform, lastZoomTransform)
  }
  return true
}

const ensureSimulation = () => {
  if (simulation) return
  simulation = d3.forceSimulation([])
    .force('link', d3.forceLink([]).id(d => d.id)
      .distance(d => 140 + ((d.pairTotal || 1) - 1) * 40))
    .force('charge', d3.forceManyBody().strength(-380))
    .force('center', d3.forceCenter(graphWidth / 2, graphHeight / 2))
    .force('collide', d3.forceCollide(46))
    .force('x', d3.forceX(graphWidth / 2).strength(0.04))
    .force('y', d3.forceY(graphHeight / 2).strength(0.04))
    .on('tick.graph', updateGraphPositions)
    .on('end.graph', persistPositions)
}

const pairKey = (source, target) => {
  const a = String(source)
  const b = String(target)
  return a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`
}

const edgeKey = (edge, index) => String(
  edge.id ?? `${edge.source}\u0000${edge.target}\u0000${edge.label || ''}\u0000${index}`
)

const initialOffset = (id, salt) => {
  const text = `${id}:${salt}`
  let hash = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return ((hash >>> 0) / 0xffffffff - 0.5) * 60
}

const syncEdgeLabels = () => {
  if (!linkLabelLayerSel) return
  if (!showEdgeLabels.value) {
    linkLabelLayerSel.selectAll('g.link-label').remove()
    linkLabelGroupSel = null
    linkLabelSel = null
    linkLabelBgSel = null
    return
  }

  linkLabelGroupSel = linkLabelLayerSel.selectAll('g.link-label')
    .data(currentEdges, d => d.key)
    .join(
      enter => {
        const label = enter.append('g')
          .attr('class', 'link-label')
          .style('cursor', 'pointer')
          .on('click', (event, d) => { event.stopPropagation(); selectEdge(d.data) })
        label.append('rect')
          .attr('fill', 'rgba(255,255,255,0.95)')
          .attr('rx', 3)
          .attr('ry', 3)
        label.append('text')
          .attr('font-size', '9px')
          .attr('fill', '#666')
          .attr('text-anchor', 'middle')
          .attr('dominant-baseline', 'middle')
          .style('pointer-events', 'none')
          .style('font-family', 'system-ui, sans-serif')
        return label
      },
      update => update,
      exit => exit.remove(),
    )

  linkLabelGroupSel.each(function (d) {
    const width = estimateEdgeLabelWidth(d.name)
    const label = d3.select(this)
    label.select('rect')
      .attr('x', -width / 2)
      .attr('y', -7)
      .attr('width', width)
      .attr('height', 14)
    label.select('text').text(d.name)
  })
  linkLabelBgSel = linkLabelGroupSel.select('rect')
  linkLabelSel = linkLabelGroupSel.select('text')
}

const restoreGraphHighlight = () => {
  if (selectedItem.value) {
    if (selectedItem.value.type === 'node') {
      const er = nodeEdges.value[activeReelIndex.value]
      highlightNode(selectedItem.value.node.id, er ? er.edge.id : null)
    } else {
      highlightEdge(selectedItem.value.edge.id)
    }
  } else if (activeType.value) {
    applyTypeHighlight()
  }
}

const renderGraph = () => {
  if (!ensureRenderer()) {
    suspendGraphRenderer()
    return
  }

  const rawNodes = visibleNodes.value
  const rawEdges = visibleEdges.value
  const previousNodeIds = new Set(currentNodes.map(n => n.id))
  const previousEdgeKeys = new Set(currentEdges.map(e => e.key))
  const topologyChanged = rawNodes.length !== currentNodes.length
    || rawEdges.length !== currentEdges.length
    || rawNodes.some(n => !previousNodeIds.has(n.id))
    || rawEdges.some((e, index) => {
      const key = edgeKey(e, index)
      const existing = edgeStateById.get(key)
      return !previousEdgeKeys.has(key)
        || existing?.sourceId !== e.source
        || existing?.targetId !== e.target
    })

  const nextNodeIds = new Set()
  const nodes = rawNodes.map(rawNode => {
    nextNodeIds.add(rawNode.id)
    let node = nodeStateById.get(rawNode.id)
    if (!node) {
      const cached = positionCache.get(rawNode.id)
      node = {
        id: rawNode.id,
        x: Number.isFinite(cached?.x) ? cached.x : graphWidth / 2 + initialOffset(rawNode.id, 'x'),
        y: Number.isFinite(cached?.y) ? cached.y : graphHeight / 2 + initialOffset(rawNode.id, 'y'),
      }
      nodeStateById.set(rawNode.id, node)
    }
    node.name = rawNode.name || '—'
    node.type = rawNode.type || '—'
    node.data = rawNode
    return node
  })
  for (const [id, node] of nodeStateById) {
    if (!nextNodeIds.has(id)) {
      if (Number.isFinite(node.x) && Number.isFinite(node.y)) {
        positionCache.set(id, { x: node.x, y: node.y })
      }
      nodeStateById.delete(id)
    }
  }

  // Compute parallel-edge curvature once per data reconciliation, not per tick.
  const pairCounts = new Map()
  rawEdges.forEach(edge => {
    if (edge.source === edge.target) return
    const key = pairKey(edge.source, edge.target)
    pairCounts.set(key, (pairCounts.get(key) || 0) + 1)
  })
  const pairIndexes = new Map()
  const nextEdgeKeys = new Set()
  const edges = rawEdges.map((rawEdge, index) => {
    const key = edgeKey(rawEdge, index)
    nextEdgeKeys.add(key)
    const selfLoop = rawEdge.source === rawEdge.target
    let pairTotal = 1
    let curvature = 0
    if (!selfLoop) {
      const keyForPair = pairKey(rawEdge.source, rawEdge.target)
      pairTotal = pairCounts.get(keyForPair) || 1
      const pairIndex = pairIndexes.get(keyForPair) || 0
      pairIndexes.set(keyForPair, pairIndex + 1)
      if (pairTotal > 1) {
        curvature = ((pairIndex / (pairTotal - 1)) - 0.5) * 1.5
        if (String(rawEdge.source) > String(rawEdge.target)) curvature = -curvature
      }
    }

    let edge = edgeStateById.get(key)
    if (!edge) {
      edge = { key }
      edgeStateById.set(key, edge)
    }
    // forceLink mutates source/target into node objects. Reset them to ids
    // before handing the updated list back to the force.
    edge.source = rawEdge.source
    edge.target = rawEdge.target
    edge.sourceId = rawEdge.source
    edge.targetId = rawEdge.target
    edge.name = rawEdge.label || '—'
    edge.curvature = curvature
    edge.selfLoop = selfLoop
    edge.pairTotal = pairTotal
    edge.data = rawEdge
    return edge
  })
  for (const key of edgeStateById.keys()) {
    if (!nextEdgeKeys.has(key)) edgeStateById.delete(key)
  }

  currentNodes = nodes
  currentEdges = edges
  ensureSimulation()
  simulation.nodes(nodes)
  simulation.force('link').links(edges)
  updateGraphSize({ reheat: false })

  linkSel = linkGroupSel.selectAll('path.graph-link')
    .data(edges, d => d.key)
    .join(
      enter => enter.append('path')
        .attr('class', 'graph-link')
        .attr('fill', 'none')
        .style('cursor', 'pointer')
        .on('click', (event, d) => { event.stopPropagation(); selectEdge(d.data) }),
      update => update,
      exit => exit.remove(),
    )
    .attr('stroke', '#C0C0C0')
    .attr('stroke-width', 1.5)

  nodeSel = nodeGroupSel.selectAll('circle.graph-node')
    .data(nodes, d => d.id)
    .join(
      enter => enter.append('circle')
        .attr('class', 'graph-node')
        .attr('r', 10)
        .style('cursor', 'pointer')
        .on('click', (event, d) => { event.stopPropagation(); selectNode(d.data) }),
      update => update,
      exit => exit.remove(),
    )
    .attr('fill', d => colorForType(d.type))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2.5)
    .call(nodeDragBehavior)

  nodeLabelSel = nodeGroupSel.selectAll('text.node-label')
    .data(nodes, d => d.id)
    .join(
      enter => enter.append('text')
        .attr('class', 'node-label')
        .attr('font-size', '11px')
        .attr('fill', '#333')
        .attr('font-weight', '500')
        .attr('dx', 14)
        .attr('dy', 4)
        .style('pointer-events', 'none')
        .style('font-family', 'system-ui, sans-serif'),
      update => update,
      exit => exit.remove(),
    )
    .text(d => d.name.length > 10 ? d.name.slice(0, 10) + '…' : d.name)

  syncEdgeLabels()
  updateGraphPositions()
  applySeenStyles()
  restoreGraphHighlight()

  if (pendingCenterRequest) {
    const request = pendingCenterRequest
    pendingCenterRequest = null
    if (request.type === 'node') centerOnNode(request.id)
    else centerOnEdge(request.edge)
  }

  if (!nodes.length) {
    simulation.stop()
  } else if (topologyChanged) {
    simulation.alpha(Math.max(simulation.alpha(), previousNodeIds.size ? 0.45 : 0.9)).restart()
  }
}

// ---------- Edge Reel 交互 ----------
const highlightActiveReel = () => {
  if (!selectedItem.value || selectedItem.value.type !== 'node') return
  const nodeId = selectedItem.value.node.id
  const er = nodeEdges.value[activeReelIndex.value]
  if (er) emit('seen-edge', er.edge.id)
  // 保持整个节点的边高亮，同时突出当前走查的边
  highlightNode(nodeId, er ? er.edge.id : null)
}

const setActiveReel = (i, { scroll = true } = {}) => {
  if (i < 0 || i >= nodeEdges.value.length) return
  activeReelIndex.value = i
  highlightActiveReel()
  if (scroll) scrollReelToActive()
}

// 关系列表已不再单独滚动，随详情面板（.detail-content）一起滚动
const scrollReelToActive = () => {
  const list = reelList.value
  const scroller = detailContent.value
  if (!list || !scroller) return
  const item = list.children[activeReelIndex.value]
  if (!item) return
  const itemRect = item.getBoundingClientRect()
  const scRect = scroller.getBoundingClientRect()
  const target = scroller.scrollTop + (itemRect.top - scRect.top) - (scroller.clientHeight - item.clientHeight) / 2
  scroller.scrollTo({ top: Math.max(0, target), behavior: 'smooth' })
}

let reelScrollRaf = null
const onReelScroll = () => {
  if (reelScrollRaf) cancelAnimationFrame(reelScrollRaf)
  reelScrollRaf = requestAnimationFrame(() => {
    reelScrollRaf = null
    const list = reelList.value
    const scroller = detailContent.value
    if (!list || !scroller) return
    const children = Array.from(list.children)
    if (!children.length) return

    const maxScrollTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight)
    let best = -1
    if (maxScrollTop > 0 && scroller.scrollTop >= maxScrollTop - 2) {
      best = children.length - 1
    }

    const scRect = scroller.getBoundingClientRect()
    const center = scRect.top + scroller.clientHeight / 2
    if (best < 0) {
      let bestDist = Infinity
      children.forEach((child, i) => {
        const r = child.getBoundingClientRect()
        const mid = r.top + r.height / 2
        const dist = Math.abs(mid - center)
        if (dist < bestDist) { bestDist = dist; best = i }
      })
    }
    if (best >= 0 && best !== activeReelIndex.value) {
      activeReelIndex.value = best
      highlightActiveReel()
    }
  })
}

const onKey = (e) => {
  if (!selectedItem.value || selectedItem.value.type !== 'node' || !nodeEdges.value.length) return
  if (e.key === 'ArrowDown') { e.preventDefault(); setActiveReel((activeReelIndex.value + 1) % nodeEdges.value.length) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveReel((activeReelIndex.value - 1 + nodeEdges.value.length) % nodeEdges.value.length) }
}

// ---------- watchers ----------
const scheduleGraphRender = () => {
  nextTick(() => {
    if (graphRenderRaf !== null) return
    graphRenderRaf = requestAnimationFrame(() => {
      graphRenderRaf = null
      renderGraph()
    })
  })
}

// visibleNodes/visibleEdges cover data replacement, scope changes and chapter
// reveal changes. A single animation-frame scheduler coalesces them so one
// logical update cannot trigger two complete D3 reconciliation passes.
watch([visibleNodes, visibleEdges], () => {
  if (!selectedItemVisible()) selectedItem.value = null
  scheduleGraphRender()
})

watch(showEdgeLabels, () => {
  syncEdgeLabels()
  updateGraphPositions()
  if (activeType.value) applyTypeHighlight()
})

watch(() => visibleEdges.value.length, (edgeCount) => {
  if (shouldAutoHideEdgeLabels({ edgeCount, userOverrode: edgeLabelsUserOverrode.value })) {
    showEdgeLabels.value = false
  }
}, { immediate: true })

// 已读状态 / 专注未读 / 选中项变化时，仅更新样式，避免整图重排
watch([() => props.seenEdges, focusUnread, () => selectedItem.value], () => {
  applySeenStyles()
})

const handleResize = () => {
  if (graphResizeRaf !== null) return
  graphResizeRaf = requestAnimationFrame(() => {
    graphResizeRaf = null
    if (rendererSvgElement === graphSvg.value && svgSel) updateGraphSize()
    else scheduleGraphRender()
  })
}

// 点击弹层外部关闭实体类型图例
const onDocumentMouseDown = (e) => {
  if (!legendOpen.value) return
  if (legendControl.value && legendControl.value.contains(e.target)) return
  legendOpen.value = false
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', onKey)
  document.addEventListener('mousedown', onDocumentMouseDown)
  if (typeof ResizeObserver !== 'undefined' && graphContainer.value) {
    resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(graphContainer.value)
  }
  scheduleGraphRender()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('keydown', onKey)
  document.removeEventListener('mousedown', onDocumentMouseDown)
  resizeObserver?.disconnect()
  if (graphRenderRaf !== null) cancelAnimationFrame(graphRenderRaf)
  if (graphResizeRaf !== null) cancelAnimationFrame(graphResizeRaf)
  if (reelScrollRaf) cancelAnimationFrame(reelScrollRaf)
  suspendGraphRenderer()
})
</script>

<style scoped>
.graph-panel {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: #FAFAFA;
  background-image: radial-gradient(#D0D0D0 1.5px, transparent 1.5px);
  background-size: 24px 24px;
  overflow: hidden;
}

.panel-header {
  position: absolute;
  top: 0; left: 0; right: 0;
  padding: 12px 20px;
  /* Navigation tools must remain reachable when a narrow layout lets the
     relationship detail card overlap the wrapped toolbar. */
  z-index: 30;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px 16px; flex-wrap: wrap;
  background: linear-gradient(to bottom, rgba(255,255,255,0.95), rgba(255,255,255,0.75) 60%, rgba(255,255,255,0));
  pointer-events: none;
}

.header-left { pointer-events: auto; display: flex; align-items: center; gap: 14px; min-width: 0; flex-wrap: wrap; }
.panel-title { font-size: 14px; font-weight: 600; color: #333; white-space: nowrap; }
.header-tools { pointer-events: auto; display: flex; gap: 10px; align-items: center; }
.graph-history-back {
  position: relative;
  width: 34px; height: 32px; padding: 0; flex: 0 0 auto;
  border: 1px solid #DADADA; border-radius: 8px;
  display: inline-flex; align-items: center; justify-content: center;
  background: #FFF; color: #333; cursor: pointer;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
  transition: background 0.15s, color 0.15s, border-color 0.15s, transform 0.15s;
}
.graph-history-back:hover,
.graph-history-back:focus-visible {
  background: #FFF3EE; color: #FF4500; border-color: #FF9B78;
  transform: translateX(-1px);
}
.graph-history-depth {
  position: absolute; top: -7px; right: -7px;
  min-width: 17px; height: 17px; padding: 0 4px;
  border-radius: 9px; display: inline-flex; align-items: center; justify-content: center;
  background: #FF4500; color: #FFF; border: 1px solid #FFF;
  font-size: 10px; line-height: 1; font-weight: 750;
}

.graph-scope-control {
  display: inline-flex;
  border: 1px solid #DADADA;
  border-radius: 8px;
  overflow: hidden;
  background: #FFF;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.scope-mode-btn {
  width: 34px; height: 32px; border: none; border-left: 1px solid #E8E8E8;
  display: inline-flex; align-items: center; justify-content: center;
  background: #FFF; color: #555; cursor: pointer; font-size: 14px;
  transition: background 0.15s, color 0.15s;
}
.scope-mode-btn:first-child { border-left: none; }
.scope-mode-btn:hover { background: #F5F5F5; color: #000; }
.scope-mode-btn.active { background: #1A1A1A; color: #FFF; }

.tool-btn {
  height: 32px; padding: 0 12px;
  border: 1px solid #E0E0E0; background: #FFF; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; gap: 6px;
  cursor: pointer; color: #666; transition: all 0.2s; font-size: 13px;
}
.tool-btn:hover { background: #F5F5F5; color: #000; border-color: #CCC; }
.tool-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.tool-btn:disabled:hover { background: #FFF; color: #666; border-color: #E0E0E0; }
.tool-btn .btn-text { font-size: 12px; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.graph-container { width: 100%; height: 100%; }
.graph-view, .graph-svg { width: 100%; height: 100%; display: block; }

.graph-state {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  text-align: center; color: #999;
}
.empty-icon { font-size: 48px; margin-bottom: 16px; opacity: 0.2; }
.empty-icon.error-icon { opacity: 0.6; color: #E53935; }

/* 实体类型弹层（从 header 工具按钮展开） */
.legend-control { position: relative; }
.legend-popover {
  position: absolute; top: calc(100% + 8px); right: 0; z-index: 20;
  background: #FFF; padding: 12px 14px; border-radius: 8px;
  border: 1px solid #EAEAEA; box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}
.legend-items { display: flex; flex-wrap: wrap; gap: 8px 10px; max-width: 280px; }
.legend-item {
  display: flex; align-items: center; gap: 6px; font-size: 12px; color: #555;
  cursor: pointer; padding: 3px 8px; border-radius: 12px;
  border: 1px solid transparent; transition: all 0.15s;
}
.legend-item:hover { background: #F5F5F5; }
.legend-item.active { background: #FCE4EC; border-color: #E91E63; color: #E91E63; font-weight: 600; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.legend-label { white-space: nowrap; }

/* 详情面板 */
.detail-panel {
  position: absolute; top: 60px; right: 12px; width: min(340px, calc(100% - 24px));
  box-sizing: border-box;
  max-height: calc(100% - 100px);
  background: #FFF; border: 1px solid #EAEAEA; border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.1); overflow: hidden;
  font-family: 'Noto Sans SC', system-ui, sans-serif; font-size: 13px;
  z-index: 20; display: flex; flex-direction: column;
}
.detail-panel-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 16px; background: #FAFAFA; border-bottom: 1px solid #EEE; flex-shrink: 0;
}
.detail-title { font-weight: 600; color: #333; font-size: 14px; flex: 1; }
.detail-type-badge {
  padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 500;
  color: #fff; margin-left: 0; margin-right: 8px;
}
.detail-close {
  background: none; border: none; font-size: 20px; cursor: pointer;
  color: #999; line-height: 1; padding: 0; transition: color 0.2s;
}
.detail-close:hover { color: #333; }
.detail-content {
  padding: 16px; overflow-y: auto; flex: 1; scroll-behavior: smooth;
  container-type: inline-size;
}

.node-name { font-size: 16px; font-weight: 600; color: #222; margin-bottom: 4px; }
.node-aliases { font-size: 12px; color: #888; margin-bottom: 8px; }
.node-desc { font-size: 13px; line-height: 1.6; color: #444; margin-bottom: 12px; }

.section-title { font-size: 12px; font-weight: 600; color: #666; margin: 12px 0 8px; }

.mention-item {
  padding: 8px 10px; background: #F8F8F8; border: 1px solid #EEE;
  border-radius: 6px; margin-bottom: 6px; cursor: pointer; transition: all 0.15s;
}
.mention-item:hover { background: #F0F0FF; border-color: #C7C7F0; }
.mention-ep { display: inline-block; font-size: 10px; color: #7B2D8E; font-weight: 600; margin-right: 6px; }
.mention-quote { font-size: 12px; color: #444; line-height: 1.5; }
.mention-jump {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; color: #3498db; font-weight: 600; white-space: nowrap;
}
.book-mentions { margin-top: 14px; border-top: 1px solid #F0F0F0; padding-top: 8px; }
.mentions-toggle {
  width: 100%; border: none; background: transparent; padding: 2px 0 8px;
  display: flex; align-items: center; justify-content: space-between;
  color: #666; cursor: pointer;
}
.mentions-toggle .section-title {
  margin: 0; display: inline-flex; align-items: center; gap: 6px;
}
.mentions-list { margin-top: 2px; }

.relationship-statement {
  display: grid;
  grid-template-columns: minmax(72px, 1fr) minmax(104px, 1.2fr) minmax(72px, 1fr);
  gap: 0; align-items: center; margin-bottom: 12px;
}
.relationship-part {
  min-width: 0; text-align: center;
}
.relationship-part strong {
  display: block; color: #222; font-size: 12px; line-height: 1.35;
  overflow-wrap: anywhere;
}
.relationship-part.endpoint {
  align-self: stretch; display: flex; flex-direction: column; padding: 10px 8px;
  border: 1px solid #E8E8E8; border-radius: 7px; background: #F8F8F8;
  justify-content: center; position: relative; z-index: 1;
}
.relationship-part.endpoint.source { border-color: #D7E1EA; background: #F7FAFC; }
.relationship-part.endpoint.target { border-color: #E6DDE9; background: #FBF8FC; }
.relationship-connector {
  min-width: 0; align-self: stretch; display: grid;
  grid-template-rows: minmax(0, 1fr) 14px; gap: 3px; align-items: end;
  padding: 4px 7px 0; text-align: center;
}
.relationship-part.predicate { align-self: end; padding: 0 2px; }
.relationship-part.predicate strong { color: #7B2D8E; }
.relationship-arrow {
  position: relative; display: block; width: 100%; height: 14px;
}
.relationship-arrow::before {
  content: ''; position: absolute; left: 0; right: 7px; top: 6px;
  height: 2px; border-radius: 2px; background: #7B2D8E;
}
.relationship-arrow::after {
  content: ''; position: absolute; right: 0; top: 2px;
  width: 0; height: 0; border-top: 5px solid transparent;
  border-bottom: 5px solid transparent; border-left: 8px solid #7B2D8E;
}
.relationship-statement.compact {
  grid-template-columns: minmax(62px, 1fr) minmax(92px, 1.15fr) minmax(62px, 1fr);
  margin-bottom: 8px;
}
.relationship-statement.compact .relationship-part.endpoint { padding: 7px 6px; }
.relationship-statement.compact .relationship-part strong { font-size: 11px; }

@container (max-width: 290px) {
  .relationship-statement,
  .relationship-statement.compact {
    grid-template-columns: minmax(0, 1fr);
  }
  .relationship-connector {
    grid-template-rows: auto 28px; padding: 4px 0;
  }
  .relationship-arrow { width: 16px; height: 28px; justify-self: center; }
  .relationship-arrow::before {
    left: 7px; right: auto; top: 0; bottom: 7px; width: 2px; height: auto;
  }
  .relationship-arrow::after {
    left: 3px; right: auto; top: auto; bottom: 0;
    border-top: 8px solid #7B2D8E; border-right: 5px solid transparent;
    border-bottom: 0; border-left: 5px solid transparent;
  }
}

/* Edge Reel */
.edge-reel { margin-top: 14px; border-top: 1px solid #F0F0F0; padding-top: 8px; }
.reel-header { display: flex; align-items: center; justify-content: space-between; }
.reel-hint { font-size: 11px; color: #aaa; margin-bottom: 8px; }
.reel-list { }
.reel-item {
  padding: 10px; border: 1px solid #EEE; border-radius: 8px; margin-bottom: 8px;
  cursor: pointer; transition: all 0.2s; background: #FFF;
}
.reel-item:hover { border-color: #D6C7E0; }
.reel-item.active {
  border-color: #E91E63; background: #FFF5F8; box-shadow: 0 2px 10px rgba(233,30,99,0.12);
}
.reel-fact { font-size: 12px; color: #555; line-height: 1.5; }
.reel-quote {
  margin-top: 6px; font-size: 12px; color: #666; line-height: 1.5;
  background: #F8F8F8; padding: 6px 8px; border-radius: 6px;
}
.reel-quote:hover { background: #F0F0FF; }
.reel-quote-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.graph-building-hint {
  position: absolute; bottom: 24px; left: 50%; transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.65); backdrop-filter: blur(8px); color: #fff;
  padding: 10px 20px; border-radius: 30px; font-size: 13px;
  display: flex; align-items: center; gap: 10px; z-index: 100; font-weight: 500;
}
.graph-progress-text {
  font-family: monospace; font-size: 12px; opacity: 0.85;
  padding-left: 8px; border-left: 1px solid rgba(255,255,255,0.3);
}
.graph-error-hint {
  background: rgba(178, 34, 52, 0.85); max-width: 80%;
}
.graph-error-hint span:not(.error-icon) {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.graph-error-hint .error-icon { flex-shrink: 0; }
.extract-retry-btn {
  height: 26px; padding: 0 10px; border: 1px solid rgba(255,255,255,0.5);
  border-radius: 6px; background: rgba(255,255,255,0.16); color: #fff;
  cursor: pointer; font-size: 12px; font-weight: 700; white-space: nowrap; flex-shrink: 0;
}
.extract-retry-btn:hover { background: rgba(255,255,255,0.28); border-color: rgba(255,255,255,0.75); }
.state-retry-btn {
  margin-top: 12px; background: #1A1A1A; border-color: #1A1A1A; color: #fff;
}
.state-retry-btn:hover { background: #FF4500; border-color: #FF4500; }
.memory-icon-wrapper { display: flex; align-items: center; animation: breathe 2s ease-in-out infinite; }
.memory-icon { width: 18px; height: 18px; color: #4CAF50; }
@keyframes breathe {
  0%, 100% { opacity: 0.7; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.15); }
}

.loading-spinner {
  width: 40px; height: 40px; border: 3px solid #E0E0E0; border-top-color: #7B2D8E;
  border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 16px;
}

:deep(.node-unseen) { animation: nodePulse 1.6s ease-in-out infinite; }
@keyframes nodePulse {
  0%, 100% { filter: drop-shadow(0 0 0 rgba(233,30,99,0)); }
  50% { filter: drop-shadow(0 0 6px rgba(233,30,99,0.7)); }
}

.tool-btn.active {
  background: #1A1A1A; color: #fff; border-color: #1A1A1A;
}
.tool-btn.active:hover { background: #000; color: #fff; }

.legend-unread {
  margin-top: 8px; padding-top: 8px; border-top: 1px solid #EEE;
  font-size: 11px; color: #E91E63; font-weight: 600;
}

.detail-seen-btn {
  margin-right: 10px;
  border: 1px solid #D6C7E0; background: #FFF; color: #7B2D8E;
  border-radius: 12px; padding: 3px 10px; font-size: 11px; font-weight: 600;
  cursor: pointer; white-space: nowrap; transition: all 0.15s;
}
.detail-seen-btn:hover { background: #F5F0F8; }
.detail-seen-btn.seen { background: #F0EAF5; color: #7B2D8E; border-color: #C9B3D9; }
</style>
