import test from 'node:test'
import assert from 'node:assert/strict'

import {
  clamp01,
  visibleInterval,
  addInterval,
  mergeIntervals,
  coverage,
  isRangeCovered,
} from '../src/utils/readProgress.js'

test('clamp01 keeps values within [0, 1]', () => {
  assert.equal(clamp01(-0.5), 0)
  assert.equal(clamp01(0.4), 0.4)
  assert.equal(clamp01(2), 1)
  assert.equal(clamp01(NaN), 0)
})

test('visibleInterval returns full range for non-scrollable content', () => {
  assert.deepEqual(visibleInterval(0, 500, 500), [0, 1])
  assert.deepEqual(visibleInterval(0, 500, 400), [0, 1])
})

test('visibleInterval maps scroll position to a clamped normalized interval', () => {
  // scrollHeight 1000, viewport 200 -> [0, 0.2]
  assert.deepEqual(visibleInterval(0, 200, 1000), [0, 0.2])
  // scrolled halfway -> [0.4, 0.6]
  assert.deepEqual(visibleInterval(400, 200, 1000), [0.4, 0.6])
  // scrolled to bottom clamps end to 1
  assert.deepEqual(visibleInterval(800, 200, 1000), [0.8, 1])
})

test('mergeIntervals merges overlapping and adjacent intervals', () => {
  assert.deepEqual(mergeIntervals([[0, 0.3], [0.2, 0.5]]), [[0, 0.5]])
  // adjacent within epsilon merge into one
  assert.deepEqual(mergeIntervals([[0, 0.3], [0.3005, 0.5]]), [[0, 0.5]])
})

test('mergeIntervals keeps non-contiguous intervals separate', () => {
  assert.deepEqual(mergeIntervals([[0, 0.2], [0.5, 0.7]]), [[0, 0.2], [0.5, 0.7]])
})

test('mergeIntervals drops invalid entries and sorts input', () => {
  assert.deepEqual(
    mergeIntervals([[0.5, 0.7], [0.9, 0.9], [0, 0.2], null, [0.3, NaN]]),
    [[0, 0.2], [0.5, 0.7]]
  )
})

test('addInterval merges a single interval into the set', () => {
  const ranges = addInterval([[0, 0.2]], [0.15, 0.4])
  assert.deepEqual(ranges, [[0, 0.4]])
})

test('coverage sums merged segment lengths', () => {
  assert.ok(Math.abs(coverage([[0, 0.2], [0.5, 0.7]]) - 0.4) < 1e-9)
  // overlapping segments are not double counted
  assert.ok(Math.abs(coverage([[0, 0.3], [0.2, 0.5]]) - 0.5) < 1e-9)
})

test('isRangeCovered detects fully covered sub-ranges', () => {
  const ranges = [[0.1, 0.5]]
  assert.equal(isRangeCovered(ranges, [0.2, 0.4]), true)
  // partially outside coverage
  assert.equal(isRangeCovered(ranges, [0.4, 0.6]), false)
  // above a mid-chapter jump stays uncovered
  assert.equal(isRangeCovered(ranges, [0.0, 0.05]), false)
})

test('isRangeCovered honors the boundary tolerance', () => {
  const ranges = [[0.1, 0.5]]
  // just outside by less than tolerance still counts as covered
  assert.equal(isRangeCovered(ranges, [0.097, 0.503], 0.005), true)
  assert.equal(isRangeCovered(ranges, [0.09, 0.51], 0.005), false)
})
