export const EMPTY_ENTITY_TYPE = '—'

// Keep the first spelling for display while removing accidental surrounding or
// repeated whitespace. This mirrors the server-side label normalization.
export const normalizeEntityTypeLabel = (value) => {
  if (typeof value !== 'string') return EMPTY_ENTITY_TYPE
  return value.trim().replace(/\s+/gu, ' ') || EMPTY_ENTITY_TYPE
}

// JavaScript has no native String.casefold(). Lowercasing plus the Unicode
// folds not already covered by it handles persisted labels such as Straße /
// STRASSE and Greek final sigma consistently with Python's str.casefold().
export const entityTypeKey = (value) => normalizeEntityTypeLabel(value)
  .toLowerCase()
  .replace(/\u00df/gu, 'ss')
  .replace(/\u03c2/gu, '\u03c3')

export const groupEntityTypes = (nodes, colors) => {
  const groups = new Map()
  for (const node of nodes || []) {
    const name = normalizeEntityTypeLabel(node?.type)
    const key = entityTypeKey(name)
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        name,
        color: colors[groups.size % colors.length],
      })
    }
  }
  return [...groups.values()]
}

export const colorForEntityType = (value, groups, fallback = '#999') => {
  const key = entityTypeKey(value)
  return groups.find(group => group.key === key)?.color || fallback
}
