export const LARGE_GRAPH_NODE_THRESHOLD = 500
export const LARGE_GRAPH_EDGE_THRESHOLD = 1000

export const shouldUseLargeGraphRenderer = ({
  nodeCount = 0,
  edgeCount = 0,
  nodeThreshold = LARGE_GRAPH_NODE_THRESHOLD,
  edgeThreshold = LARGE_GRAPH_EDGE_THRESHOLD,
} = {}) => (
  Number(nodeCount) >= nodeThreshold || Number(edgeCount) >= edgeThreshold
)

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
