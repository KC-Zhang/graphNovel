/**
 * 阅读覆盖区间工具（纯函数，无 DOM 依赖，便于单测）
 *
 * 以“归一化竖向区间”[0..1] 记录每章正文中真正进入过视口的部分。
 * 章节“已读”和链接“已看”均由该覆盖派生：
 * - 中途被链接跳入章节时，上方未浏览的文字不计入已读；
 * - 关系链接只有在其自身文字完整落入已浏览区间后才算已看。
 */

// 覆盖率达到该阈值即视为整章读完
export const FULL_READ_COVERAGE = 0.98
// 相邻区间合并的容差（也用于非归一误差吸收）
export const MERGE_EPS = 0.001
// 判断链接是否被覆盖时允许的边界容差
export const LINK_COVER_TOL = 0.005

export const clamp01 = (x) => {
  if (!Number.isFinite(x)) return 0
  if (x < 0) return 0
  if (x > 1) return 1
  return x
}

/**
 * 由滚动状态计算当前视口对应的归一化区间。
 * 内容无需滚动（scrollHeight <= clientHeight）时返回整章 [0, 1]。
 */
export const visibleInterval = (scrollTop, clientHeight, scrollHeight) => {
  if (!Number.isFinite(scrollHeight) || scrollHeight <= 0) return [0, 1]
  if (scrollHeight <= clientHeight + 1) return [0, 1]
  const start = clamp01(scrollTop / scrollHeight)
  const end = clamp01((scrollTop + clientHeight) / scrollHeight)
  if (end <= start) return [start, start]
  return [start, end]
}

/**
 * 归并区间：排序后合并重叠或相邻（间隙 <= eps）的区间。
 */
export const mergeIntervals = (ranges, eps = MERGE_EPS) => {
  const valid = (ranges || [])
    .filter(r => Array.isArray(r) && Number.isFinite(r[0]) && Number.isFinite(r[1]) && r[1] > r[0])
    .map(r => [clamp01(r[0]), clamp01(r[1])])
    .sort((a, b) => a[0] - b[0])
  const out = []
  for (const [s, e] of valid) {
    const last = out[out.length - 1]
    if (last && s <= last[1] + eps) {
      if (e > last[1]) last[1] = e
    } else {
      out.push([s, e])
    }
  }
  return out
}

/**
 * 将单个区间并入已有区间集合，返回归并后的新数组。
 */
export const addInterval = (ranges, interval, eps = MERGE_EPS) => {
  if (!Array.isArray(interval)) return mergeIntervals(ranges, eps)
  return mergeIntervals([...(ranges || []), interval], eps)
}

/**
 * 覆盖率：所有区间长度之和（0..1）。
 */
export const coverage = (ranges) => {
  return mergeIntervals(ranges).reduce((sum, [s, e]) => sum + (e - s), 0)
}

/**
 * 判断子区间 [s, e]（如某链接的竖向范围）是否被覆盖集合完整包含。
 */
export const isRangeCovered = (ranges, [s, e], tol = LINK_COVER_TOL) => {
  if (!Number.isFinite(s) || !Number.isFinite(e)) return false
  for (const [rs, re] of mergeIntervals(ranges)) {
    if (rs <= s + tol && re >= e - tol) return true
  }
  return false
}
