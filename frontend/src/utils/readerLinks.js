export const buildNormalized = (text, stripPunct = false) => {
  let norm = ''
  const map = []
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (/\s/.test(ch)) continue
    if (stripPunct && !/[\p{L}\p{N}]/u.test(ch)) continue
    norm += ch.toLowerCase()
    map.push(i)
  }
  return { norm, map }
}

export const cleanQuote = (quote) => {
  return (quote || '')
    .trim()
    .replace(/^[\s"'“”‘’「」『』（(\[【]+/, '')
    .replace(/[\s"'“”‘’「」『』）)\]】]+$/, '')
    .replace(/^(?:\.{3,}|…+)/, '')
    .replace(/(?:\.{3,}|…+)$/, '')
    .trim()
}

export const findQuoteRange = (text, quote) => {
  const q = cleanQuote(quote)
  if (!text || !q) return null

  for (const stripPunct of [false, true]) {
    const { norm, map } = buildNormalized(text, stripPunct)
    const nq = buildNormalized(q, stripPunct).norm
    if (!nq) continue

    let idx = norm.indexOf(nq)
    if (idx !== -1) {
      return { start: map[idx], end: map[idx + nq.length - 1] + 1 }
    }

    const probeMax = Math.min(nq.length, 16)
    for (let len = probeMax; len >= 6; len -= 2) {
      const probe = nq.slice(0, len)
      idx = norm.indexOf(probe)
      if (idx !== -1) {
        return { start: map[idx], end: map[idx + len - 1] + 1 }
      }
    }
  }
  return null
}

export const createMentionIndex = (graphData, maxReveal = Infinity) => {
  const index = new Map()
  const pushMentions = (item, type, name) => {
    if ((item.first_episode ?? 0) > maxReveal) return
    for (const mention of (item.mentions || [])) {
      if (!index.has(mention.episode)) index.set(mention.episode, [])
      index.get(mention.episode).push({
        quote: mention.quote,
        type,
        id: item.id,
        name,
        firstEpisode: item.first_episode ?? 0,
      })
    }
  }

  ;(graphData?.nodes || []).forEach(node => pushMentions(node, 'node', node.name || ''))
  ;(graphData?.edges || []).forEach(edge => pushMentions(edge, 'edge', edge.label || ''))

  for (const links of index.values()) {
    links.sort((a, b) => {
      if (a.type === b.type) return 0
      return a.type === 'node' ? -1 : 1
    })
  }
  return index
}

export const DEFAULT_SCROLL_READ_THRESHOLD_PX = 4

export const shouldMarkLinkRead = ({
  linkBottom,
  viewportTop,
  thresholdPx = DEFAULT_SCROLL_READ_THRESHOLD_PX,
}) => {
  if (!Number.isFinite(linkBottom) || !Number.isFinite(viewportTop)) return false
  return linkBottom <= viewportTop + thresholdPx
}
