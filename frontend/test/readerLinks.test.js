import test from 'node:test'
import assert from 'node:assert/strict'

import {
  GRAPH_SCOPES,
  createQuoteMatcher,
  createMentionIndex,
  findQuoteRange,
  scopeEpisodeLimit,
  shouldMarkLinkRead,
} from '../src/utils/readerLinks.js'

test('findQuoteRange tolerates whitespace and punctuation differences', () => {
  const text = 'Alice said: "Never eat alone." Then Bob nodded.'
  const range = findQuoteRange(text, 'Never Eat Alone')

  assert.deepEqual(text.slice(range.start, range.end), 'Never eat alone')
})

test('one quote matcher supports multiple mentions in the same chapter', () => {
  const text = 'Alice arrived first. Later, Bob met Alice.'
  const findQuote = createQuoteMatcher(text)
  assert.equal(text.slice(...Object.values(findQuote('Alice arrived'))), 'Alice arrived')
  assert.equal(text.slice(...Object.values(findQuote('Bob met Alice'))), 'Bob met Alice')
})

test('quote matcher keeps the longest reliable prefix of a non-verbatim mention', () => {
  const text = 'The CoSER dataset covers 17,966 characters from 771 renowned books. It provides authentic dialogues.'
  const quote = 'The CoSER dataset covers 17,966 characters from 771 renowned books. It provides rearranged data.'
  const range = findQuoteRange(text, quote)

  assert.equal(
    text.slice(range.start, range.end),
    'The CoSER dataset covers 17,966 characters from 771 renowned books. It provides',
  )
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

test('createMentionIndex filters future mentions inside already-revealed items', () => {
  const graph = {
    nodes: [
      {
        id: 'n1',
        name: 'Alice',
        first_episode: 0,
        mentions: [
          { episode: 0, quote: 'Alice arrives' },
          { episode: 3, quote: 'Alice reveals the ending' },
        ],
      },
    ],
    edges: [],
  }

  const index = createMentionIndex(graph, {
    scope: GRAPH_SCOPES.UPTO,
    viewEpisode: 1,
    total: 4,
  })

  assert.equal(index.has(0), true)
  assert.equal(index.has(3), false)
})

test('createMentionIndex supports current-chapter and all scope', () => {
  const graph = {
    nodes: [
      {
        id: 'n1',
        name: 'Alice',
        first_episode: 0,
        mentions: [
          { episode: 0, quote: 'Alice first' },
          { episode: 2, quote: 'Alice current' },
        ],
      },
    ],
    edges: [],
  }

  const current = createMentionIndex(graph, {
    scope: GRAPH_SCOPES.CURRENT,
    viewEpisode: 2,
    total: 3,
  })
  const all = createMentionIndex(graph, {
    scope: GRAPH_SCOPES.ALL,
    viewEpisode: 0,
    total: 3,
  })

  assert.equal(current.has(0), false)
  assert.equal(current.get(2).length, 1)
  assert.equal(all.get(0).length, 1)
  assert.equal(all.get(2).length, 1)
})

test('scopeEpisodeLimit maps all mode to the final episode', () => {
  assert.equal(scopeEpisodeLimit({ scope: GRAPH_SCOPES.CURRENT, viewEpisode: 2, total: 5 }), 2)
  assert.equal(scopeEpisodeLimit({ scope: GRAPH_SCOPES.UPTO, viewEpisode: 2, total: 5 }), 2)
  assert.equal(scopeEpisodeLimit({ scope: GRAPH_SCOPES.ALL, viewEpisode: 2, total: 5 }), 4)
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
