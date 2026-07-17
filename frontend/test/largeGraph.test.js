import test from 'node:test'
import assert from 'node:assert/strict'

import {
  colorWithAlpha,
  inferLargeGraphLayoutSettings,
  shouldUseLargeGraphRenderer,
  syncGraphologyGraph,
} from '../src/utils/largeGraph.js'

class FakeGraph {
  constructor() {
    this.nodes = new Map()
    this.edges = new Map()
  }

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

test('large graph layout settings are inferred without the synchronous layout bundle', () => {
  assert.deepEqual(inferLargeGraphLayoutSettings({ order: 100 }), {
    barnesHutOptimize: false,
    strongGravityMode: true,
    gravity: 0.05,
    scalingRatio: 10,
    slowDown: 1 + Math.log(100),
  })
  assert.equal(inferLargeGraphLayoutSettings(2001).barnesHutOptimize, true)
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
