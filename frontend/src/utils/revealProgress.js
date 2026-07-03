export const clampRevealMax = (value, total) => {
  const count = Number.isFinite(Number(total)) ? Math.floor(Number(total)) : 0
  if (count <= 0) return 0
  const index = Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : 0
  return Math.min(count - 1, Math.max(0, index))
}

const asEpisodeList = (episodes) => {
  if (episodes instanceof Set) return [...episodes]
  if (Array.isArray(episodes)) return episodes
  return []
}

export const latestReadableEpisode = ({
  viewEpisode = 0,
  readEpisodes = [],
  episodeRanges = {},
  total = 0,
  extraEpisodes = [],
} = {}) => {
  const candidates = [viewEpisode, ...asEpisodeList(readEpisodes), ...asEpisodeList(extraEpisodes)]
  Object.entries(episodeRanges || {}).forEach(([episode, ranges]) => {
    if (Array.isArray(ranges) && ranges.length) candidates.push(Number(episode))
  })

  const latest = candidates.reduce((max, value) => {
    const n = Number(value)
    return Number.isFinite(n) ? Math.max(max, n) : max
  }, 0)

  return clampRevealMax(latest, total)
}
