const RESULT_ORDER = { node: 0, edge: 1, body: 2 }

export const normalizeSearchQuery = (query) => (query || '').trim().toLocaleLowerCase()

const normalizeText = (value) => String(value || '').toLocaleLowerCase()

const stripSnippetWhitespace = (value) => String(value || '').replace(/\s+/g, ' ').trim()

export const makeSnippet = (text, start = 0, end = start, radius = 42) => {
  const source = String(text || '')
  if (!source) return ''
  const safeStart = Math.max(0, Math.min(start, source.length))
  const safeEnd = Math.max(safeStart, Math.min(end, source.length))
  const from = Math.max(0, safeStart - radius)
  const to = Math.min(source.length, safeEnd + radius)
  const prefix = from > 0 ? '...' : ''
  const suffix = to < source.length ? '...' : ''
  const rawSnippet = source.slice(from, to)
  let snippet = rawSnippet
  if (from > 0 && /\s/.test(snippet)) snippet = snippet.replace(/^\S*\s*/, '')
  if (to < source.length && /\s/.test(snippet)) snippet = snippet.replace(/\s+\S*$/, '')
  snippet = stripSnippetWhitespace(snippet || rawSnippet)
  return prefix + snippet + suffix
}

const firstMatch = (fields, query) => {
  const q = normalizeSearchQuery(query)
  if (!q) return null
  for (const field of fields) {
    const text = String(field?.text || '')
    const idx = normalizeText(text).indexOf(q)
    if (idx >= 0) {
      return {
        field: field.name || '',
        text,
        start: idx,
        end: idx + q.length,
      }
    }
  }
  return null
}

const mentionFields = (mentions = []) =>
  mentions.map((mention) => ({ name: 'quote', text: mention?.quote || '' }))

const firstMentionEpisode = (item) => {
  if (Number.isFinite(item?.first_episode)) return item.first_episode
  const episode = item?.mentions?.find((mention) => Number.isFinite(mention?.episode))?.episode
  return Number.isFinite(episode) ? episode : 0
}

const nodeFields = (node) => [
  { name: 'name', text: node?.name || '' },
  { name: 'type', text: node?.type || '' },
  { name: 'aliases', text: (node?.aliases || []).join(' ') },
  { name: 'description', text: node?.description || '' },
  ...mentionFields(node?.mentions),
]

const edgeFields = (edge, nodeById) => {
  const sourceName = nodeById[edge?.source]?.name || ''
  const targetName = nodeById[edge?.target]?.name || ''
  return [
    { name: 'label', text: edge?.label || '' },
    { name: 'fact', text: edge?.fact || '' },
    { name: 'source', text: sourceName },
    { name: 'target', text: targetName },
    { name: 'relationship', text: `${sourceName} ${edge?.label || ''} ${targetName}` },
    ...mentionFields(edge?.mentions),
  ]
}

export const searchGraphData = (graphData, query) => {
  const q = normalizeSearchQuery(query)
  if (!q) return []

  const nodes = graphData?.nodes || []
  const edges = graphData?.edges || []
  const nodeById = Object.fromEntries(nodes.map((node) => [node.id, node]))

  const nodeResults = nodes.flatMap((node) => {
    const match = firstMatch(nodeFields(node), q)
    if (!match) return []
    return [{
      kind: 'node',
      id: node.id,
      title: node.name || 'Untitled entity',
      subtitle: [node.type, (node.aliases || []).join(', ')].filter(Boolean).join(' · '),
      snippet: makeSnippet(match.text, match.start, match.end),
      matchField: match.field,
      episode: firstMentionEpisode(node),
    }]
  })

  const edgeResults = edges.flatMap((edge) => {
    const match = firstMatch(edgeFields(edge, nodeById), q)
    if (!match) return []
    const sourceName = nodeById[edge.source]?.name || edge.source || ''
    const targetName = nodeById[edge.target]?.name || edge.target || ''
    return [{
      kind: 'edge',
      id: edge.id,
      title: [sourceName, edge.label || 'relationship', targetName].filter(Boolean).join(' — '),
      subtitle: 'Relationship',
      snippet: makeSnippet(match.text, match.start, match.end),
      matchField: match.field,
      episode: firstMentionEpisode(edge),
    }]
  })

  return [...nodeResults, ...edgeResults]
}

export const findTextMatches = (text, query) => {
  const q = normalizeSearchQuery(query)
  if (!q) return []

  const source = String(text || '')
  const haystack = normalizeText(source)
  const matches = []
  let from = 0
  while (from <= haystack.length) {
    const start = haystack.indexOf(q, from)
    if (start < 0) break
    const end = start + q.length
    matches.push({ start, end })
    from = Math.max(end, start + 1)
  }
  return matches
}

export const searchBodyTexts = ({ episodes = [], textsByEpisode = new Map(), query }) => {
  const q = normalizeSearchQuery(query)
  if (!q) return []

  return episodes.flatMap((episode, index) => {
    const episodeIndex = Number.isFinite(episode?.index) ? episode.index : index
    const text = textsByEpisode instanceof Map
      ? textsByEpisode.get(episodeIndex)
      : textsByEpisode?.[episodeIndex]
    return findTextMatches(text || '', q).map((match) => ({
      kind: 'body',
      id: `body:${episodeIndex}:${match.start}`,
      title: episode?.title || `#${episodeIndex + 1}`,
      subtitle: `#${episodeIndex + 1}`,
      snippet: makeSnippet(text, match.start, match.end),
      episode: episodeIndex,
      start: match.start,
      end: match.end,
    }))
  })
}

export const orderSearchResults = (results) =>
  [...results].sort((a, b) =>
    (RESULT_ORDER[a.kind] ?? 99) - (RESULT_ORDER[b.kind] ?? 99) ||
    (a.episode ?? 0) - (b.episode ?? 0) ||
    String(a.title || '').localeCompare(String(b.title || ''))
  )
