import test from 'node:test'
import assert from 'node:assert/strict'

import { shouldAutoHideEdgeLabels, graphDensityMessage } from '../src/utils/graphPerformance.js'

test('edge labels are hidden automatically for dense graphs unless user overrides', () => {
  assert.equal(shouldAutoHideEdgeLabels({ edgeCount: 220, userOverrode: false }), true)
  assert.equal(shouldAutoHideEdgeLabels({ edgeCount: 220, userOverrode: true }), false)
  assert.equal(shouldAutoHideEdgeLabels({ edgeCount: 80, userOverrode: false }), false)
})

test('graphDensityMessage includes concrete graph size', () => {
  assert.equal(
    graphDensityMessage({ nodeCount: 120, edgeCount: 260 }),
    '120 nodes / 260 links'
  )
})
