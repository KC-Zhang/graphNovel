import test from 'node:test'
import assert from 'node:assert/strict'
import { readerTextBlocks } from '../src/utils/readerText.js'

test('reflows PDF soft line breaks into one render block', () => {
  const text = 'This is a line broken by the PDF\nlayout engine before the sentence ends.\n\nA second paragraph.'
  const blocks = readerTextBlocks(text, { reflow: true })
  assert.equal(blocks.length, 2)
  assert.equal(blocks[0].text, 'This is a line broken by the PDF\nlayout engine before the sentence ends.')
  assert.equal(text.slice(blocks[0].start, blocks[0].end), blocks[0].text)
})

test('keeps chapter headings separate while preserving offsets', () => {
  const text = 'CHAPTER 2\nA Better Reader\nBody text continues on\nthe next visual line.'
  const blocks = readerTextBlocks(text, { reflow: true })
  assert.equal(blocks[0].heading, true)
  assert.equal(blocks[0].text, 'CHAPTER 2')
  assert.equal(text.slice(blocks.at(-1).start, blocks.at(-1).end), blocks.at(-1).text)
})

