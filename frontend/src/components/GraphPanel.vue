<template>
  <div class="graph-panel">
    <div class="panel-header">
      <div class="header-left">
        <span class="panel-title">{{ $t('graph.panelTitle') }}</span>
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
                :key="type.name"
                :class="{ active: activeType === type.name }"
                @click="highlightType(type.name)"
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
        <button class="tool-btn" @click="$emit('toggle-maximize')" :title="$t('graph.toggleMaximize')">
          <span class="icon-maximize">⛶</span>
        </button>
      </div>
    </div>

    <div class="graph-container" ref="graphContainer">
      <div v-if="hasGraph" class="graph-view">
        <svg ref="graphSvg" class="graph-svg"></svg>

        <div v-if="loading" class="graph-building-hint">
          <div class="memory-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="memory-icon">
              <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-4.04z" />
            </svg>
          </div>
          <span>{{ $t('graph.realtimeUpdating') }}</span>
          <span v-if="extractProgressText" class="graph-progress-text">{{ extractProgressText }}</span>
        </div>
        <div v-else-if="extractErrorText" class="graph-building-hint graph-error-hint" :title="extractErrorText">
          <span class="error-icon">⚠</span>
          <span>{{ $t('graph.extractError', { error: extractErrorText }) }}</span>
        </div>

        <!-- 详情面板 -->
        <div v-if="selectedItem" class="detail-panel">
          <div class="detail-panel-header">
            <button
              v-if="navDepth"
              class="detail-back-btn"
              @click="$emit('go-back')"
              :title="$t('reader.back')"
            >
              <span class="detail-back-arrow">↩</span>
              <span class="detail-back-depth">{{ navDepth }}</span>
            </button>
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

            <div class="mentions" v-if="selectedItem.node.mentions && selectedItem.node.mentions.length">
              <div class="section-title">{{ $t('graph.originalText') }}</div>
              <div
                v-for="(m, i) in selectedItem.node.mentions"
                :key="'nm' + i"
                class="mention-item"
                @click="jumpTo(m)"
              >
                <span class="mention-ep">{{ episodeTitle(m.episode) }}</span>
                <span class="mention-quote">“{{ m.quote }}”</span>
                <span class="mention-jump">{{ $t('graph.readInBook') }} →</span>
              </div>
            </div>

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
                  <div class="reel-item-relation">
                    <span class="reel-dir">{{ er.outgoing ? '→' : '←' }}</span>
                    <span class="reel-label">{{ er.edge.label }}</span>
                    <span class="reel-neighbor">{{ er.neighborName }}</span>
                  </div>
                  <div class="reel-fact" v-if="er.edge.fact">{{ er.edge.fact }}</div>
                  <div
                    v-if="er.edge.mentions && er.edge.mentions.length"
                    class="reel-quote"
                    @click.stop="jumpTo(er.edge.mentions[0])"
                  >
                    “{{ er.edge.mentions[0].quote }}” <span class="mention-jump">{{ $t('graph.readInBook') }} →</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 边详情 -->
          <div v-else class="detail-content">
            <div class="edge-relation-header">
              {{ selectedItem.sourceName }} <span class="edge-arrow">→ {{ selectedItem.edge.label }} →</span> {{ selectedItem.targetName }}
            </div>
            <div class="node-desc" v-if="selectedItem.edge.fact">{{ selectedItem.edge.fact }}</div>
            <div class="mentions" v-if="selectedItem.edge.mentions && selectedItem.edge.mentions.length">
              <div class="section-title">{{ $t('graph.originalText') }}</div>
              <div
                v-for="(m, i) in selectedItem.edge.mentions"
                :key="'em' + i"
                class="mention-item"
                @click="jumpTo(m)"
              >
                <span class="mention-ep">{{ episodeTitle(m.episode) }}</span>
                <span class="mention-quote">“{{ m.quote }}”</span>
                <span class="mention-jump">{{ $t('graph.readInBook') }} →</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="loading" class="graph-state">
        <div class="loading-spinner"></div>
        <p>{{ $t('graph.graphDataLoading') }}</p>
      </div>

      <div v-else-if="extractErrorText" class="graph-state">
        <div class="empty-icon error-icon" :title="extractErrorText">⚠</div>
        <p class="empty-text">{{ $t('graph.extractError', { error: extractErrorText }) }}</p>
      </div>

      <div v-else class="graph-state">
        <div class="empty-icon">❖</div>
        <p class="empty-text">{{ $t('graph.emptyReveal') }}</p>
      </div>
    </div>

    <!-- 底部条：视图范围（累计/本章）+ 防剧透揭示控制 -->
    <div v-if="hasGraph" class="reveal-footer">
      <div class="scope-seg">
        <button class="scope-seg-btn" :class="{ active: !chapterOnly }" @click="chapterOnly = false">{{ $t('graph.cumulative') }}</button>
        <button class="scope-seg-btn" :class="{ active: chapterOnly }" @click="chapterOnly = true">{{ $t('graph.chapterOnly') }}</button>
      </div>
      <!-- 仅累计视图显示，控制图谱展开到第几章（与图谱加载进度无关） -->
      <div v-if="episodeCount && !chapterOnly" class="reveal-inline" :title="$t('graph.revealBarCaption')">
        <span class="reveal-inline-label" :title="revealEpisodeTitle">
          {{ $t('graph.revealBarLabel', { current: revealDisplay, total: episodeCount }) }}
        </span>
        <button class="reveal-step" @click="stepReveal(-1)" :title="$t('graph.revealDecrease')">−</button>
        <input
          class="reveal-slider"
          type="range"
          min="1"
          :max="Math.max(episodeCount, 1)"
          :value="revealDisplay"
          :disabled="!episodeCount"
          @input="setRevealFromInput"
        />
        <button class="reveal-step" @click="stepReveal(1)" :title="$t('graph.revealIncrease')">+</button>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as d3 from 'd3'
import { graphDensityMessage, shouldAutoHideEdgeLabels } from '../utils/graphPerformance'
import { clampRevealMax } from '../utils/revealProgress'

const props = defineProps({
  graphData: Object,        // { nodes, edges }
  currentEpisode: Number,   // 阅读进度（揭示阈值，累计视图）
  viewEpisode: Number,      // 当前正在阅读的章节（本章视图）
  episodes: Array,          // 章节元数据（用于标题）
  loading: Boolean,
  extractProgress: { type: Object, default: null },
  seenEdges: { type: Array, default: () => [] },  // 已查看关系 id（节点已读由此派生）
  selectRequest: { type: Object, default: null },  // 外部请求选中 { type, id, nonce }
  latestReadEpisode: { type: Number, default: 0 },
  navDepth: { type: Number, default: 0 }  // 阅读导航返回栈深度
})

const emit = defineEmits([
  'toggle-maximize', 'jump',
  'seen-edge', 'set-edge-seen', 'set-reveal-max', 'select-change', 'go-back'
])

const graphContainer = ref(null)
const graphSvg = ref(null)
const reelList = ref(null)
const detailContent = ref(null)
const selectedItem = ref(null)
const showEdgeLabels = ref(true)
const edgeLabelsUserOverrode = ref(false)
const activeReelIndex = ref(0)
const focusUnread = ref(false)
// 只显示当前章节的图谱（关系/实体过多时更快）；关闭时为累计视图
const chapterOnly = ref(false)
// 实体类型图例：以 header 弹层展示，点击某类型高亮该类全部实体
const legendOpen = ref(false)
const legendControl = ref(null)
const activeType = ref(null)

// 已查看集合（快速查询）
const seenEdgeSet = computed(() => new Set(props.seenEdges))

const COLORS = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C', '#3498db', '#9b59b6', '#27ae60', '#f39c12']

// 高亮配色：选中节点/相连边用 ACCENT，正在走查的边用 ACTIVE（更醒目）
const HL_ACCENT = '#E91E63'
const HL_ACTIVE = '#FF4500'

// 位置缓存，保证逐章展开时已有节点位置稳定
const positionCache = new Map()

const episodeCount = computed(() => props.episodes?.length || 0)
const currentRevealIndex = computed(() => clampRevealMax(props.currentEpisode ?? 0, episodeCount.value))
const revealDisplay = computed(() => episodeCount.value ? currentRevealIndex.value + 1 : 0)
const revealEpisodeTitle = computed(() =>
  props.episodes?.[currentRevealIndex.value]?.title || `#${revealDisplay.value}`
)

const emitRevealMax = (idx) => {
  emit('set-reveal-max', clampRevealMax(idx, episodeCount.value))
}

const setRevealFromInput = (e) => {
  emitRevealMax(Number(e.target.value) - 1)
}

const stepReveal = (delta) => {
  emitRevealMax(currentRevealIndex.value + delta)
}

// 向阅读面板同步当前选中项，供其导航历史快照/恢复使用
watch(() => selectedItem.value, (sel) => {
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

const visibleNodes = computed(() => {
  const nodes = props.graphData?.nodes || []
  if (chapterOnly.value) {
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
  const upto = props.currentEpisode ?? 0
  return nodes.filter(n => (n.first_episode ?? 0) <= upto)
})

const visibleEdges = computed(() => {
  const ids = new Set(visibleNodes.value.map(n => n.id))
  const edges = props.graphData?.edges || []
  if (chapterOnly.value) {
    const ep = props.viewEpisode ?? 0
    return edges.filter(e => mentionedIn(e, ep) && ids.has(e.source) && ids.has(e.target))
  }
  const upto = props.currentEpisode ?? 0
  return edges.filter(
    e => (e.first_episode ?? 0) <= upto && ids.has(e.source) && ids.has(e.target)
  )
})

// 节点已读状态：由其（可见）关系派生。无关系视为已读；所有关系已读则已读。
const nodeSeenSet = computed(() => {
  const degree = {}
  const unseen = {}
  visibleEdges.value.forEach(e => {
    degree[e.source] = (degree[e.source] || 0) + 1
    degree[e.target] = (degree[e.target] || 0) + 1
    if (!seenEdgeSet.value.has(e.id)) {
      unseen[e.source] = (unseen[e.source] || 0) + 1
      unseen[e.target] = (unseen[e.target] || 0) + 1
    }
  })
  const seen = new Set()
  visibleNodes.value.forEach(n => {
    if (!(unseen[n.id] > 0)) seen.add(n.id)
  })
  return seen
})

const hasGraph = computed(() => visibleNodes.value.length > 0)
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

const nodeById = computed(() => {
  const m = {}
  visibleNodes.value.forEach(n => { m[n.id] = n })
  return m
})

const entityTypes = computed(() => {
  const typeMap = {}
  visibleNodes.value.forEach(node => {
    const type = node.type || '—'
    if (!typeMap[type]) {
      typeMap[type] = { name: type, color: COLORS[Object.keys(typeMap).length % COLORS.length] }
    }
  })
  return Object.values(typeMap)
})

const colorForType = (type) => {
  const t = entityTypes.value.find(e => e.name === (type || '—'))
  return t ? t.color : '#999'
}

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
        neighborName: nodeById.value[neighborId]?.name || '—'
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
let svgSel = null
let zoomBehavior = null

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
      .filter(n => (n.type || '—') === activeType.value)
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
  const p = positionCache.get(id)
  if (p) centerOnPoint(p.x, p.y)
}

const centerOnEdge = (edge) => {
  const a = positionCache.get(edge.source)
  const b = positionCache.get(edge.target)
  if (a && b) centerOnPoint((a.x + b.x) / 2, (a.y + b.y) / 2)
  else if (a) centerOnPoint(a.x, a.y)
}

// 外部（阅读面板反向链接）请求选中并居中某节点/关系
watch(() => props.selectRequest, (req) => {
  if (!req) return
  if (!req.type || !req.id) { closeDetailPanel(); return }
  if (req.type === 'node') {
    const n = visibleNodes.value.find(x => x.id === req.id)
    if (n) { selectNode(n); nextTick(() => centerOnNode(n.id)) }
  } else if (req.type === 'edge') {
    const e = visibleEdges.value.find(x => x.id === req.id)
    if (e) { selectEdge(e); nextTick(() => centerOnEdge(e)) }
  }
})

const renderGraph = () => {
  if (!graphSvg.value || !graphContainer.value) return
  if (simulation) simulation.stop()

  const container = graphContainer.value
  const width = container.clientWidth
  const height = container.clientHeight

  const svg = d3.select(graphSvg.value)
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)
  svg.selectAll('*').remove()

  const rawNodes = visibleNodes.value
  const rawEdges = visibleEdges.value
  if (rawNodes.length === 0) return

  const nodes = rawNodes.map(n => {
    const cached = positionCache.get(n.id)
    return {
      id: n.id,
      name: n.name || '—',
      type: n.type || '—',
      data: n,
      x: cached ? cached.x : width / 2 + (Math.random() - 0.5) * 60,
      y: cached ? cached.y : height / 2 + (Math.random() - 0.5) * 60
    }
  })

  // 计算重复边曲率
  const pairCount = {}
  rawEdges.forEach(e => {
    if (e.source === e.target) return
    const key = [e.source, e.target].sort().join('_')
    pairCount[key] = (pairCount[key] || 0) + 1
  })
  const pairIdx = {}
  const edges = rawEdges.map(e => {
    const selfLoop = e.source === e.target
    let curvature = 0
    let pairTotal = 1
    if (!selfLoop) {
      const key = [e.source, e.target].sort().join('_')
      pairTotal = pairCount[key]
      const idx = pairIdx[key] || 0
      pairIdx[key] = idx + 1
      if (pairTotal > 1) {
        curvature = ((idx / (pairTotal - 1)) - 0.5) * 1.5
        if (e.source > e.target) curvature = -curvature
      }
    }
    return {
      source: e.source,
      target: e.target,
      name: e.label || '—',
      curvature,
      selfLoop,
      pairTotal,
      data: e
    }
  })

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(d => 140 + ((d.pairTotal || 1) - 1) * 40))
    .force('charge', d3.forceManyBody().strength(-380))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide(46))
    .force('x', d3.forceX(width / 2).strength(0.04))
    .force('y', d3.forceY(height / 2).strength(0.04))

  const g = svg.append('g')
  svgSel = svg
  zoomBehavior = d3.zoom().extent([[0, 0], [width, height]]).scaleExtent([0.1, 4]).on('zoom', (event) => {
    g.attr('transform', event.transform)
  })
  svg.call(zoomBehavior)

  const linkGroup = g.append('g').attr('class', 'links')

  const getLinkPath = (d) => {
    const sx = d.source.x, sy = d.source.y
    const tx = d.target.x, ty = d.target.y
    if (d.selfLoop) {
      const r = 28
      return `M${sx + 8},${sy - 4} A${r},${r} 0 1,1 ${sx + 8},${sy + 4}`
    }
    if (d.curvature === 0) return `M${sx},${sy} L${tx},${ty}`
    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy) || 1
    const off = Math.max(35, dist * 0.3)
    const cx = (sx + tx) / 2 + (-dy / dist) * d.curvature * off
    const cy = (sy + ty) / 2 + (dx / dist) * d.curvature * off
    return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`
  }

  const getMid = (d) => {
    const sx = d.source.x, sy = d.source.y
    const tx = d.target.x, ty = d.target.y
    if (d.selfLoop) return { x: sx + 60, y: sy }
    if (d.curvature === 0) return { x: (sx + tx) / 2, y: (sy + ty) / 2 }
    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy) || 1
    const off = Math.max(35, dist * 0.3)
    const cx = (sx + tx) / 2 + (-dy / dist) * d.curvature * off
    const cy = (sy + ty) / 2 + (dx / dist) * d.curvature * off
    return { x: 0.25 * sx + 0.5 * cx + 0.25 * tx, y: 0.25 * sy + 0.5 * cy + 0.25 * ty }
  }

  linkSel = linkGroup.selectAll('path').data(edges).enter().append('path')
    .attr('stroke', '#C0C0C0')
    .attr('stroke-width', 1.5)
    .attr('fill', 'none')
    .style('cursor', 'pointer')
    .on('click', (event, d) => { event.stopPropagation(); selectEdge(d.data) })

  linkLabelBgSel = linkGroup.selectAll('rect').data(edges).enter().append('rect')
    .attr('fill', 'rgba(255,255,255,0.95)').attr('rx', 3).attr('ry', 3)
    .style('cursor', 'pointer').style('pointer-events', 'all')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', (event, d) => { event.stopPropagation(); selectEdge(d.data) })

  linkLabelSel = linkGroup.selectAll('text').data(edges).enter().append('text')
    .text(d => d.name)
    .attr('font-size', '9px').attr('fill', '#666')
    .attr('text-anchor', 'middle').attr('dominant-baseline', 'middle')
    .style('cursor', 'pointer').style('pointer-events', 'all')
    .style('font-family', 'system-ui, sans-serif')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', (event, d) => { event.stopPropagation(); selectEdge(d.data) })

  const nodeGroup = g.append('g').attr('class', 'nodes')
  nodeSel = nodeGroup.selectAll('circle').data(nodes).enter().append('circle')
    .attr('r', 10)
    .attr('fill', d => colorForType(d.type))
    .attr('stroke', '#fff').attr('stroke-width', 2.5)
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (event, d) => { d.fx = d.x; d.fy = d.y; d._sx = event.x; d._sy = event.y; d._drag = false })
      .on('drag', (event, d) => {
        const dist = Math.hypot(event.x - d._sx, event.y - d._sy)
        if (!d._drag && dist > 3) { d._drag = true; simulation.alphaTarget(0.3).restart() }
        if (d._drag) { d.fx = event.x; d.fy = event.y }
      })
      .on('end', (event, d) => { if (d._drag) simulation.alphaTarget(0); d.fx = null; d.fy = null; d._drag = false })
    )
    .on('click', (event, d) => { event.stopPropagation(); selectNode(d.data) })

  const nodeLabels = nodeGroup.selectAll('text').data(nodes).enter().append('text')
    .text(d => d.name.length > 10 ? d.name.slice(0, 10) + '…' : d.name)
    .attr('font-size', '11px').attr('fill', '#333').attr('font-weight', '500')
    .attr('dx', 14).attr('dy', 4)
    .style('pointer-events', 'none').style('font-family', 'system-ui, sans-serif')
  nodeLabelSel = nodeLabels

  // 应用已读/未读样式
  applySeenStyles()

  simulation.on('tick', () => {
    linkSel.attr('d', getLinkPath)
    if (showEdgeLabels.value) {
      linkLabelSel.each(function (d) {
        const mid = getMid(d)
        d3.select(this).attr('x', mid.x).attr('y', mid.y)
      })
      linkLabelBgSel.each(function (d, i) {
        const mid = getMid(d)
        const textEl = linkLabelSel.nodes()[i]
        const bbox = textEl.getBBox()
        d3.select(this)
          .attr('x', mid.x - bbox.width / 2 - 4).attr('y', mid.y - bbox.height / 2 - 2)
          .attr('width', bbox.width + 8).attr('height', bbox.height + 4)
      })
    }
    nodeSel.attr('cx', d => d.x).attr('cy', d => d.y)
    nodeLabels.attr('x', d => d.x).attr('y', d => d.y)
    nodes.forEach(n => positionCache.set(n.id, { x: n.x, y: n.y }))
  })

  svg.on('click', () => { closeDetailPanel() })

  // 恢复选中高亮
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
const revealKey = computed(() => `${visibleNodes.value.length}_${visibleEdges.value.length}_${props.currentEpisode}_${chapterOnly.value ? 'c' + (props.viewEpisode ?? 0) : 'a'}`)
watch(revealKey, () => {
  if (!selectedItemVisible()) selectedItem.value = null
  nextTick(renderGraph)
})
watch(() => props.graphData, () => { nextTick(renderGraph) }, { deep: false })

watch(showEdgeLabels, (v) => {
  if (linkLabelSel) linkLabelSel.style('display', v ? 'block' : 'none')
  if (linkLabelBgSel) linkLabelBgSel.style('display', v ? 'block' : 'none')
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

const handleResize = () => nextTick(renderGraph)

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
  nextTick(renderGraph)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('keydown', onKey)
  document.removeEventListener('mousedown', onDocumentMouseDown)
  if (reelScrollRaf) cancelAnimationFrame(reelScrollRaf)
  if (simulation) simulation.stop()
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
  z-index: 10;
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

/* 底部条：视图范围（累计/本章）+ 防剧透揭示控制，横跨整个面板宽度以避免换行 */
.reveal-footer {
  position: absolute; bottom: 0; left: 0; right: 0; z-index: 10;
  display: flex; align-items: center; justify-content: center; gap: 16px;
  padding: 10px 20px; flex-wrap: wrap;
  background: linear-gradient(to top, rgba(255,255,255,0.95), rgba(255,255,255,0.75) 60%, rgba(255,255,255,0));
}

/* 视图范围分段控件：累计 / 本章 */
.scope-seg {
  display: inline-flex; border: 1px solid #E0E0E0; border-radius: 6px; overflow: hidden;
  background: #FFF; flex-shrink: 0; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.scope-seg-btn {
  height: 30px; padding: 0 14px; border: none; background: #FFF;
  color: #666; cursor: pointer; font-size: 12px; font-weight: 600; white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
.scope-seg-btn + .scope-seg-btn { border-left: 1px solid #E0E0E0; }
.scope-seg-btn:hover { background: #F5F5F5; color: #000; }
.scope-seg-btn.active { background: #1A1A1A; color: #FFF; }

/* 防剧透揭示控制（底部条内，风格与工具按钮一致） */
.reveal-inline {
  display: flex; align-items: center; gap: 8px;
  background: #FFF; border: 1px solid #E0E0E0; border-radius: 6px; padding: 4px 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.reveal-inline-label {
  font-size: 12px; font-weight: 600; color: #444; white-space: nowrap;
}
.reveal-slider { width: 140px; accent-color: #1A1A1A; cursor: pointer; }
.reveal-step {
  width: 22px; height: 22px; border: 1px solid #E0E0E0; border-radius: 5px;
  background: #FFF; color: #555; cursor: pointer; font-size: 14px; line-height: 1; flex-shrink: 0;
}
.reveal-step:hover { background: #F5F5F5; border-color: #CCC; color: #000; }

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
  position: absolute; top: 60px; right: 20px; width: 340px;
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
.detail-back-btn {
  display: inline-flex; align-items: center; gap: 4px;
  background: #FF4500; color: #fff; border: none;
  padding: 4px 6px 4px 8px; border-radius: 14px; cursor: pointer;
  margin-right: 10px; flex-shrink: 0;
  box-shadow: 0 1px 4px rgba(255,69,0,0.3); transition: background 0.15s, transform 0.1s;
}
.detail-back-btn:hover { background: #e63e00; transform: translateY(-1px); }
.detail-back-btn:active { transform: translateY(0); }
.detail-back-arrow { font-size: 15px; line-height: 1; font-weight: 700; }
.detail-back-depth {
  min-width: 16px; height: 16px; padding: 0 4px; border-radius: 8px;
  background: rgba(255,255,255,0.28); color: #fff;
  font-size: 11px; font-weight: 700; line-height: 16px; text-align: center;
}
.detail-content { padding: 16px; overflow-y: auto; flex: 1; scroll-behavior: smooth; }

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
.mention-jump { font-size: 11px; color: #3498db; font-weight: 500; white-space: nowrap; }

.edge-relation-header {
  background: #F8F8F8; padding: 12px; border-radius: 8px; margin-bottom: 12px;
  font-size: 13px; font-weight: 500; color: #333; line-height: 1.5; word-break: break-word;
}
.edge-arrow { color: #7B2D8E; }

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
.reel-item-relation { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.reel-dir { color: #E91E63; font-weight: 700; }
.reel-label { font-size: 12px; font-weight: 600; color: #7B2D8E; }
.reel-neighbor { font-size: 13px; font-weight: 600; color: #222; }
.reel-fact { font-size: 12px; color: #555; line-height: 1.5; }
.reel-quote {
  margin-top: 6px; font-size: 12px; color: #666; line-height: 1.5;
  background: #F8F8F8; padding: 6px 8px; border-radius: 6px;
}
.reel-quote:hover { background: #F0F0FF; }

.graph-building-hint {
  position: absolute; bottom: 68px; left: 50%; transform: translateX(-50%);
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
