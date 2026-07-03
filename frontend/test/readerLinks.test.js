import test from 'node:test'
import assert from 'node:assert/strict'

import { createMentionIndex, findQuoteRange, shouldMarkLinkRead } from '../src/utils/readerLinks.js'

test('findQuoteRange tolerates whitespace and punctuation differences', () => {
  const text = 'Alice said: "Never eat alone." Then Bob nodded.'
  const range = findQuoteRange(text, 'Never Eat Alone')

  assert.deepEqual(text.slice(range.start, range.end), 'Never eat alone')
})

test('createMentionIndex groups only revealed mentions by episode', () => {
  const graph = {
    nodes: [
      { id: 'n1', name: 'Alice', first_episode: 0, mentions: [{ episode: 0, quote: 'Alice' }] },
      { id: 'n2', name: 'Future', first_episode: 3, mentions: [{ episode: 1, quote: 'Future' }] },
    ],
    edges: [
      { id: 'e1', label: 'knows', first_episode: 1, mentions: [{ episode: 1, quote: 'Alice knows Bob' }] },
    ],
  }

  const index = createMentionIndex(graph, 1)

  assert.equal(index.get(0).length, 1)
  assert.equal(index.get(1).length, 1)
  assert.equal(index.has(3), false)
  assert.equal(index.get(1)[0].type, 'edge')
})

test('shouldMarkLinkRead waits until a link scrolls past the viewport top', () => {
  assert.equal(shouldMarkLinkRead({ linkBottom: 130, viewportTop: 100 }), false)
  assert.equal(shouldMarkLinkRead({ linkBottom: 105, viewportTop: 100 }), false)
  assert.equal(shouldMarkLinkRead({ linkBottom: 104, viewportTop: 100 }), true)
  assert.equal(shouldMarkLinkRead({ linkBottom: 80, viewportTop: 100 }), true)
})

test('shouldMarkLinkRead supports explicit threshold boundaries', () => {
  assert.equal(shouldMarkLinkRead({ linkBottom: 111, viewportTop: 100, thresholdPx: 10 }), false)
  assert.equal(shouldMarkLinkRead({ linkBottom: 110, viewportTop: 100, thresholdPx: 10 }), true)
})
