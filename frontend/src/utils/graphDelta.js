const mentionKey = (mention) => `${mention?.episode ?? ''}\u0000${mention?.quote ?? ''}`

const mergeMentions = (previous = [], incoming = []) => {
  const result = [...previous]
  const seen = new Set(result.map(mentionKey))
  for (const mention of incoming) {
    const key = mentionKey(mention)
    if (seen.has(key)) continue
    seen.add(key)
    result.push(mention)
  }
  return result
}

const mergeItems = (previous = [], incoming = []) => {
  const result = [...previous]
  const index = new Map(result.map((item, position) => [item.id, position]))
  for (const item of incoming) {
    const position = index.get(item.id)
    if (position === undefined) {
      index.set(item.id, result.length)
      result.push(item)
      continue
    }
    const current = result[position]
    result[position] = {
      ...current,
      ...item,
      mentions: mergeMentions(current.mentions, item.mentions),
    }
  }
  return result
}

export const mergeGraphPayload = (current, payload) => {
  if (!payload || payload.mode !== 'delta') {
    return {
      ...(payload || {}),
      nodes: payload?.nodes || [],
      edges: payload?.edges || [],
    }
  }
  return {
    ...(current || {}),
    ...payload,
    nodes: mergeItems(current?.nodes, payload.nodes),
    edges: mergeItems(current?.edges, payload.edges),
  }
}

/**
 * Status can briefly advance before graph.json and the project revision finish
 * persisting. Compare against the revision confirmed by /graph/data instead of
 * assuming that a status observation means the corresponding graph was loaded.
 */
export const graphNeedsRefresh = ({
  extractedUpto = -1,
  graphRevision = -1,
  failedChanged = false,
} = {}) => failedChanged || extractedUpto > graphRevision
