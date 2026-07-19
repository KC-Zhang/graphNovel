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

export const createQuoteMatcher = (text) => {
  const source = String(text || '')
  const lookups = source ? [false, true].map(stripPunct => ({
    stripPunct,
    ...buildNormalized(source, stripPunct),
  })) : []

  return (quote) => {
    const q = cleanQuote(quote)
    if (!source || !q) return null
    let bestFallback = null

    for (const { stripPunct, norm, map } of lookups) {
      const nq = buildNormalized(q, stripPunct).norm
      if (!nq) continue

      let idx = norm.indexOf(nq)
      if (idx !== -1) {
        return { start: map[idx], end: map[idx + nq.length - 1] + 1 }
      }

      if (nq.length < 6) continue
      const seed = nq.slice(0, 6)
      let searchFrom = 0
      while (searchFrom <= norm.length - seed.length) {
        idx = norm.indexOf(seed, searchFrom)
        if (idx < 0) break
        let length = seed.length
        while (
          length < nq.length
          && idx + length < norm.length
          && norm[idx + length] === nq[length]
        ) length += 1
        if (!bestFallback || length > bestFallback.length) {
          bestFallback = { map, idx, length }
        }
        searchFrom = idx + 1
      }
    }
    return bestFallback
      ? {
          start: bestFallback.map[bestFallback.idx],
          end: bestFallback.map[bestFallback.idx + bestFallback.length - 1] + 1,
        }
      : null
  }
}

export const findQuoteRange = (text, quote) => createQuoteMatcher(text)(quote)

export const GRAPH_SCOPES = Object.freeze({
  CURRENT: 'current',
  UPTO: 'upto',
  ALL: 'all',
})

export const normalizeGraphScope = (scope) => (
  Object.values(GRAPH_SCOPES).includes(scope) ? scope : GRAPH_SCOPES.UPTO
)

export const scopeEpisodeLimit = ({ scope = GRAPH_SCOPES.UPTO, viewEpisode = 0, total = 0 } = {}) => {
  const normalized = normalizeGraphScope(scope)
  if (normalized === GRAPH_SCOPES.ALL) {
    return Number.isFinite(total) && total > 0 ? total - 1 : Infinity
  }
  const episode = Number(viewEpisode)
  if (episode === Infinity) return Infinity
  return Number.isFinite(episode) ? Math.max(0, episode) : 0
}

export const scopeAllowsMention = (episode, options = {}) => {
  const normalized = normalizeGraphScope(options.scope)
  if (normalized === GRAPH_SCOPES.ALL) return true
  const ep = Number(episode)
  const viewEpisode = scopeEpisodeLimit(options)
  if (!Number.isFinite(ep)) return false
  if (normalized === GRAPH_SCOPES.CURRENT) return ep === viewEpisode
  return ep <= viewEpisode
}

export const createMentionIndex = (graphData, options = Infinity) => {
  const index = new Map()
  const scopeOptions = typeof options === 'number'
    ? { scope: GRAPH_SCOPES.UPTO, viewEpisode: options }
    : { ...(options || {}), scope: normalizeGraphScope(options?.scope) }

  const pushMentions = (item, type, name) => {
    const firstEpisode = item.first_episode ?? 0
    if (scopeOptions.scope === GRAPH_SCOPES.UPTO && firstEpisode > scopeEpisodeLimit(scopeOptions)) return
    if (scopeOptions.scope === GRAPH_SCOPES.CURRENT && !(item.mentions || []).some(m => scopeAllowsMention(m.episode, scopeOptions))) return

    for (const mention of (item.mentions || [])) {
      if (!scopeAllowsMention(mention.episode, scopeOptions)) continue
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
