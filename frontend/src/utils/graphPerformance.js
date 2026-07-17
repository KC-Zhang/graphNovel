export const EDGE_LABEL_AUTO_HIDE_THRESHOLD = 180

export const shouldAutoHideEdgeLabels = ({
  edgeCount,
  userOverrode = false,
  threshold = EDGE_LABEL_AUTO_HIDE_THRESHOLD,
}) => {
  return !userOverrode && edgeCount > threshold
}

export const graphDensityMessage = ({ nodeCount, edgeCount }) => {
  return `${nodeCount} nodes / ${edgeCount} links`
}

// SVG getBBox() forces a layout read. Estimating the small edge-label backing
// rectangle once when data changes keeps graph ticks write-only and scales much
// better for dense graphs. CJK/wide glyphs get a full em; Latin glyphs use the
// average width of the 9px system font used by GraphPanel.
export const estimateEdgeLabelWidth = (label, { fontSize = 9, padding = 8 } = {}) => {
  const text = String(label || '')
  let ems = 0
  for (const char of text) {
    ems += /[\u1100-\u115f\u2e80-\ua4cf\uac00-\ud7a3\uf900-\ufaff\ufe10-\ufe6f\uff00-\uffef]/u.test(char)
      ? 1
      : 0.58
  }
  return Math.ceil(ems * fontSize + padding)
}
