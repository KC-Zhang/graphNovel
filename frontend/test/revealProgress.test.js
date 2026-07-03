import test from 'node:test'
import assert from 'node:assert/strict'
import { clampRevealMax, latestReadableEpisode } from '../src/utils/revealProgress.js'

test('clampRevealMax keeps reveal cap within chapter bounds', () => {
  assert.equal(clampRevealMax(-3, 5), 0)
  assert.equal(clampRevealMax(2, 5), 2)
  assert.equal(clampRevealMax(10, 5), 4)
})

test('clampRevealMax returns zero when there are no chapters', () => {
  assert.equal(clampRevealMax(4, 0), 0)
  assert.equal(clampRevealMax(4, -1), 0)
})

test('latestReadableEpisode uses current view, read chapters, ranges, and extra reached episodes', () => {
  assert.equal(
    latestReadableEpisode({
      viewEpisode: 1,
      readEpisodes: new Set([0, 3]),
      episodeRanges: { 4: [[0, 0.2]] },
      total: 8,
      extraEpisodes: [6],
    }),
    6
  )
})

test('latestReadableEpisode clamps restored targets to existing chapters', () => {
  assert.equal(
    latestReadableEpisode({
      viewEpisode: 2,
      readEpisodes: [12],
      episodeRanges: { 20: [[0.1, 0.3]] },
      total: 5,
    }),
    4
  )
})
