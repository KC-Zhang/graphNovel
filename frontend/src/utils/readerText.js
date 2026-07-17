const headingPattern = /^(?:chapter|part|book)\s+(?:\d+|[ivxlcdm]+)\b|^第\s*[\d一二三四五六七八九十百千零两〇]+\s*[章回卷篇部]/i

const looksLikeHeading = (line) => {
  const value = String(line || '').trim()
  if (!value || value.length > 90) return false
  if (headingPattern.test(value)) return true
  const letters = value.replace(/[^A-Za-z]/g, '')
  return letters.length >= 4 && letters === letters.toUpperCase() && value.split(/\s+/).length <= 12
}

const shouldEndParagraph = (line, accumulatedLength) =>
  accumulatedLength >= 120 && /[.!?。！？][”’"')\]]?$/.test(String(line || '').trim())

/**
 * Build render blocks while retaining raw character offsets used by search and
 * graph mentions. PDF chapter text is reflowed across soft line breaks; source
 * formats with intentional line structure keep the previous line-by-line view.
 */
export const readerTextBlocks = (text, { reflow = false } = {}) => {
  const source = String(text || '')
  if (!source) return []
  if (!reflow) {
    const blocks = []
    let offset = 0
    source.split('\n').forEach((line) => {
      const start = offset
      offset += line.length + 1
      if (line.trim()) blocks.push({ text: line, start, end: start + line.length, heading: false })
    })
    return blocks
  }

  const lines = source.split('\n')
  const blocks = []
  let rawOffset = 0
  let current = null

  const flush = () => {
    if (!current) return
    current.text = source.slice(current.start, current.end)
    blocks.push(current)
    current = null
  }

  lines.forEach((line) => {
    const start = rawOffset
    const end = start + line.length
    rawOffset = end + 1
    const trimmed = line.trim()
    if (!trimmed) {
      flush()
      return
    }
    if (looksLikeHeading(trimmed)) {
      flush()
      blocks.push({ text: line, start, end, heading: true })
      return
    }
    if (!current) current = { text: '', start, end, heading: false }
    else current.end = end
    if (shouldEndParagraph(line, current.end - current.start)) flush()
  })
  flush()
  return blocks
}

