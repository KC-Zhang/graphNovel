<template>
  <div
    ref="container"
    class="large-graph-view"
    role="application"
    :aria-label="ariaLabel"
    :aria-busy="status === 'loading'"
    :data-renderer-status="status"
    :data-node-count="nodes.length"
    :data-edge-count="edges.length"
  >
    <div v-if="status === 'error'" class="large-graph-view__message" role="status">
      WebGL graph unavailable
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { entityTypeKey } from '../utils/entityTypes'
import {
  colorWithAlpha,
  graphNodeKey,
  inferLargeGraphLayoutSettings,
  syncGraphologyGraph,
} from '../utils/largeGraph'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  selectedNodeId: { type: [String, Number], default: null },
  selectedEdgeId: { type: [String, Number], default: null },
  typeColors: { type: [Object, Array, Map], default: () => ({}) },
  seenNodeIds: { type: [Array, Set], default: () => [] },
  seenEdgeIds: { type: [Array, Set], default: () => [] },
  focusUnread: Boolean,
  focusedNodeIds: { type: [Array, Set], default: () => [] },
  focusedEdgeIds: { type: [Array, Set], default: () => [] },
  showEdgeLabels: { type: Boolean, default: false },
  layoutEnabled: { type: Boolean, default: true },
  layoutDurationMs: { type: Number, default: 6500 },
  layoutSettings: { type: Object, default: () => ({}) },
  ariaLabel: { type: String, default: 'Knowledge graph' },
})

const emit = defineEmits([
  'select-node', 'select-edge', 'ready', 'renderer-error', 'layout-error',
])
const container = ref(null)
const status = ref('loading')

let graph = null
let renderer = null
let ForceAtlas2Layout = null
let layout = null
let layoutRunning = false
let layoutTimer = null
let layoutStartedAt = 0
let layoutRemainingMs = 0
let resizeObserver = null
let resizeFrame = null
let syncFrame = null
let layoutBootstrapFrame = null
let layoutBootstrapTimer = null
let layoutRuntimePromise = null
let disposed = false

const renderState = {
  selectedNode: null,
  selectedEdge: null,
  nodeColors: new Map(),
  dimNodes: new Set(),
  dimEdges: new Set(),
  accentNodes: new Set(),
  accentEdges: new Set(),
}

const asKey = value => graphNodeKey(value)
const asKeySet = values => new Set(Array.from(values || [], value => String(value)))
const finiteSize = (value, fallback, min, max) => {
  const number = Number(value)
  return Number.isFinite(number) ? Math.max(min, Math.min(max, number)) : fallback
}

const colorValue = value => {
  if (typeof value === 'string') return value
  return value?.color
}

const colorForType = (type, rawColor) => {
  const colors = props.typeColors
  const key = entityTypeKey(type)
  let match

  if (colors instanceof Map) {
    match = colors.get(key) ?? colors.get(type)
  } else if (Array.isArray(colors)) {
    match = colors.find(item => item?.key === key || entityTypeKey(item?.name) === key)
  } else if (colors && typeof colors === 'object') {
    match = colors[key] ?? colors[type]
  }

  return colorValue(match) || colorValue(rawColor) || '#7B2D8E'
}

const nodeAttributes = (node, key) => ({
  label: node?.name || node?.label || key,
  color: colorForType(node?.type, node?.color),
  size: finiteSize(node?.size, 6, 2, 24),
  rawData: node,
})

const edgeAttributes = edge => ({
  label: edge?.label || edge?.name || '',
  color: edge?.color || '#B8B8B8',
  size: finiteSize(edge?.size, 1.1, 0.25, 8),
  type: edge?.type || 'arrow',
  rawData: edge,
})

const updateRenderState = () => {
  if (!graph) return

  const selectedNode = asKey(props.selectedNodeId)
  const selectedEdge = asKey(props.selectedEdgeId)
  const seenNodes = asKeySet(props.seenNodeIds)
  const seenEdges = asKeySet(props.seenEdgeIds)
  const focusedNodes = asKeySet(props.focusedNodeIds)
  const focusedEdges = asKeySet(props.focusedEdgeIds)
  const hasExplicitFocus = focusedNodes.size > 0 || focusedEdges.size > 0
  const exemptNodes = new Set()
  const exemptEdges = new Set()

  if (selectedNode && graph.hasNode(selectedNode)) {
    exemptNodes.add(selectedNode)
    graph.forEachEdge(selectedNode, (edge, _attributes, source, target) => {
      exemptEdges.add(String(edge))
      exemptNodes.add(String(source))
      exemptNodes.add(String(target))
    })
  }
  if (selectedEdge && graph.hasEdge(selectedEdge)) {
    exemptEdges.add(selectedEdge)
    exemptNodes.add(String(graph.source(selectedEdge)))
    exemptNodes.add(String(graph.target(selectedEdge)))
  }

  const nodeColors = new Map()
  const dimNodes = new Set()
  const dimEdges = new Set()
  const accentNodes = new Set(exemptNodes)
  const accentEdges = new Set(exemptEdges)

  graph.forEachNode((node, attributes) => {
    const key = String(node)
    const raw = attributes.rawData || {}
    nodeColors.set(key, colorForType(raw.type, raw.color || attributes.color))
    const outsideFocus = hasExplicitFocus && !focusedNodes.has(key) && !exemptNodes.has(key)
    const readAndFiltered = props.focusUnread && seenNodes.has(key) && !exemptNodes.has(key)
    if (outsideFocus || readAndFiltered) dimNodes.add(key)
  })

  graph.forEachEdge((edge, _attributes, source, target) => {
    const key = String(edge)
    const sourceKey = String(source)
    const targetKey = String(target)
    const inFocusedNodes = focusedNodes.has(sourceKey) && focusedNodes.has(targetKey)
    const outsideFocus = hasExplicitFocus && !focusedEdges.has(key) && !inFocusedNodes && !exemptEdges.has(key)
    const readAndFiltered = props.focusUnread && seenEdges.has(key) && !exemptEdges.has(key)
    if (outsideFocus || readAndFiltered) dimEdges.add(key)
  })

  renderState.selectedNode = selectedNode
  renderState.selectedEdge = selectedEdge
  renderState.nodeColors = nodeColors
  renderState.dimNodes = dimNodes
  renderState.dimEdges = dimEdges
  renderState.accentNodes = accentNodes
  renderState.accentEdges = accentEdges
}

const nodeReducer = (node, data) => {
  const key = String(node)
  const selected = key === renderState.selectedNode
  const endpointOfSelection = !selected && renderState.accentNodes.has(key)
  const dimmed = renderState.dimNodes.has(key)
  const color = renderState.nodeColors.get(key) || data.color

  return {
    ...data,
    color: selected ? '#E91E63' : (dimmed ? colorWithAlpha(color, 0.16) : color),
    size: data.size + (selected ? 3.5 : endpointOfSelection ? 1.25 : 0),
    highlighted: selected,
    forceLabel: selected,
    zIndex: selected ? 3 : endpointOfSelection ? 2 : 0,
  }
}

const edgeReducer = (edge, data) => {
  const key = String(edge)
  const selected = key === renderState.selectedEdge
  const related = !selected && renderState.accentEdges.has(key)
  const dimmed = renderState.dimEdges.has(key)
  return {
    ...data,
    label: props.showEdgeLabels ? data.label : '',
    color: selected ? '#FF4500' : related ? '#E91E63' : (
      dimmed ? colorWithAlpha(data.color, 0.1) : data.color
    ),
    size: data.size + (selected ? 2.75 : related ? 1.1 : 0),
    forceLabel: props.showEdgeLabels && selected,
    zIndex: selected ? 3 : related ? 2 : 0,
  }
}

const refreshStyles = () => {
  if (!renderer) return
  updateRenderState()
  renderer.setSetting('renderEdgeLabels', props.showEdgeLabels)
  renderer.refresh()
}

const clearLayoutTimer = () => {
  if (layoutTimer !== null) window.clearTimeout(layoutTimer)
  layoutTimer = null
}

const stopLayout = ({ kill = false } = {}) => {
  clearLayoutTimer()
  if (layoutRunning && layout) layout.stop()
  layoutRunning = false
  if (kill && layout) {
    layout.kill()
    layout = null
  }
}

const armLayoutTimer = (duration) => {
  clearLayoutTimer()
  if (!(duration > 0)) return
  layoutStartedAt = performance.now()
  layoutTimer = window.setTimeout(() => {
    layoutTimer = null
    layoutRemainingMs = 0
    if (layoutRunning && layout) layout.stop()
    layoutRunning = false
    renderer?.refresh()
  }, duration)
}

const resumeLayout = () => {
  if (!layout || layoutRunning || document.hidden || !props.layoutEnabled) return
  layout.start()
  layoutRunning = true
  armLayoutTimer(layoutRemainingMs)
}

const pauseLayout = () => {
  if (!layoutRunning || !layout) return
  if (layoutRemainingMs > 0) {
    layoutRemainingMs = Math.max(0, layoutRemainingMs - (performance.now() - layoutStartedAt))
  }
  clearLayoutTimer()
  layout.stop()
  layoutRunning = false
}

const startLayout = () => {
  stopLayout({ kill: true })
  if (
    !graph || !ForceAtlas2Layout ||
    !props.layoutEnabled || graph.order < 2
  ) return

  try {
    const inferred = inferLargeGraphLayoutSettings(graph)
    layout = new ForceAtlas2Layout(graph, {
      settings: { ...inferred, ...props.layoutSettings },
    })
    layoutRemainingMs = Math.max(0, props.layoutDurationMs)
    resumeLayout()
  } catch (error) {
    stopLayout({ kill: true })
    emit('renderer-error', error)
  }
}

const loadLayoutRuntime = async () => {
  if (disposed || ForceAtlas2Layout) return
  try {
    if (!layoutRuntimePromise) {
      layoutRuntimePromise = import('graphology-layout-forceatlas2/worker')
    }
    const workerModule = await layoutRuntimePromise
    if (disposed) return
    ForceAtlas2Layout = workerModule.default || workerModule.FA2Layout
    if (!ForceAtlas2Layout) throw new Error('ForceAtlas2 worker runtime is unavailable')
    if (props.layoutEnabled) startLayout()
  } catch (error) {
    if (!disposed) emit('layout-error', error)
  }
}

// Let Sigma commit its deterministic-position canvas before downloading and
// starting the layout supervisor. Worker bootstrapping used to happen in the
// same task as renderer creation, delaying the first usable graph frame.
const scheduleLayoutBootstrap = () => {
  if (disposed || !props.layoutEnabled) return
  if (ForceAtlas2Layout) {
    startLayout()
    return
  }
  if (layoutRuntimePromise || layoutBootstrapFrame !== null || layoutBootstrapTimer !== null) return
  layoutBootstrapFrame = requestAnimationFrame(() => {
    layoutBootstrapFrame = null
    layoutBootstrapTimer = window.setTimeout(() => {
      layoutBootstrapTimer = null
      loadLayoutRuntime()
    }, 0)
  })
}

const runSync = () => {
  if (!graph) return null
  const shouldResume = layoutRunning
  stopLayout({ kill: true })
  const result = syncGraphologyGraph(graph, {
    nodes: props.nodes,
    edges: props.edges,
    nodeAttributes,
    edgeAttributes,
  })
  updateRenderState()
  renderer?.refresh()
  if (result.topologyChanged || shouldResume) startLayout()
  return result
}

const queueSync = () => {
  if (!graph || disposed) return
  if (syncFrame !== null) cancelAnimationFrame(syncFrame)
  syncFrame = requestAnimationFrame(() => {
    syncFrame = null
    runSync()
  })
}

const handleVisibilityChange = () => {
  if (document.hidden) pauseLayout()
  else resumeLayout()
}

const handleResize = () => {
  if (!renderer || resizeFrame !== null) return
  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = null
    renderer?.resize()
    renderer?.refresh()
  })
}

const resetCamera = () => renderer?.getCamera().animatedReset({ duration: 350 })

const centerOnNode = (id) => {
  if (!renderer) return false
  const key = asKey(id)
  if (!key || !graph.hasNode(key)) return false
  const data = renderer.getNodeDisplayData(key)
  if (!data) return false
  const current = renderer.getCamera().getState()
  renderer.getCamera().animate({
    x: data.x,
    y: data.y,
    ratio: Math.min(current.ratio, 0.35),
  }, { duration: 350 })
  return true
}

const centerOnEdge = (id) => {
  if (!renderer) return false
  const key = asKey(id)
  if (!key || !graph.hasEdge(key)) return false
  const source = renderer.getNodeDisplayData(graph.source(key))
  const target = renderer.getNodeDisplayData(graph.target(key))
  if (!source || !target) return false
  const current = renderer.getCamera().getState()
  renderer.getCamera().animate({
    x: (source.x + target.x) / 2,
    y: (source.y + target.y) / 2,
    ratio: Math.min(current.ratio, 0.35),
  }, { duration: 350 })
  return true
}

watch([() => props.nodes, () => props.edges], queueSync, { flush: 'post' })
watch([
  () => props.selectedNodeId,
  () => props.selectedEdgeId,
  () => props.typeColors,
  () => props.seenNodeIds,
  () => props.seenEdgeIds,
  () => props.focusUnread,
  () => props.focusedNodeIds,
  () => props.focusedEdgeIds,
  () => props.showEdgeLabels,
], refreshStyles, { flush: 'post' })

watch(() => props.layoutEnabled, enabled => {
  if (!graph) return
  if (enabled) scheduleLayoutBootstrap()
  else stopLayout({ kill: true })
})

watch([() => props.layoutDurationMs, () => props.layoutSettings], () => {
  if (graph && props.layoutEnabled) startLayout()
}, { flush: 'post' })

onMounted(async () => {
  await nextTick()
  try {
    // These imports intentionally create a lazy WebGL chunk. Small graphs do
    // not pay Sigma/Graphology/ForceAtlas2 startup cost.
    const [graphologyModule, sigmaModule] = await Promise.all([
      import('graphology'),
      import('sigma'),
    ])
    if (disposed) return

    const Graph = graphologyModule.default || graphologyModule.Graph
    const Sigma = sigmaModule.default || sigmaModule.Sigma

    graph = new Graph({ type: 'directed', multi: true, allowSelfLoops: true })
    syncGraphologyGraph(graph, {
      nodes: props.nodes,
      edges: props.edges,
      nodeAttributes,
      edgeAttributes,
    })
    updateRenderState()

    renderer = new Sigma(graph, container.value, {
      allowInvalidContainer: true,
      defaultEdgeType: 'arrow',
      enableEdgeEvents: true,
      hideEdgesOnMove: true,
      hideLabelsOnMove: true,
      labelDensity: 0.08,
      labelGridCellSize: 140,
      labelRenderedSizeThreshold: 8,
      minCameraRatio: 0.04,
      maxCameraRatio: 5,
      renderEdgeLabels: props.showEdgeLabels,
      stagePadding: 24,
      zIndex: true,
      nodeReducer,
      edgeReducer,
    })

    renderer.on('clickNode', ({ node, event }) => {
      event?.preventSigmaDefault?.()
      emit('select-node', graph.getNodeAttribute(node, 'rawData'))
    })
    renderer.on('clickEdge', ({ edge, event }) => {
      event?.preventSigmaDefault?.()
      emit('select-edge', graph.getEdgeAttribute(edge, 'rawData'))
    })

    if (typeof ResizeObserver === 'function') {
      resizeObserver = new ResizeObserver(handleResize)
      resizeObserver.observe(container.value)
    } else {
      window.addEventListener('resize', handleResize)
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    status.value = 'ready'
    emit('ready', { graph, renderer })
    scheduleLayoutBootstrap()
  } catch (error) {
    if (disposed) return
    status.value = 'error'
    emit('renderer-error', error)
  }
})

onBeforeUnmount(() => {
  disposed = true
  if (syncFrame !== null) cancelAnimationFrame(syncFrame)
  if (resizeFrame !== null) cancelAnimationFrame(resizeFrame)
  if (layoutBootstrapFrame !== null) cancelAnimationFrame(layoutBootstrapFrame)
  if (layoutBootstrapTimer !== null) window.clearTimeout(layoutBootstrapTimer)
  syncFrame = null
  resizeFrame = null
  layoutBootstrapFrame = null
  layoutBootstrapTimer = null
  resizeObserver?.disconnect()
  window.removeEventListener('resize', handleResize)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  stopLayout({ kill: true })
  renderer?.kill()
  renderer = null
  graph?.clear()
  graph = null
})

defineExpose({
  centerOnEdge,
  centerOnNode,
  getGraph: () => graph,
  getRenderer: () => renderer,
  refresh: refreshStyles,
  resetCamera,
  startLayout,
  stopLayout,
  sync: runSync,
})
</script>

<style scoped>
.large-graph-view {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: #fff;
}

.large-graph-view :deep(canvas) {
  touch-action: none;
}

.large-graph-view__message {
  position: absolute;
  z-index: 1;
  inset: 50% auto auto 50%;
  transform: translate(-50%, -50%);
  padding: 8px 12px;
  border-radius: 6px;
  color: #666;
  background: rgb(255 255 255 / 92%);
  font: 500 13px/1.4 system-ui, sans-serif;
}
</style>
