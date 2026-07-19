const normalizeText = (value, stripPunct = false) => {
  let normalized = ''
  for (const sourceChar of String(value || '').normalize('NFKC').toLocaleLowerCase()) {
    if (/\s/u.test(sourceChar)) continue
    if (stripPunct && !/[\p{L}\p{N}]/u.test(sourceChar)) continue
    normalized += sourceChar
  }
  return normalized
}

const buildSpanIndex = (spanTexts, stripPunct) => {
  let normalized = ''
  const positions = []

  spanTexts.forEach((sourceText, spanIndex) => {
    let offset = 0
    for (const sourceChar of String(sourceText || '')) {
      const compatible = sourceChar.normalize('NFKC').toLocaleLowerCase()
      for (const normalizedChar of compatible) {
        if (/\s/u.test(normalizedChar)) continue
        if (stripPunct && !/[\p{L}\p{N}]/u.test(normalizedChar)) continue
        normalized += normalizedChar
        positions.push({ spanIndex, offset, length: sourceChar.length })
      }
      offset += sourceChar.length
    }
  })

  return { normalized, positions, stripPunct }
}

const longestPrefixMatch = (haystack, needle, minimum = 6) => {
  if (needle.length < minimum) return null
  const seed = needle.slice(0, minimum)
  let searchFrom = 0
  let best = null

  while (searchFrom <= haystack.length - seed.length) {
    const start = haystack.indexOf(seed, searchFrom)
    if (start < 0) break
    let length = seed.length
    while (
      length < needle.length
      && start + length < haystack.length
      && haystack[start + length] === needle[length]
    ) length += 1

    if (!best || length > best.length) best = { start, length }
    searchFrom = start + 1
  }

  return best
}

const toSpanRange = (index, start, length) => {
  const first = index.positions[start]
  const last = index.positions[start + length - 1]
  if (!first || !last) return null
  return {
    start: { spanIndex: first.spanIndex, offset: first.offset },
    end: { spanIndex: last.spanIndex, offset: last.offset + last.length },
    matchedLength: length,
  }
}

export const createPdfSpanMatcher = (spanTexts) => {
  const indexes = [false, true].map(stripPunct => buildSpanIndex(spanTexts, stripPunct))

  return (query) => {
    let bestFallback = null
    for (const index of indexes) {
      const needle = normalizeText(query, index.stripPunct)
      if (!needle) continue

      const exactStart = index.normalized.indexOf(needle)
      if (exactStart >= 0) return toSpanRange(index, exactStart, needle.length)

      const fallback = longestPrefixMatch(index.normalized, needle)
      if (!fallback || (bestFallback && fallback.length <= bestFallback.length)) continue
      bestFallback = { index, ...fallback }
    }

    return bestFallback
      ? toSpanRange(bestFallback.index, bestFallback.start, bestFallback.length)
      : null
  }
}

const applyRange = (spanTexts, match, callback) => {
  if (!match) return
  for (let spanIndex = match.start.spanIndex; spanIndex <= match.end.spanIndex; spanIndex += 1) {
    const textLength = String(spanTexts[spanIndex] || '').length
    const start = spanIndex === match.start.spanIndex ? match.start.offset : 0
    const end = spanIndex === match.end.spanIndex ? match.end.offset : textLength
    if (end > start) callback(spanIndex, start, end)
  }
}

export const createPdfAnnotationPlan = (spanTexts, links = [], highlightText = '') => {
  const texts = spanTexts.map(value => String(value || ''))
  const findMatch = createPdfSpanMatcher(texts)
  const states = texts.map(text => ({
    linkAt: Array(text.length).fill(-1),
    highlightAt: Array(text.length).fill(false),
  }))

  links.forEach((link, linkIndex) => {
    const match = findMatch(link.text || link.quote || link.name)
    applyRange(texts, match, (spanIndex, start, end) => {
      const linkAt = states[spanIndex].linkAt
      for (let offset = start; offset < end; offset += 1) {
        // ReaderView orders node links before relationship links. Preserve that
        // priority instead of allowing later overlapping PDF matches to win.
        if (linkAt[offset] < 0) linkAt[offset] = linkIndex
      }
    })
  })

  const highlightMatch = findMatch(highlightText)
  applyRange(texts, highlightMatch, (spanIndex, start, end) => {
    states[spanIndex].highlightAt.fill(true, start, end)
  })

  const spans = texts.map((text, spanIndex) => {
    if (!text) return []
    const { linkAt, highlightAt } = states[spanIndex]
    const segments = []
    let start = 0

    for (let offset = 1; offset <= text.length; offset += 1) {
      const boundary = offset === text.length
        || linkAt[offset] !== linkAt[start]
        || highlightAt[offset] !== highlightAt[start]
      if (!boundary) continue
      segments.push({
        text: text.slice(start, offset),
        linkIndex: linkAt[start],
        highlight: highlightAt[start],
      })
      start = offset
    }
    return segments
  })

  return { spans, hasHighlight: !!highlightMatch }
}
