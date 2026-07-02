<template>
  <div class="graph-panel">
    <div class="panel-header">
      <span class="panel-title">{{ $t('graph.panelTitle') }}</span>
      <div class="header-tools">
        <button class="tool-btn" @click="$emit('refresh')" :disabled="loading" :title="$t('graph.refreshGraph')">
          <span class="icon-refresh" :class="{ 'spinning': loading }">↻</span>
          <span class="btn-text">{{ $t('graph.refreshGraph') }}</span>
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
          {{ $t('graph.realtimeUpdating') }}
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
          <div v-if="selectedItem.type === 'node'" class="detail-content">
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
                <button class="reel-play" @click="toggleAutoplay" :title="$t('graph.autoScroll')">
                  {{ autoplay ? '⏸' : '▶' }}
                </button>
              </div>
              <div class="reel-hint">{{ $t('graph.reelHint') }}</div>
              <div class="reel-list" ref="reelList" @scroll="onReelScroll">
                <div
                  v-for="(er, i) in nodeEdges"
                  :key="er.edge.id"
                  class="reel-item"
                  :class="{ active: i === activeReelIndex }"
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

      <div v-else class="graph-state">
        <div class="empty-icon">❖</div>
        <p class="empty-text">{{ $t('graph.emptyReveal') }}</p>
      </div>
    </div>

    <div v-if="hasGraph && entityTypes.length" class="graph-legend">
      <span class="legend-title">{{ $t('graph.entityTypes') }}</span>
      <div class="legend-items">
        <div class="legend-item" v-for="type in entityTypes" :key="type.name">
          <span class="legend-dot" :style="{ background: type.color }"></span>
          <span class="legend-label">{{ type.name }}</span>
        </div>
      </div>
      <div class="legend-unread" v-if="unseenNodeCount || unseenEdgeCount">
        {{ $t('graph.unreadNodes', { n: unseenNodeCount }) }} · {{ $t('graph.unreadLinks', { n: unseenEdgeCount }) }}
      </div>
    </div>

    <div v-if="hasGraph" class="edge-labels-toggle">
      <label class="toggle-switch">
        <input type="checkbox" v-model="showEdgeLabels" />
        <span class="slider"></span>
      </label>
      <span class="toggle-label">{{ $t('graph.showEdgeLabels') }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as d3 from 'd3'

const props = defineProps({
  graphData: Object,        // { nodes, edges }
  currentEpisode: Number,   // 阅读进度（揭示阈值）
  episodes: Array,          // 章节元数据（用于标题）
  loading: Boolean,
  seenNodes: { type: Array, default: () => [] },  // 已查看节点 id
  seenEdges: { type: Array, default: () => [] },  // 已查看关系 id
  selectRequest: { type: Object, default: null }  // 外部请求选中 { type, id, nonce }
})

const emit = defineEmits([
  'refresh', 'toggle-maximize', 'jump',
  'seen-node', 'seen-edge', 'set-node-seen', 'set-edge-seen'
])

const graphContainer = ref(null)
const graphSvg = ref(null)
const reelList = ref(null)
const selectedItem = ref(null)
const showEdgeLabels = ref(true)
const activeReelIndex = ref(0)
const autoplay = ref(false)
const focusUnread = ref(false)

// 已查看集合（快速查询）
const seenNodeSet = computed(() => new Set(props.seenNodes))
const seenEdgeSet = computed(() => new Set(props.seenEdges))

const COLORS = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C', '#3498db', '#9b59b6', '#27ae60', '#f39c12']

// 位置缓存，保证逐章展开时已有节点位置稳定
const positionCache = new Map()

// ---------- 可见子图（按阅读进度过滤） ----------
const visibleNodes = computed(() => {
  const nodes = props.graphData?.nodes || []
  const upto = props.currentEpisode ?? 0
  return nodes.filter(n => (n.first_episode ?? 0) <= upto)
})

const visibleEdges = computed(() => {
  const upto = props.currentEpisode ?? 0
  const ids = new Set(visibleNodes.value.map(n => n.id))
  return (props.graphData?.edges || []).filter(
    e => (e.first_episode ?? 0) <= upto && ids.has(e.source) && ids.has(e.target)
  )
})

const hasGraph = computed(() => visibleNodes.value.length > 0)

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

// 当前可见范围内的未读数量
const unseenNodeCount = computed(() =>
  visibleNodes.value.filter(n => !seenNodeSet.value.has(n.id)).length
)
const unseenEdgeCount = computed(() =>
  visibleEdges.value.filter(e => !seenEdgeSet.value.has(e.id)).length
)

// 当前选中项是否已读
const selectedSeen = computed(() => {
  if (!selectedItem.value) return false
  if (selectedItem.value.type === 'node') return seenNodeSet.value.has(selectedItem.value.node.id)
  return seenEdgeSet.value.has(selectedItem.value.edge.id)
})

const toggleSelectedSeen = () => {
  if (!selectedItem.value) return
  const value = !selectedSeen.value
  if (selectedItem.value.type === 'node') {
    emit('set-node-seen', { id: selectedItem.value.node.id, value })
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
  autoplay.value = false
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
  const dimNode = (id) => focusUnread.value && seenNodeSet.value.has(id) && !exNodes.has(id)
  const dimEdge = (id) => focusUnread.value && seenEdgeSet.value.has(id) && !exEdges.has(id)
  if (nodeSel) {
    nodeSel
      .attr('r', d => seenNodeSet.value.has(d.id) ? 9 : 12)
      .classed('node-unseen', d => !seenNodeSet.value.has(d.id))
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
}

const clearGraphHighlight = () => {
  if (nodeSel) nodeSel.attr('stroke', '#fff').attr('stroke-width', 2.5)
  if (linkSel) linkSel.attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
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

const highlightNode = (nodeId) => {
  clearGraphHighlight()
  if (nodeSel) {
    nodeSel.filter(d => d.id === nodeId).attr('stroke', '#E91E63').attr('stroke-width', 4)
  }
  if (linkSel) {
    linkSel.filter(d => d.data.source === nodeId || d.data.target === nodeId)
      .attr('stroke', '#E91E63').attr('stroke-width', 2.5)
  }
}

const selectNode = (node) => {
  selectedItem.value = {
    type: 'node',
    node,
    color: colorForType(node.type)
  }
  activeReelIndex.value = 0
  autoplay.value = false
  emit('seen-node', node.id)
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
  if (!req || !req.id) return
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
    nodeSel.attr('cx', d => d.x).attr('cy', d => d.y)
    nodeLabels.attr('x', d => d.x).attr('y', d => d.y)
    nodes.forEach(n => positionCache.set(n.id, { x: n.x, y: n.y }))
  })

  svg.on('click', () => { closeDetailPanel() })

  // 恢复选中高亮
  if (selectedItem.value) {
    if (selectedItem.value.type === 'node') highlightNode(selectedItem.value.node.id)
    else highlightEdge(selectedItem.value.edge.id)
  }
}

// ---------- Edge Reel 交互 ----------
const highlightActiveReel = () => {
  const er = nodeEdges.value[activeReelIndex.value]
  if (er) {
    emit('seen-edge', er.edge.id)
    highlightEdge(er.edge.id)
  }
}

const setActiveReel = (i) => {
  activeReelIndex.value = i
  highlightActiveReel()
  scrollReelToActive()
}

const scrollReelToActive = () => {
  const list = reelList.value
  if (!list) return
  const item = list.children[activeReelIndex.value]
  if (item) list.scrollTo({ top: item.offsetTop - list.offsetTop - 8, behavior: 'smooth' })
}

let reelScrollRaf = null
const onReelScroll = () => {
  if (autoplay.value) return
  if (reelScrollRaf) cancelAnimationFrame(reelScrollRaf)
  reelScrollRaf = requestAnimationFrame(() => {
    const list = reelList.value
    if (!list) return
    const center = list.scrollTop + list.clientHeight / 2
    let best = 0, bestDist = Infinity
    Array.from(list.children).forEach((child, i) => {
      const mid = child.offsetTop - list.offsetTop + child.clientHeight / 2
      const dist = Math.abs(mid - center)
      if (dist < bestDist) { bestDist = dist; best = i }
    })
    if (best !== activeReelIndex.value) {
      activeReelIndex.value = best
      highlightActiveReel()
    }
  })
}

let autoplayTimer = null
const toggleAutoplay = () => {
  autoplay.value = !autoplay.value
  if (autoplay.value) {
    autoplayTimer = setInterval(() => {
      if (!nodeEdges.value.length) return
      activeReelIndex.value = (activeReelIndex.value + 1) % nodeEdges.value.length
      highlightActiveReel()
      scrollReelToActive()
    }, 2000)
  } else if (autoplayTimer) {
    clearInterval(autoplayTimer)
    autoplayTimer = null
  }
}

const onKey = (e) => {
  if (!selectedItem.value || selectedItem.value.type !== 'node' || !nodeEdges.value.length) return
  if (e.key === 'ArrowDown') { e.preventDefault(); setActiveReel((activeReelIndex.value + 1) % nodeEdges.value.length) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveReel((activeReelIndex.value - 1 + nodeEdges.value.length) % nodeEdges.value.length) }
}

// ---------- watchers ----------
const revealKey = computed(() => `${visibleNodes.value.length}_${visibleEdges.value.length}_${props.currentEpisode}`)
watch(revealKey, () => { nextTick(renderGraph) })
watch(() => props.graphData, () => { nextTick(renderGraph) }, { deep: false })

watch(showEdgeLabels, (v) => {
  if (linkLabelSel) linkLabelSel.style('display', v ? 'block' : 'none')
  if (linkLabelBgSel) linkLabelBgSel.style('display', v ? 'block' : 'none')
})

// 已读状态 / 专注未读 / 选中项变化时，仅更新样式，避免整图重排
watch([() => props.seenNodes, () => props.seenEdges, focusUnread, () => selectedItem.value], () => {
  applySeenStyles()
})

const handleResize = () => nextTick(renderGraph)

onMounted(() => {
  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', onKey)
  nextTick(renderGraph)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('keydown', onKey)
  if (autoplayTimer) clearInterval(autoplayTimer)
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
  padding: 16px 20px;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(to bottom, rgba(255,255,255,0.95), rgba(255,255,255,0));
  pointer-events: none;
}

.panel-title { font-size: 14px; font-weight: 600; color: #333; pointer-events: auto; }
.header-tools { pointer-events: auto; display: flex; gap: 10px; align-items: center; }

.tool-btn {
  height: 32px; padding: 0 12px;
  border: 1px solid #E0E0E0; background: #FFF; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; gap: 6px;
  cursor: pointer; color: #666; transition: all 0.2s; font-size: 13px;
}
.tool-btn:hover { background: #F5F5F5; color: #000; border-color: #CCC; }
.tool-btn .btn-text { font-size: 12px; }
.icon-refresh.spinning { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.graph-container { width: 100%; height: 100%; }
.graph-view, .graph-svg { width: 100%; height: 100%; display: block; }

.graph-state {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  text-align: center; color: #999;
}
.empty-icon { font-size: 48px; margin-bottom: 16px; opacity: 0.2; }

.graph-legend {
  position: absolute; bottom: 24px; left: 24px;
  background: rgba(255,255,255,0.95); padding: 12px 16px; border-radius: 8px;
  border: 1px solid #EAEAEA; box-shadow: 0 4px 16px rgba(0,0,0,0.06); z-index: 10;
}
.legend-title {
  display: block; font-size: 11px; font-weight: 600; color: #E91E63;
  margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px;
}
.legend-items { display: flex; flex-wrap: wrap; gap: 10px 16px; max-width: 320px; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #555; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.legend-label { white-space: nowrap; }

.edge-labels-toggle {
  position: absolute; top: 60px; right: 20px;
  display: flex; align-items: center; gap: 10px;
  background: #FFF; padding: 8px 14px; border-radius: 20px;
  border: 1px solid #E0E0E0; box-shadow: 0 2px 8px rgba(0,0,0,0.04); z-index: 10;
}
.toggle-switch { position: relative; display: inline-block; width: 40px; height: 22px; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.slider {
  position: absolute; cursor: pointer; inset: 0;
  background-color: #E0E0E0; border-radius: 22px; transition: 0.3s;
}
.slider:before {
  position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px;
  background-color: white; border-radius: 50%; transition: 0.3s;
}
input:checked + .slider { background-color: #7B2D8E; }
input:checked + .slider:before { transform: translateX(18px); }
.toggle-label { font-size: 12px; color: #666; }

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
.detail-content { padding: 16px; overflow-y: auto; flex: 1; }

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
.reel-play {
  width: 26px; height: 26px; border-radius: 50%; border: 1px solid #E0E0E0;
  background: #FFF; cursor: pointer; color: #7B2D8E; font-size: 12px;
}
.reel-play:hover { background: #F5F0F8; }
.reel-hint { font-size: 11px; color: #aaa; margin-bottom: 8px; }
.reel-list { max-height: 260px; overflow-y: auto; scroll-behavior: smooth; }
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
  position: absolute; bottom: 24px; left: 50%; transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.65); backdrop-filter: blur(8px); color: #fff;
  padding: 10px 20px; border-radius: 30px; font-size: 13px;
  display: flex; align-items: center; gap: 10px; z-index: 100; font-weight: 500;
}
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
  background: #7B2D8E; color: #fff; border-color: #7B2D8E;
}
.tool-btn.active:hover { background: #6a2679; color: #fff; }

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
