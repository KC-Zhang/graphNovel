import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { isRangeCovered } from '../src/utils/readProgress.js'

const readerSrc = readFileSync(
  fileURLToPath(new URL('../src/views/ReaderView.vue', import.meta.url)),
  'utf8'
)

test('turning to the next chapter no longer marks page edges as seen', () => {
  // The page-turn clearing helper must be gone entirely.
  assert.ok(!readerSrc.includes('markCurrentPageEdgesSeen'), 'markCurrentPageEdgesSeen should be removed')
  // nextEpisode should only advance the chapter, not clear links.
  const nextBody = readerSrc.match(/const nextEpisode = \(\) => \{([\s\S]*?)\}/)
  assert.ok(nextBody, 'nextEpisode should exist')
  assert.ok(!/markEdgeSeen|markCurrentPageEdgesSeen/.test(nextBody[1]), 'nextEpisode must not clear links')
})

test('link clearing is driven by interval coverage', () => {
  // Reader relies on coverage-based marking for edges.
  assert.ok(readerSrc.includes('markCoveredEdges'), 'markCoveredEdges should drive edge clearing')
  assert.ok(readerSrc.includes('isRangeCovered'), 'reader should use isRangeCovered for edges')
})

test('a link above a mid-chapter jump stays unseen until scrolled into a covered range', () => {
  // Simulate: user is linked into the middle; only [0.5, 0.7] has been viewed.
  const viewed = [[0.5, 0.7]]
  const linkAbove = [0.1, 0.13]
  const linkInView = [0.55, 0.58]
  assert.equal(isRangeCovered(viewed, linkAbove), false)
  assert.equal(isRangeCovered(viewed, linkInView), true)
})
