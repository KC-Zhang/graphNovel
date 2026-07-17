import test from 'node:test'
import assert from 'node:assert/strict'
import { graphNeedsRefresh, mergeGraphPayload } from '../src/utils/graphDelta.js'

test('merges graph deltas without losing earlier mentions', () => {
  const current = {
    nodes: [{ id: 'n1', name: 'Alice', mentions: [{ episode: 0, quote: 'Alice' }] }],
    edges: [],
  }
  const delta = {
    mode: 'delta',
    revision_episode: 1,
    nodes: [{ id: 'n1', name: 'Alice A.', mentions: [{ episode: 1, quote: 'Alice returns' }] }],
    edges: [{ id: 'e1', source: 'n1', target: 'n2', mentions: [] }],
  }

  const merged = mergeGraphPayload(current, delta)
  assert.equal(merged.nodes[0].name, 'Alice A.')
  assert.equal(merged.nodes[0].mentions.length, 2)
  assert.equal(merged.edges.length, 1)
  assert.equal(merged.revision_episode, 1)
})

test('full graph payload replaces previous graph', () => {
  const merged = mergeGraphPayload(
    { nodes: [{ id: 'old' }], edges: [{ id: 'old-edge' }] },
    { mode: 'full', nodes: [{ id: 'new' }], edges: [] },
  )
  assert.deepEqual(merged.nodes.map(node => node.id), ['new'])
  assert.deepEqual(merged.edges, [])
})

test('graph refresh follows the persisted graph revision, not status observation', () => {
  assert.equal(graphNeedsRefresh({ extractedUpto: 2, graphRevision: 1 }), true)
  assert.equal(graphNeedsRefresh({ extractedUpto: 2, graphRevision: 2 }), false)
  assert.equal(graphNeedsRefresh({ extractedUpto: 2, graphRevision: 2, failedChanged: true }), true)
})
