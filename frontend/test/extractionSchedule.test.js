import test from 'node:test'
import assert from 'node:assert/strict'

import { fullBookExtractionTarget } from '../src/utils/extractionSchedule.js'

test('whole-book extraction is scheduled independently of the current display scope', () => {
  assert.equal(fullBookExtractionTarget(44), 43)
  assert.equal(fullBookExtractionTarget(3), 2)
  assert.equal(fullBookExtractionTarget(1), 0)
})

test('empty and invalid episode totals do not schedule extraction', () => {
  assert.equal(fullBookExtractionTarget(0), -1)
  assert.equal(fullBookExtractionTarget(-4), -1)
  assert.equal(fullBookExtractionTarget(Number.NaN), -1)
})
