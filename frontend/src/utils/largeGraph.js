export const LARGE_GRAPH_NODE_THRESHOLD = 500
export const LARGE_GRAPH_EDGE_THRESHOLD = 1000
export const NATIVE_EDGE_EVENTS_MAX_EDGES = 5000
export const MASSIVE_GRAPH_NODE_THRESHOLD = 2000
export const MASSIVE_GRAPH_EDGE_THRESHOLD = 8000
export const MASSIVE_GRAPH_EDGE_LABEL_BUDGET = 36

export const shouldUseLargeGraphRenderer = ({
  nodeCount = 0,
  edgeCount = 0,
  nodeThreshold = LARGE_GRAPH_NODE_THRESHOLD,
  edgeThreshold = LARGE_GRAPH_EDGE_THRESHOLD,
} = {}) => (
  Number(nodeCount) >= nodeThreshold || Number(edgeCount) >= edgeThreshold
)

// Sigma's native edge picking renders a second off-screen WebGL buffer. That
// is convenient for ordinary graphs, but on software WebGL/headless devices it
// can dominate the first frame for tens of thousands of edges. Dense graphs
// use click-time geometric picking instead, keeping direct edge selection
// without paying the framebuffer cost on every render.
export const shouldEnableNativeEdgeEvents = ({
  edgeCount = 0,
  maxEdges = NATIVE_EDGE_EVENTS_MAX_EDGES,
} = {}) => Number(edgeCount) <= maxEdges

export const shouldUseMassiveGraphProfile = ({
  nodeCount = 0,
  edgeCount = 0,
  nodeThreshold = MASSIVE_GRAPH_NODE_THRESHOLD,
  edgeThreshold = MASSIVE_GRAPH_EDGE_THRESHOLD,
} = {}) => (
  Number(nodeCount) >= nodeThreshold || Number(edgeCount) >= edgeThreshold
)

// Dense graph labels need a quieter base than the SVG graph. Increase visual
// emphasis smoothly as incident relationships accumulate, while keeping even
// book-wide hubs compact enough to coexist with the topology.
export const degreeAwareNodeLabelSize = ({
  connectionCount = 0,
  baseSize = 12,
  maxSize = 18,
  ordinaryConnectionCount = 3,
  growth = 0.9,
} = {}) => {
  const base = Math.max(1, Number(baseSize) || 12)
  const maximum = Math.max(base, Number(maxSize) || 18)
  const ordinary = Math.max(0, Number(ordinaryConnectionCount) || 0)
  const connections = Math.max(0, Number(connectionCount) || 0)
  const scale = Math.max(0, Number(growth) || 0)
  return Math.min(maximum, base + scale * Math.log1p(
    Math.max(0, connections - ordinary),
  ))
}

// Sigma's camera ratio is inverse zoom (smaller means closer). Text should gain
// a little emphasis as the user enters a neighbourhood, but must not scale at
// the same rate as graph geometry or it quickly covers nearby nodes.
export const graphZoomLabelScale = ({
  cameraRatio = 1,
  minScale = 0.78,
  maxScale = 1.6,
  exponent = 0.3,
} = {}) => {
  const rawRatio = Number(cameraRatio)
  const ratio = Number.isFinite(rawRatio) && rawRatio > 0 ? rawRatio : 1
  const minimum = Math.max(0.01, Number(minScale) || 0.78)
  const maximum = Math.max(minimum, Number(maxScale) || 1.6)
  const power = Math.max(0, Number(exponent) || 0.3)
  return Math.max(minimum, Math.min(maximum, ratio ** -power))
}

/**
 * Pick a small, stable set of useful relationship labels for a massive graph.
 * Sigma still renders every edge in WebGL; this only bounds the much more
 * expensive canvas text overlay. Distinct relationship phrases win first,
 * then edges attached to more connected entities fill the remaining budget.
 */
export const selectBoundedEdgeLabelIds = ({
  edges = [],
  maxLabels = MASSIVE_GRAPH_EDGE_LABEL_BUDGET,
} = {}) => {
  const budget = Math.max(0, Math.floor(Number(maxLabels) || 0))
  if (!budget) return new Set()

  const degree = new Map()
  const records = []
  for (const [index, edge] of (edges || []).entries()) {
    const id = graphNodeKey(edge?.id ?? edge?.key)
    const source = graphNodeKey(edge?.source)
    const target = graphNodeKey(edge?.target)
    const label = String(edge?.label ?? edge?.name ?? '').trim()
    if (!id || !source || !target || !label) continue
    degree.set(source, (degree.get(source) || 0) + 1)
    degree.set(target, (degree.get(target) || 0) + 1)
    records.push({ id, source, target, label, index })
  }

  records.sort((left, right) => (
    (degree.get(right.source) || 0) + (degree.get(right.target) || 0) -
      (degree.get(left.source) || 0) - (degree.get(left.target) || 0)
  ) || left.index - right.index)

  const selected = new Set()
  const phrases = new Set()
  for (const record of records) {
    const phrase = record.label.toLowerCase()
    if (phrases.has(phrase)) continue
    selected.add(record.id)
    phrases.add(phrase)
    if (selected.size >= budget) return selected
  }
  for (const record of records) {
    selected.add(record.id)
    if (selected.size >= budget) break
  }
  return selected
}

export const accumulatedWheelZoomRatio = ({
  currentRatio = 1,
  wheelSteps = 0,
  zoomingRatio = 1.7,
  minRatio = 0.04,
  maxRatio = 5,
  maxSteps = 4,
} = {}) => {
  const ratio = Math.max(Number.EPSILON, Number(currentRatio) || 1)
  const base = Math.max(1.01, Number(zoomingRatio) || 1.7)
  const steps = Math.max(-maxSteps, Math.min(maxSteps, Number(wheelSteps) || 0))
  return Math.max(minRatio, Math.min(maxRatio, ratio * (base ** -steps)))
}

const pointSegmentDistanceSquared = (point, source, target) => {
  const dx = target.x - source.x
  const dy = target.y - source.y
  if (!dx && !dy) {
    return (point.x - source.x) ** 2 + (point.y - source.y) ** 2
  }
  const t = Math.max(0, Math.min(1,
    ((point.x - source.x) * dx + (point.y - source.y) * dy) / (dx * dx + dy * dy)
  ))
  const x = source.x + t * dx
  const y = source.y + t * dy
  return (point.x - x) ** 2 + (point.y - y) ** 2
}

export const findClosestEdgeAtPoint = ({
  edges = [],
  point,
  nodePoint,
  maxDistance = 8,
} = {}) => {
  if (!point || typeof nodePoint !== 'function') return null
  const pointCache = new Map()
  const resolvePoint = id => {
    const key = graphNodeKey(id)
    if (!key) return null
    if (!pointCache.has(key)) pointCache.set(key, nodePoint(key))
    return pointCache.get(key)
  }
  let closest = null
  let closestDistance = Math.max(0, Number(maxDistance) || 0) ** 2

  for (const edge of edges || []) {
    const source = resolvePoint(edge?.source)
    const target = resolvePoint(edge?.target)
    if (!source || !target) continue
    const distance = pointSegmentDistanceSquared(point, source, target)
    if (distance <= closestDistance) {
      closestDistance = distance
      closest = edge
    }
  }
  return closest
}

// Mirrors graphology-layout-forceatlas2's small inferSettings helper without
// loading the synchronous layout implementation on the graph's critical path.
// The actual layout still runs through the package's Web Worker supervisor.
export const inferLargeGraphLayoutSettings = (graphOrOrder) => {
  const rawOrder = typeof graphOrOrder === 'number' ? graphOrOrder : graphOrOrder?.order
  const order = Math.max(0, Number(rawOrder) || 0)
  return {
    barnesHutOptimize: order > 2000,
    strongGravityMode: true,
    gravity: 0.05,
    scalingRatio: 10,
    slowDown: 1 + Math.log(Math.max(1, order)),
  }
}

const finiteNumber = (value) => Number.isFinite(Number(value))

export const graphNodeKey = (nodeOrId) => {
  const value = nodeOrId && typeof nodeOrId === 'object' ? nodeOrId.id : nodeOrId
  return value === null || value === undefined || value === '' ? null : String(value)
}

const edgeEndpointKey = (edge, side) => graphNodeKey(edge?.[side])

const encodedPart = (value) => encodeURIComponent(String(value ?? ''))

// Persisted graphs normally have edge ids. The fallback remains deterministic
// for legacy payloads and distinguishes parallel relationships.
const fallbackEdgeKey = (edge, occurrence) => [
  '__bookmiro_edge__',
  encodedPart(edgeEndpointKey(edge, 'source')),
  encodedPart(edgeEndpointKey(edge, 'target')),
  encodedPart(edge?.label ?? edge?.name ?? ''),
  occurrence,
].join(':')

const hashString = (value) => {
  let hash = 2166136261
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

const deterministicPosition = (key, index, anchors = []) => {
  const hash = hashString(key)
  const angle = ((hash % 3600) / 3600) * Math.PI * 2
  const jitter = 12 + ((hash >>> 12) % 24)

  if (anchors.length) {
    const x = anchors.reduce((sum, point) => sum + point.x, 0) / anchors.length
    const y = anchors.reduce((sum, point) => sum + point.y, 0) / anchors.length
    return {
      x: x + Math.cos(angle) * jitter,
      y: y + Math.sin(angle) * jitter,
    }
  }

  const radius = 20 + Math.sqrt(index + 1) * 18
  return {
    x: Math.cos(angle) * radius,
    y: Math.sin(angle) * radius,
  }
}

const graphNodeKeys = (graph) => {
  const keys = []
  graph.forEachNode(key => keys.push(String(key)))
  return keys
}

const graphEdgeKeys = (graph) => {
  const keys = []
  graph.forEachEdge(key => keys.push(String(key)))
  return keys
}

const addEdgeWithKey = (graph, key, source, target, attributes) => {
  if (typeof graph.addDirectedEdgeWithKey === 'function') {
    graph.addDirectedEdgeWithKey(key, source, target, attributes)
  } else {
    graph.addEdgeWithKey(key, source, target, attributes)
  }
}

const defaultYieldControl = () => {
  // scheduler.yield continuations receive boosted priority in Chromium and
  // can starve input/timer work across a long hydration chain. A macrotask
  // turn gives the reader and heartbeat a real chance to run between slices.
  return new Promise(resolve => setTimeout(resolve, 0))
}

const monotonicNow = () => globalThis.performance?.now?.() ?? Date.now()

/**
 * Populate a new Graphology graph without monopolising the browser main
 * thread. Sigma cannot paint until its graph exists, but a large JSON payload
 * can still take several frames to convert into Graphology records. Splitting
 * that conversion into short tasks keeps reader controls, scrolling and pane
 * resizing responsive while preserving every valid node and edge.
 *
 * This is intentionally an initial-hydration helper. Incremental updates use
 * syncGraphologyGraph so existing layout coordinates continue to win.
 */
export const hydrateGraphologyGraphCooperatively = async (graph, {
  nodes = [],
  edges = [],
  nodeAttributes = node => ({ label: node?.name || String(node?.id ?? '') }),
  edgeAttributes = edge => ({ label: edge?.label || '' }),
  frameBudgetMs = 8,
  yieldControl = defaultYieldControl,
  now = monotonicNow,
  shouldAbort = () => false,
} = {}) => {
  if (!graph) throw new TypeError('A Graphology-compatible graph is required')
  if ((Number(graph.order) || 0) > 0 || (Number(graph.size) || 0) > 0) {
    throw new Error('Cooperative hydration requires an empty graph')
  }

  const budget = Math.max(1, Number(frameBudgetMs) || 8)
  let sliceStartedAt = now()
  let yieldCount = 0
  let aborted = false

  const checkpoint = async () => {
    if (shouldAbort()) {
      aborted = true
      return false
    }
    if (now() - sliceStartedAt < budget) return true
    await yieldControl()
    yieldCount += 1
    sliceStartedAt = now()
    if (shouldAbort()) {
      aborted = true
      return false
    }
    return true
  }

  let addedNodes = 0
  let updatedNodes = 0
  let addedEdges = 0
  let updatedEdges = 0
  let removedEdges = 0
  const invalidEdges = []
  let newNodeIndex = 0

  let processed = 0
  for (const raw of nodes || []) {
    const key = graphNodeKey(raw)
    if (key) {
      const incoming = nodeAttributes(raw, key) || {}
      if (graph.hasNode(key)) {
        const current = graph.getNodeAttributes(key)
        const position = positionFromAttributes(current) ||
          positionFromAttributes(incoming) ||
          deterministicPosition(key, newNodeIndex)
        graph.replaceNodeAttributes(key, { ...incoming, ...position })
        updatedNodes += 1
      } else {
        const position = positionFromAttributes(incoming) || deterministicPosition(key, newNodeIndex)
        graph.addNode(key, { ...incoming, ...position })
        newNodeIndex += 1
        addedNodes += 1
      }
    }
    processed += 1
    if (processed % 128 === 0 && !await checkpoint()) break
  }

  const occurrenceBySignature = new Map()
  if (!aborted) {
    processed = 0
    for (const raw of edges || []) {
      const source = edgeEndpointKey(raw, 'source')
      const target = edgeEndpointKey(raw, 'target')
      if (!source || !target || !graph.hasNode(source) || !graph.hasNode(target)) {
        invalidEdges.push(raw)
      } else {
        const signature = `${source}\u0000${target}\u0000${String(raw?.label ?? raw?.name ?? '')}`
        const occurrence = occurrenceBySignature.get(signature) || 0
        occurrenceBySignature.set(signature, occurrence + 1)
        const key = raw?.id === null || raw?.id === undefined || raw?.id === ''
          ? fallbackEdgeKey(raw, occurrence)
          : String(raw.id)
        const incoming = edgeAttributes(raw, key) || {}

        if (graph.hasEdge(key)) {
          const endpointChanged = String(graph.source(key)) !== source || String(graph.target(key)) !== target
          if (endpointChanged) {
            graph.dropEdge(key)
            removedEdges += 1
            addEdgeWithKey(graph, key, source, target, incoming)
            addedEdges += 1
          } else {
            graph.replaceEdgeAttributes(key, incoming)
            updatedEdges += 1
          }
        } else {
          addEdgeWithKey(graph, key, source, target, incoming)
          addedEdges += 1
        }
      }
      processed += 1
      if (processed % 256 === 0 && !await checkpoint()) break
    }
  }

  return {
    addedNodes,
    updatedNodes,
    removedNodes: 0,
    addedEdges,
    updatedEdges,
    removedEdges,
    invalidEdges,
    aborted,
    yieldCount,
    topologyChanged: Boolean(addedNodes || addedEdges || removedEdges),
  }
}

const positionFromAttributes = (attributes) => {
  if (!attributes || !finiteNumber(attributes.x) || !finiteNumber(attributes.y)) return null
  return { x: Number(attributes.x), y: Number(attributes.y) }
}

/**
 * Incrementally mirrors API nodes and edges into a Graphology graph.
 *
 * Existing node coordinates always win over incoming attributes. This is what
 * keeps a progressively revealed graph stable after ForceAtlas2 has moved it.
 */
export const syncGraphologyGraph = (graph, {
  nodes = [],
  edges = [],
  nodeAttributes = node => ({ label: node?.name || String(node?.id ?? '') }),
  edgeAttributes = edge => ({ label: edge?.label || '' }),
} = {}) => {
  if (!graph) throw new TypeError('A Graphology-compatible graph is required')

  const nodeRecords = new Map()
  for (const node of nodes || []) {
    const key = graphNodeKey(node)
    if (key) nodeRecords.set(key, node)
  }

  const occurrenceBySignature = new Map()
  const edgeRecords = new Map()
  const invalidEdges = []
  for (const edge of edges || []) {
    const source = edgeEndpointKey(edge, 'source')
    const target = edgeEndpointKey(edge, 'target')
    if (!source || !target || !nodeRecords.has(source) || !nodeRecords.has(target)) {
      invalidEdges.push(edge)
      continue
    }

    const signature = `${source}\u0000${target}\u0000${String(edge?.label ?? edge?.name ?? '')}`
    const occurrence = occurrenceBySignature.get(signature) || 0
    occurrenceBySignature.set(signature, occurrence + 1)
    const key = edge?.id === null || edge?.id === undefined || edge?.id === ''
      ? fallbackEdgeKey(edge, occurrence)
      : String(edge.id)
    edgeRecords.set(key, { key, source, target, raw: edge })
  }

  let addedNodes = 0
  let updatedNodes = 0
  let removedNodes = 0
  let addedEdges = 0
  let updatedEdges = 0
  let removedEdges = 0

  // Stop retaining an edge if it disappeared or if a reused id now points to
  // different endpoints. Endpoint changes require a drop/add in Graphology.
  for (const key of graphEdgeKeys(graph)) {
    const incoming = edgeRecords.get(key)
    const endpointChanged = incoming && (
      String(graph.source(key)) !== incoming.source || String(graph.target(key)) !== incoming.target
    )
    if (!incoming || endpointChanged) {
      graph.dropEdge(key)
      removedEdges += 1
    }
  }

  for (const key of graphNodeKeys(graph)) {
    if (!nodeRecords.has(key)) {
      graph.dropNode(key)
      removedNodes += 1
    }
  }

  // Build an adjacency index so newly revealed nodes can start close to an
  // already positioned neighbour instead of flashing in from the origin.
  const neighbours = new Map()
  for (const { source, target } of edgeRecords.values()) {
    if (!neighbours.has(source)) neighbours.set(source, [])
    if (!neighbours.has(target)) neighbours.set(target, [])
    neighbours.get(source).push(target)
    if (source !== target) neighbours.get(target).push(source)
  }

  let newNodeIndex = 0
  for (const [key, raw] of nodeRecords) {
    const incoming = nodeAttributes(raw, key) || {}
    if (graph.hasNode(key)) {
      const current = graph.getNodeAttributes(key)
      const currentPosition = positionFromAttributes(current)
      const incomingPosition = positionFromAttributes(incoming)
      const position = currentPosition || incomingPosition || deterministicPosition(key, newNodeIndex)
      graph.replaceNodeAttributes(key, { ...incoming, ...position })
      updatedNodes += 1
      continue
    }

    const anchors = (neighbours.get(key) || [])
      .filter(neighbour => graph.hasNode(neighbour))
      .map(neighbour => positionFromAttributes(graph.getNodeAttributes(neighbour)))
      .filter(Boolean)
    const incomingPosition = positionFromAttributes(incoming)
    const position = incomingPosition || deterministicPosition(key, newNodeIndex, anchors)
    graph.addNode(key, { ...incoming, ...position })
    newNodeIndex += 1
    addedNodes += 1
  }

  for (const [key, { source, target, raw }] of edgeRecords) {
    const incoming = edgeAttributes(raw, key) || {}
    if (graph.hasEdge(key)) {
      graph.replaceEdgeAttributes(key, incoming)
      updatedEdges += 1
    } else {
      addEdgeWithKey(graph, key, source, target, incoming)
      addedEdges += 1
    }
  }

  return {
    addedNodes,
    updatedNodes,
    removedNodes,
    addedEdges,
    updatedEdges,
    removedEdges,
    invalidEdges,
    topologyChanged: Boolean(
      addedNodes || removedNodes || addedEdges || removedEdges
    ),
  }
}

export const colorWithAlpha = (color, alpha) => {
  const opacity = Math.max(0, Math.min(1, Number(alpha)))
  const value = typeof color === 'string' ? color.trim() : ''
  let red
  let green
  let blue

  const shortHex = /^#([\da-f])([\da-f])([\da-f])$/iu.exec(value)
  const longHex = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})(?:[\da-f]{2})?$/iu.exec(value)
  const rgb = /^rgba?\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)/iu.exec(value)

  if (shortHex) {
    red = parseInt(shortHex[1] + shortHex[1], 16)
    green = parseInt(shortHex[2] + shortHex[2], 16)
    blue = parseInt(shortHex[3] + shortHex[3], 16)
  } else if (longHex) {
    red = parseInt(longHex[1], 16)
    green = parseInt(longHex[2], 16)
    blue = parseInt(longHex[3], 16)
  } else if (rgb) {
    red = Math.min(255, Number(rgb[1]))
    green = Math.min(255, Number(rgb[2]))
    blue = Math.min(255, Number(rgb[3]))
  } else {
    return value || '#999999'
  }

  return `rgba(${red}, ${green}, ${blue}, ${opacity})`
}
