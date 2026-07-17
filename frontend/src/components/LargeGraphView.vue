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
    :data-layout-mode="graphLayoutMode"
  >
    <div v-if="status === 'error'" class="large-graph-view__message" role="status">
      WebGL graph unavailable
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { entityTypeKey } from '../utils/entityTypes'
import {
  accumulatedWheelZoomRatio,
  colorWithAlpha,
  findClosestEdgeAtPoint,
  graphNodeKey,
  hydrateGraphologyGraphCooperatively,
  inferLargeGraphLayoutSettings,
  shouldEnableNativeEdgeEvents,
  shouldUseMassiveGraphProfile,
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
const massiveGraph = computed(() => shouldUseMassiveGraphProfile({
  nodeCount: props.nodes.length,
  edgeCount: props.edges.length,
}))
const graphLayoutMode = computed(() => (
  massiveGraph.value || !props.layoutEnabled ? 'static' : 'worker'
))

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
let resizeTimer = null
let syncFrame = null
let layoutBootstrapFrame = null
let layoutBootstrapTimer = null
let layoutRuntimePromise = null
let disposed = false
let nativeEdgeEventsEnabled = true
let styleRefreshToken = 0
let wheelTimer = null
let wheelSteps = 0
let wheelPoint = null

const renderState = {
  selectedNode: null,
  selectedEdge: null,
  seenNodes: new Set(),
  seenEdges: new Set(),
  focusedNodes: new Set(),
  focusedEdges: new Set(),
  hasExplicitFocus: false,
  accentNodes: new Set(),
  accentEdges: new Set(),
}

let typeColorSource = null
let typeColorLookup = new Map()

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

const rebuildTypeColorLookup = () => {
  const colors = props.typeColors
  if (colors === typeColorSource) return
  typeColorSource = colors
  const next = new Map()

  if (colors instanceof Map) {
    for (const [key, value] of colors) {
      next.set(entityTypeKey(key), colorValue(value))
    }
  } else if (Array.isArray(colors)) {
    for (const item of colors) {
      const key = item?.key || entityTypeKey(item?.name)
      if (key) next.set(key, colorValue(item))
    }
  } else if (colors && typeof colors === 'object') {
    for (const [key, value] of Object.entries(colors)) {
      next.set(entityTypeKey(key), colorValue(value))
    }
  }

  typeColorLookup = next
}

const colorForType = (type, rawColor) => {
  rebuildTypeColorLookup()
  const key = entityTypeKey(type)
  return typeColorLookup.get(key) || colorValue(rawColor) || '#7B2D8E'
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
  type: massiveGraph.value ? 'line' : (edge?.type || 'arrow'),
  rawData: edge,
})

const updateRenderState = () => {
  if (!graph) return

  const selectedNode = asKey(props.selectedNodeId)
  const selectedEdge = asKey(props.selectedEdgeId)
  // Read-state sets are irrelevant until "focus unread" is enabled. Avoid
  // copying thousands of ids on initial All Chapters render.
  const seenNodes = props.focusUnread ? asKeySet(props.seenNodeIds) : new Set()
  const seenEdges = props.focusUnread ? asKeySet(props.seenEdgeIds) : new Set()
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

  renderState.selectedNode = selectedNode
  renderState.selectedEdge = selectedEdge
  renderState.seenNodes = seenNodes
  renderState.seenEdges = seenEdges
  renderState.focusedNodes = focusedNodes
  renderState.focusedEdges = focusedEdges
  renderState.hasExplicitFocus = hasExplicitFocus
  renderState.accentNodes = exemptNodes
  renderState.accentEdges = exemptEdges
}

const nodeReducer = (node, data) => {
  const key = String(node)
  const selected = key === renderState.selectedNode
  const endpointOfSelection = !selected && renderState.accentNodes.has(key)
  const outsideFocus = renderState.hasExplicitFocus &&
    !renderState.focusedNodes.has(key) && !renderState.accentNodes.has(key)
  const readAndFiltered = props.focusUnread &&
    renderState.seenNodes.has(key) && !renderState.accentNodes.has(key)
  const dimmed = outsideFocus || readAndFiltered
  // The synchronized graph attribute already contains the resolved type
  // color. Re-normalizing the entity type inside Sigma's reducer would repeat
  // that string work for every node on every worker-driven render frame.
  const color = data.color

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
  const raw = data.rawData || {}
  const source = asKey(raw.source)
  const target = asKey(raw.target)
  const inFocusedNodes = renderState.focusedNodes.has(source) && renderState.focusedNodes.has(target)
  const outsideFocus = renderState.hasExplicitFocus &&
    !renderState.focusedEdges.has(key) && !inFocusedNodes && !renderState.accentEdges.has(key)
  const readAndFiltered = props.focusUnread &&
    renderState.seenEdges.has(key) && !renderState.accentEdges.has(key)
  const dimmed = outsideFocus || readAndFiltered
  return {
    ...data,
    label: props.showEdgeLabels && !massiveGraph.value ? data.label : '',
    color: selected ? '#FF4500' : related ? '#E91E63' : (
      dimmed ? colorWithAlpha(data.color, 0.1) : data.color
    ),
    size: data.size + (selected ? 2.75 : related ? 1.1 : 0),
    forceLabel: props.showEdgeLabels && selected,
    zIndex: selected ? 3 : related ? 2 : 0,
  }
}

const needsInteractiveReducers = () => Boolean(
  renderState.selectedNode || renderState.selectedEdge || props.focusUnread ||
  renderState.hasExplicitFocus
)

const yieldMainThread = () => {
  if (typeof globalThis.scheduler?.yield === 'function') return globalThis.scheduler.yield()
  return new Promise(resolve => window.setTimeout(resolve, 0))
}

const refreshMassiveGraphStyles = async (token) => {
  // Make the selected neighbourhood visible first, then repaint the rest in
  // bounded chunks. Sigma's partial skip-indexation path updates existing GPU
  // slots and avoids rebuilding the complete 25k+ item index for a toolbar
  // click such as "focus unread".
  const priorityNodes = [...renderState.accentNodes]
  if (renderState.selectedNode) priorityNodes.push(renderState.selectedNode)
  const priorityEdges = [...renderState.accentEdges]
  if (renderState.selectedEdge) priorityEdges.push(renderState.selectedEdge)
  const validPriorityNodes = priorityNodes.filter(key => graph?.hasNode(key))
  const validPriorityEdges = priorityEdges.filter(key => graph?.hasEdge(key))
  if (validPriorityNodes.length || validPriorityEdges.length) {
    renderer?.refresh({
      partialGraph: { nodes: validPriorityNodes, edges: validPriorityEdges },
      skipIndexation: true,
      schedule: true,
    })
  }

  await yieldMainThread()
  if (disposed || token !== styleRefreshToken || !renderer || !graph) return
  const nodeKeys = graph.nodes()
  const edgeKeys = graph.edges()
  const chunkSize = 512
  const length = Math.max(nodeKeys.length, edgeKeys.length)
  for (let offset = 0; offset < length; offset += chunkSize) {
    if (disposed || token !== styleRefreshToken || !renderer || !graph) return
    renderer.refresh({
      partialGraph: {
        nodes: nodeKeys.slice(offset, offset + chunkSize),
        edges: edgeKeys.slice(offset, offset + chunkSize),
      },
      skipIndexation: true,
      schedule: true,
    })
    await yieldMainThread()
  }
}

const refreshStyles = () => {
  if (!renderer) return
  updateRenderState()
  const renderEdgeLabels = props.showEdgeLabels && !massiveGraph.value
  if (massiveGraph.value) {
    styleRefreshToken += 1
    const refreshToken = styleRefreshToken
    const reducer = needsInteractiveReducers()
    const nextNodeReducer = reducer ? nodeReducer : null
    const nextEdgeReducer = reducer ? edgeReducer : null
    const reducerChanged = renderer.getSetting('nodeReducer') !== nextNodeReducer ||
      renderer.getSetting('edgeReducer') !== nextEdgeReducer
    const labelsChanged = renderer.getSetting('renderEdgeLabels') !== renderEdgeLabels
    if (reducerChanged || labelsChanged) {
      // Sigma must rebuild once when reducer presence changes. Subsequent
      // focus/selection updates stay on the cooperative partial path below.
      renderer.setSettings({
        nodeReducer: nextNodeReducer,
        edgeReducer: nextEdgeReducer,
        renderEdgeLabels,
      })
      return
    }
    void refreshMassiveGraphStyles(refreshToken)
    return
  } else if (renderer.getSetting('renderEdgeLabels') !== renderEdgeLabels) {
    renderer.setSetting('renderEdgeLabels', renderEdgeLabels)
  }
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
    renderer?.scheduleRender()
  }, duration)
}

const resumeLayout = () => {
  if (!layout || layoutRunning || document.hidden || !props.layoutEnabled || massiveGraph.value) return
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
    !props.layoutEnabled || massiveGraph.value || graph.order < 2
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
    if (props.layoutEnabled && !massiveGraph.value) startLayout()
  } catch (error) {
    if (!disposed) emit('layout-error', error)
  }
}

// Let Sigma commit its deterministic-position canvas before downloading and
// starting the layout supervisor. Worker bootstrapping used to happen in the
// same task as renderer creation, delaying the first usable graph frame.
const scheduleLayoutBootstrap = () => {
  if (disposed || !props.layoutEnabled || massiveGraph.value) return
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
  styleRefreshToken += 1
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
  if (!renderer) return
  if (massiveGraph.value) {
    if (resizeTimer !== null) window.clearTimeout(resizeTimer)
    resizeTimer = window.setTimeout(() => {
      resizeTimer = null
      renderer?.resize()
      renderer?.scheduleRender()
    }, 80)
    return
  }
  if (resizeFrame !== null) return
  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = null
    renderer?.resize()
    // Resizing changes viewport buffers, not graph attributes. A full refresh
    // would re-run reducers and rebuild indices for every node and edge.
    renderer?.scheduleRender()
  })
}

const handleMassiveWheel = (event) => {
  if (!massiveGraph.value || !renderer) return
  // Capture before Sigma's mouse captor. Its ordinary wheel dispatch performs
  // a synchronous WebGL readPixels hit-test for every wheel event, which can
  // cost hundreds of milliseconds under software WebGL even though zooming
  // does not need to know the hovered node.
  event.preventDefault()
  event.stopImmediatePropagation()
  const deltaY = Number(event.deltaY) || 0
  const rect = container.value?.getBoundingClientRect()
  if (!rect) return
  wheelSteps += -deltaY / 120
  wheelPoint = { x: event.clientX - rect.left, y: event.clientY - rect.top }
  if (wheelTimer !== null) window.clearTimeout(wheelTimer)
  wheelTimer = window.setTimeout(() => {
    wheelTimer = null
    if (!renderer || !wheelPoint || !massiveGraph.value) {
      wheelSteps = 0
      wheelPoint = null
      return
    }
    const camera = renderer.getCamera()
    const current = camera.getState()
    const ratio = accumulatedWheelZoomRatio({
      currentRatio: current.ratio,
      wheelSteps,
      zoomingRatio: renderer.getSetting('zoomingRatio') ?? 1.7,
      minRatio: renderer.getSetting('minCameraRatio') ?? 0.04,
      maxRatio: renderer.getSetting('maxCameraRatio') ?? 5,
    })
    const next = renderer.getViewportZoomedState(wheelPoint, ratio)
    wheelSteps = 0
    wheelPoint = null
    camera.setState(next)
  }, 60)
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
  if (enabled && !massiveGraph.value) scheduleLayoutBootstrap()
  else stopLayout({ kill: true })
})

watch(massiveGraph, massive => {
  if (!graph) return
  if (massive) stopLayout({ kill: true })
  else if (props.layoutEnabled) scheduleLayoutBootstrap()
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
    await hydrateGraphologyGraphCooperatively(graph, {
      nodes: props.nodes,
      edges: props.edges,
      nodeAttributes,
      edgeAttributes,
      shouldAbort: () => disposed,
    })
    if (disposed) return
    updateRenderState()

    nativeEdgeEventsEnabled = !massiveGraph.value &&
      shouldEnableNativeEdgeEvents({ edgeCount: graph.size })

    renderer = new Sigma(graph, container.value, {
      allowInvalidContainer: true,
      defaultEdgeType: massiveGraph.value ? 'line' : 'arrow',
      enableEdgeEvents: nativeEdgeEventsEnabled,
      hideEdgesOnMove: true,
      hideLabelsOnMove: true,
      labelDensity: 0.08,
      labelGridCellSize: 140,
      labelRenderedSizeThreshold: 8,
      minCameraRatio: 0.04,
      maxCameraRatio: 5,
      renderEdgeLabels: props.showEdgeLabels && !massiveGraph.value,
      stagePadding: 24,
      zIndex: !massiveGraph.value,
      nodeReducer: massiveGraph.value && !needsInteractiveReducers() ? null : nodeReducer,
      edgeReducer: massiveGraph.value && !needsInteractiveReducers() ? null : edgeReducer,
    })

    renderer.on('clickNode', ({ node, event }) => {
      event?.preventSigmaDefault?.()
      emit('select-node', graph.getNodeAttribute(node, 'rawData'))
    })
    renderer.on('clickEdge', ({ edge, event }) => {
      event?.preventSigmaDefault?.()
      emit('select-edge', graph.getEdgeAttribute(edge, 'rawData'))
    })
    renderer.on('clickStage', ({ event }) => {
      if (nativeEdgeEventsEnabled) return
      const edge = findClosestEdgeAtPoint({
        edges: props.edges,
        point: event,
        nodePoint: key => {
          if (!graph.hasNode(key)) return null
          return renderer.graphToViewport(graph.getNodeAttributes(key))
        },
      })
      if (!edge) return
      event?.preventSigmaDefault?.()
      emit('select-edge', edge)
    })
    container.value.addEventListener('wheel', handleMassiveWheel, {
      capture: true,
      passive: false,
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
  styleRefreshToken += 1
  if (syncFrame !== null) cancelAnimationFrame(syncFrame)
  if (resizeFrame !== null) cancelAnimationFrame(resizeFrame)
  if (resizeTimer !== null) window.clearTimeout(resizeTimer)
  if (wheelTimer !== null) window.clearTimeout(wheelTimer)
  if (layoutBootstrapFrame !== null) cancelAnimationFrame(layoutBootstrapFrame)
  if (layoutBootstrapTimer !== null) window.clearTimeout(layoutBootstrapTimer)
  syncFrame = null
  resizeFrame = null
  resizeTimer = null
  wheelTimer = null
  layoutBootstrapFrame = null
  layoutBootstrapTimer = null
  resizeObserver?.disconnect()
  container.value?.removeEventListener('wheel', handleMassiveWheel, true)
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
