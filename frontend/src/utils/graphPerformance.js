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
