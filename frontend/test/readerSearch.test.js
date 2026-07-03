import test from 'node:test'
import assert from 'node:assert/strict'
import {
  findTextMatches,
  makeSnippet,
  orderSearchResults,
  searchBodyTexts,
  searchGraphData,
} from '../src/utils/readerSearch.js'

const graphData = {
  nodes: [
    {
      id: 'n1',
      name: 'Alice',
      type: 'Person',
      aliases: ['The Cartographer'],
      description: 'Keeps the old map.',
      first_episode: 2,
      mentions: [{ episode: 2, quote: 'Alice studies the river crossing.' }],
    },
    {
      id: 'n2',
      name: 'Bob',
      type: 'Person',
      aliases: [],
      description: 'Station keeper.',
      first_episode: 0,
      mentions: [],
    },
  ],
  edges: [
    {
      id: 'e1',
      source: 'n1',
      target: 'n2',
      label: 'trusts',
      fact: 'Alice trusts Bob with the map.',
      first_episode: 3,
      mentions: [{ episode: 3, quote: 'The map stayed with Bob.' }],
    },
  ],
}

test('searchGraphData matches node aliases and descriptions', () => {
  const results = searchGraphData(graphData, 'cartographer')
  assert.equal(results.length, 1)
  assert.equal(results[0].kind, 'node')
  assert.equal(results[0].id, 'n1')
  assert.equal(results[0].episode, 2)
})

test('searchGraphData matches edge labels, facts, and endpoint names', () => {
  assert.equal(searchGraphData(graphData, 'trusts')[0].kind, 'edge')
  assert.equal(searchGraphData(graphData, 'old map')[0].id, 'n1')
  assert.equal(searchGraphData(graphData, 'alice trusts bob')[0].id, 'e1')
})

test('orderSearchResults places nodes before edges before body matches', () => {
  const ordered = orderSearchResults([
    { kind: 'body', title: 'Body', episode: 0 },
    { kind: 'edge', title: 'Edge', episode: 0 },
    { kind: 'node', title: 'Node', episode: 0 },
  ])
  assert.deepEqual(ordered.map((result) => result.kind), ['node', 'edge', 'body'])
})

test('searchBodyTexts orders body results by chapter and offset', () => {
  const episodes = [{ index: 0, title: 'One' }, { index: 1, title: 'Two' }]
  const textsByEpisode = new Map([
    [0, 'Alpha beta alpha.'],
    [1, 'Beta alpha.'],
  ])
  const results = searchBodyTexts({ episodes, textsByEpisode, query: 'alpha' })
  assert.deepEqual(results.map((result) => [result.episode, result.start]), [[0, 0], [0, 11], [1, 5]])
})

test('findTextMatches is case-insensitive and supports Chinese substring matching', () => {
  assert.deepEqual(findTextMatches('Alice met ALICE.', 'alice').map((m) => m.start), [0, 10])
  assert.deepEqual(findTextMatches('宝玉见黛玉，黛玉微笑。', '黛玉').map((m) => m.start), [3, 6])
})

test('makeSnippet handles matches near text boundaries', () => {
  assert.equal(makeSnippet('Alice starts here and walks onward.', 0, 5, 8), 'Alice starts...')
  assert.equal(makeSnippet('A long road ends with Clara', 22, 27, 8), '...with Clara')
})
