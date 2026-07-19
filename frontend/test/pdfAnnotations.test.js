import test from 'node:test'
import assert from 'node:assert/strict'

import { createPdfAnnotationPlan, createPdfSpanMatcher } from '../src/utils/pdfAnnotations.js'

test('PDF span matching ignores layout splits, whitespace, and punctuation differences', () => {
  const spans = [
    '1',
    'Fudan University, ',
    '2',
    'StepFun',
  ]
  const match = createPdfSpanMatcher(spans)('1Fudan University 2StepFun')

  assert.deepEqual(match.start, { spanIndex: 0, offset: 0 })
  assert.deepEqual(match.end, { spanIndex: 3, offset: 7 })
})

test('PDF annotation plan marks exact text fragments and preserves first-link priority', () => {
  const spans = ['The CoSER dataset covers 17,966 characters from 771 books.']
  const links = [
    { type: 'node', id: 'dataset', text: 'CoSER dataset' },
    { type: 'edge', id: 'contains', text: 'CoSER dataset covers 17,966 characters' },
  ]
  const plan = createPdfAnnotationPlan(spans, links, '17,966 characters')

  assert.deepEqual(plan.spans[0], [
    { text: 'The ', linkIndex: -1, highlight: false },
    { text: 'CoSER dataset', linkIndex: 0, highlight: false },
    { text: ' covers ', linkIndex: 1, highlight: false },
    { text: '17,966 characters', linkIndex: 1, highlight: true },
    { text: ' from 771 books.', linkIndex: -1, highlight: false },
  ])
})

test('PDF annotation plan uses the matched source slice before a non-verbatim quote', () => {
  const spans = ['The CoSER dataset covers 17,966 characters from 771 renowned books.']
  const links = [{
    type: 'node',
    id: 'dataset',
    text: 'The CoSER dataset covers 17,966 characters from 771 renowned books',
    quote: 'The CoSER dataset covers 17,966 characters and rearranged words',
  }]
  const plan = createPdfAnnotationPlan(spans, links)

  assert.equal(plan.spans[0].filter(segment => segment.linkIndex === 0).map(segment => segment.text).join(''), links[0].text)
})
