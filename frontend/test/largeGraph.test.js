import test from 'node:test'
import assert from 'node:assert/strict'

import {
  accumulatedWheelZoomRatio,
  colorWithAlpha,
  degreeAwareLayoutWeight,
  findClosestEdgeAtPoint,
  hydrateGraphologyGraphCooperatively,
  inferLargeGraphLayoutSettings,
  MASSIVE_GRAPH_EDGE_LABEL_BUDGET,
  selectBoundedEdgeLabelIds,
  shouldEnableNativeEdgeEvents,
  shouldUseLargeGraphRenderer,
  shouldUseMassiveGraphProfile,
  syncGraphologyGraph,
} from '../src/utils/largeGraph.js'

class FakeGraph {
  constructor() {
    this.nodes = new Map()
    this.edges = new Map()
  }

  get order() { return this.nodes.size }
  get size() { return this.edges.size }

  addNode(key, attributes) { this.nodes.set(String(key), { ...attributes }) }
  hasNode(key) { return this.nodes.has(String(key)) }
  getNodeAttributes(key) { return this.nodes.get(String(key)) }
  replaceNodeAttributes(key, attributes) { this.nodes.set(String(key), { ...attributes }) }
  forEachNode(callback) {
    for (const [key, attributes] of this.nodes) callback(key, attributes)
  }
  dropNode(key) {
    const normalized = String(key)
    this.nodes.delete(normalized)
    for (const [edge, record] of this.edges) {
      if (record.source === normalized || record.target === normalized) this.edges.delete(edge)
    }
  }

  addDirectedEdgeWithKey(key, source, target, attributes) {
    this.edges.set(String(key), {
      source: String(source),
      target: String(target),
      attributes: { ...attributes },
    })
  }
  hasEdge(key) { return this.edges.has(String(key)) }
  source(key) { return this.edges.get(String(key)).source }
  target(key) { return this.edges.get(String(key)).target }
  replaceEdgeAttributes(key, attributes) {
    this.edges.get(String(key)).attributes = { ...attributes }
  }
  forEachEdge(callback) {
    for (const [key, record] of this.edges) {
      callback(key, record.attributes, record.source, record.target)
    }
  }
  dropEdge(key) { this.edges.delete(String(key)) }
}

const nodeAttributes = node => ({ label: node.name, rawData: node })
const edgeAttributes = edge => ({ label: edge.label, rawData: edge })

test('large graph threshold can be selected by either nodes or edges', () => {
  assert.equal(shouldUseLargeGraphRenderer({ nodeCount: 499, edgeCount: 999 }), false)
  assert.equal(shouldUseLargeGraphRenderer({ nodeCount: 500, edgeCount: 10 }), true)
  assert.equal(shouldUseLargeGraphRenderer({ nodeCount: 20, edgeCount: 1000 }), true)
})

test('dense graphs replace the native edge picking buffer with click-time picking', () => {
  assert.equal(shouldEnableNativeEdgeEvents({ edgeCount: 5000 }), true)
  assert.equal(shouldEnableNativeEdgeEvents({ edgeCount: 5001 }), false)
})

test('massive graphs use the static first-paint profile at either limit', () => {
  assert.equal(shouldUseMassiveGraphProfile({ nodeCount: 1999, edgeCount: 7999 }), false)
  assert.equal(shouldUseMassiveGraphProfile({ nodeCount: 2000, edgeCount: 100 }), true)
  assert.equal(shouldUseMassiveGraphProfile({ nodeCount: 100, edgeCount: 8000 }), true)
})

test('layout attraction weakens symmetrically around high-degree hubs', () => {
  assert.equal(degreeAwareLayoutWeight({ sourceDegree: 1, targetDegree: 1 }), 1)
  assert.equal(degreeAwareLayoutWeight({ sourceDegree: 4, targetDegree: 2 }), 0.5)
  assert.equal(degreeAwareLayoutWeight({ sourceDegree: 2, targetDegree: 100 }), 0.25)
  assert.equal(degreeAwareLayoutWeight({ sourceDegree: 100, targetDegree: 2 }), 0.25)
})

test('massive edge labels are deterministic, diverse, and strictly budgeted', () => {
  const edges = Array.from({ length: 120 }, (_, index) => ({
    id: `e${index}`,
    source: index < 60 ? 'hub' : `n${index}`,
    target: `n${index + 1}`,
    label: index % 3 === 0 ? 'knows' : `relationship ${index}`,
  }))
  const first = selectBoundedEdgeLabelIds({ edges })
  const second = selectBoundedEdgeLabelIds({ edges })

  assert.equal(first.size, MASSIVE_GRAPH_EDGE_LABEL_BUDGET)
  assert.deepEqual([...first], [...second])
  assert.ok(first.has('e0'), 'a highly connected labelled edge should be represented')
})

test('massive edge label selection ignores blank labels and honors a smaller budget', () => {
  const selected = selectBoundedEdgeLabelIds({
    edges: [
      { id: 'blank', source: 'a', target: 'b', label: '  ' },
      { id: 'one', source: 'a', target: 'b', label: 'supports' },
      { id: 'two', source: 'b', target: 'c', label: 'causes' },
    ],
    maxLabels: 1,
  })
  assert.deepEqual([...selected], ['one'])
})

test('massive wheel input is accumulated into one bounded camera ratio', () => {
  assert.ok(accumulatedWheelZoomRatio({ currentRatio: 1, wheelSteps: 3 }) < 1)
  assert.ok(accumulatedWheelZoomRatio({ currentRatio: 1, wheelSteps: -3 }) > 1)
  assert.ok(Math.abs(
    accumulatedWheelZoomRatio({ currentRatio: 1, wheelSteps: 100 }) - (1 / (1.7 ** 4))
  ) < 1e-12)
  assert.equal(accumulatedWheelZoomRatio({ currentRatio: 1, wheelSteps: -100 }), 5)
})

test('click-time edge picking preserves direct selection for dense graphs', () => {
  const points = new Map([
    ['a', { x: 10, y: 10 }],
    ['b', { x: 110, y: 10 }],
    ['c', { x: 10, y: 80 }],
  ])
  const edges = [
    { id: 'horizontal', source: 'a', target: 'b' },
    { id: 'vertical', source: 'a', target: 'c' },
  ]

  assert.equal(findClosestEdgeAtPoint({
    edges,
    point: { x: 64, y: 13 },
    nodePoint: id => points.get(id),
  })?.id, 'horizontal')
  assert.equal(findClosestEdgeAtPoint({
    edges,
    point: { x: 45, y: 45 },
    nodePoint: id => points.get(id),
  }), null)
})

test('large graph layout settings are inferred without the synchronous layout bundle', () => {
  assert.deepEqual(inferLargeGraphLayoutSettings({ order: 100 }), {
    linLogMode: false,
    outboundAttractionDistribution: false,
    adjustSizes: false,
    edgeWeightInfluence: 1,
    barnesHutOptimize: false,
    barnesHutTheta: 0.7,
    strongGravityMode: true,
    gravity: 0.5,
    scalingRatio: 20,
    slowDown: 1 + Math.log(100),
  })
  assert.equal(inferLargeGraphLayoutSettings(500).barnesHutOptimize, true)
})

test('incremental sync preserves positions and places a new neighbour nearby', () => {
  const graph = new FakeGraph()
  syncGraphologyGraph(graph, {
    nodes: [{ id: 'alice', name: 'Alice' }],
    edges: [],
    nodeAttributes,
    edgeAttributes,
  })
  graph.nodes.get('alice').x = 120
  graph.nodes.get('alice').y = -45

  const result = syncGraphologyGraph(graph, {
    nodes: [
      { id: 'alice', name: 'Alice updated' },
      { id: 'bob', name: 'Bob' },
    ],
    edges: [{ id: 'knows', source: 'alice', target: 'bob', label: 'knows' }],
    nodeAttributes,
    edgeAttributes,
  })

  assert.equal(graph.getNodeAttributes('alice').x, 120)
  assert.equal(graph.getNodeAttributes('alice').y, -45)
  assert.equal(graph.getNodeAttributes('alice').label, 'Alice updated')
  assert.ok(Math.hypot(
    graph.getNodeAttributes('bob').x - 120,
    graph.getNodeAttributes('bob').y + 45,
  ) < 40)
  assert.equal(result.addedNodes, 1)
  assert.equal(result.addedEdges, 1)
  assert.equal(result.topologyChanged, true)
})

test('cooperative hydration yields between bounded slices and preserves the full graph', async () => {
  const graph = new FakeGraph()
  const nodes = Array.from({ length: 640 }, (_, index) => ({
    id: `n${index}`,
    name: `Node ${index}`,
  }))
  const edges = Array.from({ length: 2048 }, (_, index) => ({
    id: `e${index}`,
    source: `n${index % nodes.length}`,
    target: `n${(index * 17 + 1) % nodes.length}`,
    label: 'relates',
  }))
  edges.push({ id: 'invalid', source: 'n0', target: 'missing', label: 'invalid' })

  let clock = 0
  let yielded = 0
  const result = await hydrateGraphologyGraphCooperatively(graph, {
    nodes,
    edges,
    nodeAttributes,
    edgeAttributes,
    frameBudgetMs: 1,
    now: () => clock++,
    yieldControl: async () => { yielded += 1 },
  })

  assert.equal(graph.order, nodes.length)
  assert.equal(graph.size, edges.length - 1)
  assert.equal(result.invalidEdges.length, 1)
  assert.equal(result.aborted, false)
  assert.equal(result.yieldCount, yielded)
  assert.ok(yielded >= 5, `expected multiple cooperative yields, got ${yielded}`)
})

test('cooperative hydration can abort safely between slices', async () => {
  const graph = new FakeGraph()
  const nodes = Array.from({ length: 1000 }, (_, index) => ({ id: `n${index}` }))
  let clock = 0
  let abort = false

  const result = await hydrateGraphologyGraphCooperatively(graph, {
    nodes,
    edges: [],
    frameBudgetMs: 1,
    now: () => clock++,
    yieldControl: async () => { abort = true },
    shouldAbort: () => abort,
  })

  assert.equal(result.aborted, true)
  assert.ok(graph.order > 0)
  assert.ok(graph.order < nodes.length)
  assert.equal(graph.size, 0)
})

test('incremental sync removes stale data and replaces changed edge endpoints', () => {
  const graph = new FakeGraph()
  syncGraphologyGraph(graph, {
    nodes: [{ id: 'a' }, { id: 'b' }, { id: 'c' }],
    edges: [{ id: 'edge', source: 'a', target: 'b', label: 'old' }],
    nodeAttributes,
    edgeAttributes,
  })

  const result = syncGraphologyGraph(graph, {
    nodes: [{ id: 'a' }, { id: 'c' }],
    edges: [
      { id: 'edge', source: 'a', target: 'c', label: 'new' },
      { id: 'invalid', source: 'a', target: 'missing', label: 'ignored' },
    ],
    nodeAttributes,
    edgeAttributes,
  })

  assert.equal(graph.hasNode('b'), false)
  assert.equal(graph.source('edge'), 'a')
  assert.equal(graph.target('edge'), 'c')
  assert.equal(result.removedNodes, 1)
  assert.equal(result.removedEdges, 1)
  assert.equal(result.addedEdges, 1)
  assert.equal(result.invalidEdges.length, 1)
})

test('legacy parallel edges receive stable distinct fallback keys', () => {
  const graph = new FakeGraph()
  const payload = {
    nodes: [{ id: 'a' }, { id: 'b' }],
    edges: [
      { source: 'a', target: 'b', label: 'knows' },
      { source: 'a', target: 'b', label: 'knows' },
    ],
    nodeAttributes,
    edgeAttributes,
  }
  syncGraphologyGraph(graph, payload)
  const firstKeys = [...graph.edges.keys()]
  const result = syncGraphologyGraph(graph, payload)

  assert.equal(firstKeys.length, 2)
  assert.equal(new Set(firstKeys).size, 2)
  assert.deepEqual([...graph.edges.keys()], firstKeys)
  assert.equal(result.topologyChanged, false)
})

test('colorWithAlpha dims common CSS color formats', () => {
  assert.equal(colorWithAlpha('#f63', 0.2), 'rgba(255, 102, 51, 0.2)')
  assert.equal(colorWithAlpha('#004E89', 0.5), 'rgba(0, 78, 137, 0.5)')
  assert.equal(colorWithAlpha('rgb(12, 24, 36)', 0.1), 'rgba(12, 24, 36, 0.1)')
})
