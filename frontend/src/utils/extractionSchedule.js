/**
 * Extraction runs sequentially on the server, so requesting the complete book
 * does not delay the first chapter. Keeping the full target warm also means a
 * later scope change or chapter jump does not have to restart cold extraction.
 */
export const fullBookExtractionTarget = (total) => {
  const normalizedTotal = Number.isFinite(total) ? Math.max(0, Math.trunc(total)) : 0
  return normalizedTotal > 0 ? normalizedTotal - 1 : -1
}
