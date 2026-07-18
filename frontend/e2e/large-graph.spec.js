import { expect, test } from '@playwright/test'

const projectId = 'proj_aaaaaaaaaaaa'
const EPISODE_COUNT = 12
const CURRENT_NODE_COUNT = 96
const CURRENT_EDGE_COUNT = 240
const ALL_NODE_COUNT = 5_000
const ALL_EDGE_COUNT = 20_000
const HEARTBEAT_INTERVAL_MS = 16
const SEMANTIC_SOURCE_ID = `entity-${ALL_NODE_COUNT - 2}`
const SEMANTIC_TARGET_ID = `entity-${ALL_NODE_COUNT - 1}`
const SEMANTIC_EDGE_ID = 'relationship-semantic'
const SEMANTIC_SOURCE_NAME = 'Narrator'
const SEMANTIC_RELATIONSHIP = 'frequented restaurant of'
const SEMANTIC_TARGET_NAME = 'Jimmy Rodriguez'
const standardDenseProjectId = 'proj_bbbbbbbbbbbb'
const STANDARD_DENSE_NODE_COUNT = 600
const STANDARD_DENSE_EDGE_COUNT = 1_200

const episodeFor = (index) => (
  index < CURRENT_NODE_COUNT
    ? 0
    : 1 + ((index - CURRENT_NODE_COUNT) % (EPISODE_COUNT - 1))
)

const makeAllChaptersGraph = () => {
  const nodes = Array.from({ length: ALL_NODE_COUNT }, (_, index) => {
    const episode = episodeFor(index)
    const id = `entity-${index}`
    const semanticName = id === SEMANTIC_SOURCE_ID
      ? SEMANTIC_SOURCE_NAME
      : id === SEMANTIC_TARGET_ID
        ? SEMANTIC_TARGET_NAME
        : null
    return {
      id,
      name: semanticName || `Entity ${index}`,
      size: semanticName ? 18 : undefined,
      type: index % 3 === 0 ? 'Person' : index % 3 === 1 ? 'Concept' : 'Place',
      first_episode: episode,
      last_episode: episode,
      mentions: [{ episode, quote: semanticName || `Entity ${index}` }],
    }
  })

  const edges = Array.from({ length: ALL_EDGE_COUNT }, (_, index) => {
    const semantic = index === ALL_EDGE_COUNT - 1
    const isCurrent = index < CURRENT_EDGE_COUNT
    const sourceIndex = semantic
      ? ALL_NODE_COUNT - 2
      : isCurrent
      ? index % CURRENT_NODE_COUNT
      : index % ALL_NODE_COUNT
    let targetIndex = semantic
      ? ALL_NODE_COUNT - 1
      : isCurrent
      ? (index * 17 + 1) % CURRENT_NODE_COUNT
      : (index * 37 + Math.floor(index / ALL_NODE_COUNT) + 1) % ALL_NODE_COUNT
    if (targetIndex === sourceIndex) targetIndex = (targetIndex + 1) % ALL_NODE_COUNT
    const episode = isCurrent
      ? 0
      : 1 + ((index - CURRENT_EDGE_COUNT) % (EPISODE_COUNT - 1))
    return {
      id: semantic ? SEMANTIC_EDGE_ID : `relationship-${index}`,
      source: `entity-${sourceIndex}`,
      target: `entity-${targetIndex}`,
      label: semantic ? SEMANTIC_RELATIONSHIP : `connects ${index}`,
      fact: `Stress-test relationship ${index}`,
      first_episode: episode,
      last_episode: episode,
      mentions: [{ episode, quote: `Relationship ${index}` }],
    }
  })

  return { nodes, edges }
}

const makeStandardDenseGraph = () => {
  const nodes = Array.from({ length: STANDARD_DENSE_NODE_COUNT }, (_, index) => ({
    id: `dense-entity-${index}`,
    name: `Dense Entity ${index}`,
    type: index % 2 === 0 ? 'Person' : 'Concept',
    first_episode: 0,
    last_episode: 0,
    mentions: [{ episode: 0, quote: `Dense Entity ${index}` }],
  }))
  const edges = Array.from({ length: STANDARD_DENSE_EDGE_COUNT }, (_, index) => {
    const sourceIndex = index % STANDARD_DENSE_NODE_COUNT
    // Half the relationships terminate at one of six book-wide hubs. This is
    // the topology that used to pull every ordinary entity into a few dense
    // stars; the other half keeps cross-community structure in the fixture.
    let targetIndex = index % 2 === 0
      ? Math.floor(index / 2) % 6
      : (index * 17 + Math.floor(index / STANDARD_DENSE_NODE_COUNT) + 1) %
        STANDARD_DENSE_NODE_COUNT
    if (sourceIndex === targetIndex) targetIndex = (targetIndex + 1) % STANDARD_DENSE_NODE_COUNT
    return {
      id: `dense-relationship-${index}`,
      source: `dense-entity-${sourceIndex}`,
      target: `dense-entity-${targetIndex}`,
      label: `dense relationship ${index}`,
      first_episode: 0,
      last_episode: 0,
      mentions: [{ episode: 0, quote: `Dense relationship ${index}` }],
    }
  })
  return { nodes, edges }
}

const resetHeartbeat = page => page.evaluate(() => {
  window.__bookMiroHeartbeat.samples = []
  window.__bookMiroHeartbeat.last = performance.now()
  window.__bookMiroHeartbeat.startedAt = performance.now()
})

const readHeartbeat = page => page.evaluate(({ expectedInterval }) => {
  const heartbeat = window.__bookMiroHeartbeat
  const samples = [...heartbeat.samples]
  const sorted = [...samples].sort((a, b) => a - b)
  const percentile = (ratio) => sorted.length
    ? sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * ratio))]
    : 0
  const maxGap = sorted.at(-1) || 0
  return {
    elapsed: performance.now() - heartbeat.startedAt,
    samples: samples.length,
    maxGap,
    maxBlockedFor: Math.max(0, maxGap - expectedInterval),
    p95Gap: percentile(0.95),
    gapsOver100ms: samples.filter(gap => gap > 100).length,
  }
}, { expectedInterval: HEARTBEAT_INTERVAL_MS })

const readLabelCount = async (graph, attribute) => Number(
  await graph.getAttribute(attribute) || 0
)

const readStandardDenseLayoutMetrics = page => page.evaluate(({ expectedInterval }) => {
  const frame = window.__bookMiroStandardDenseLabelFrame
  const items = frame?.items || []
  if (!items.length) return null

  const percentile = (values, ratio) => {
    const sorted = [...values].sort((left, right) => left - right)
    return sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * ratio))]
  }
  const width = Math.max(1, items[0].canvasWidth)
  const height = Math.max(1, items[0].canvasHeight)
  const nearest = items.map((item, index) => {
    let closest = Number.POSITIVE_INFINITY
    for (let otherIndex = 0; otherIndex < items.length; otherIndex += 1) {
      if (index === otherIndex) continue
      const other = items[otherIndex]
      closest = Math.min(closest, Math.hypot(item.x - other.x, item.y - other.y))
    }
    return closest
  })

  // 64 CSS pixels is deliberately independent of devicePixelRatio and wide
  // enough to distinguish separate neighbourhoods from a central hairball.
  const cellSize = 64
  const cellCounts = new Map()
  for (const item of items) {
    const key = `${Math.floor(item.x / cellSize)}:${Math.floor(item.y / cellSize)}`
    cellCounts.set(key, (cellCounts.get(key) || 0) + 1)
  }
  const totalCells = Math.ceil(width / cellSize) * Math.ceil(height / cellSize)
  const concentration = [...cellCounts.values()].reduce((sum, count) => (
    sum + (count / items.length) ** 2
  ), 0)
  const effectiveCells = concentration ? 1 / concentration : 0

  const overlapping = new Set()
  const overlapCountByLabel = new Map(items.map(item => [item.text, 0]))
  let overlapPairs = 0
  const boxes = items.map(item => ({
    ...item,
    left: item.x,
    right: item.x + item.width,
    top: item.y - item.ascent,
    bottom: item.y + item.descent,
  })).sort((left, right) => left.left - right.left)
  for (let leftIndex = 0; leftIndex < boxes.length; leftIndex += 1) {
    const left = boxes[leftIndex]
    for (let rightIndex = leftIndex + 1; rightIndex < boxes.length; rightIndex += 1) {
      const right = boxes[rightIndex]
      if (right.left >= left.right) break
      const overlapWidth = Math.min(left.right, right.right) - right.left
      const overlapHeight = Math.min(left.bottom, right.bottom) - Math.max(left.top, right.top)
      if (overlapWidth <= 0 || overlapHeight <= 0) continue
      const overlapArea = overlapWidth * overlapHeight
      const smallerArea = Math.min(
        left.width * (left.ascent + left.descent),
        right.width * (right.ascent + right.descent),
      )
      // Ignore one-pixel grazing caused by font-metric rounding. A collision
      // only counts when it obscures a meaningful part of either label.
      if (overlapArea < smallerArea * 0.08) continue
      overlapPairs += 1
      overlapping.add(left.text)
      overlapping.add(right.text)
      overlapCountByLabel.set(left.text, overlapCountByLabel.get(left.text) + 1)
      overlapCountByLabel.set(right.text, overlapCountByLabel.get(right.text) + 1)
    }
  }

  const xValues = items.map(item => item.x)
  const yValues = items.map(item => item.y)
  const heartbeatSamples = [...(window.__bookMiroHeartbeat?.samples || [])]
  const sortedHeartbeat = [...heartbeatSamples].sort((left, right) => left - right)
  const maxHeartbeatGap = sortedHeartbeat.at(-1) || 0
  const anchorsInside = items.filter(item => (
    item.x >= 0 && item.x <= width && item.y >= 0 && item.y <= height
  )).length
  const fullyVisibleLabels = boxes.filter(item => (
    item.left >= 0 && item.right <= width && item.top >= 0 && item.bottom <= height
  )).length
  return {
    labelCount: items.length,
    frameAgeMs: performance.now() - frame.lastClearAt,
    frameCount: frame.clearCount,
    anchorInsideFraction: anchorsInside / items.length,
    fullyVisibleLabelFraction: fullyVisibleLabels / items.length,
    robustSpanX: (percentile(xValues, 0.9) - percentile(xValues, 0.1)) / width,
    robustSpanY: (percentile(yValues, 0.9) - percentile(yValues, 0.1)) / height,
    occupiedCellCount: cellCounts.size,
    occupiedCellRatio: cellCounts.size / Math.min(items.length, totalCells),
    effectiveCellRatio: effectiveCells / Math.min(items.length, totalCells),
    maxCellCount: Math.max(...cellCounts.values()),
    maxCellShare: Math.max(...cellCounts.values()) / items.length,
    nearestP10: percentile(nearest, 0.1),
    nearestMedian: percentile(nearest, 0.5),
    near12Fraction: nearest.filter(distance => distance < 12).length / items.length,
    overlapLabelFraction: overlapping.size / items.length,
    overlapPairsPerLabel: overlapPairs / items.length,
    overlapPartnersP95: percentile([...overlapCountByLabel.values()], 0.95),
    maxOverlapPartners: Math.max(...overlapCountByLabel.values()),
    layoutHeartbeat: {
      samples: heartbeatSamples.length,
      maxGap: maxHeartbeatGap,
      maxBlockedFor: Math.max(0, maxHeartbeatGap - expectedInterval),
      p95Gap: percentile(sortedHeartbeat, 0.95),
      gapsOver100ms: heartbeatSamples.filter(gap => gap > 100).length,
    },
  }
}, { expectedInterval: HEARTBEAT_INTERVAL_MS })

test.describe('all-chapters large graph performance', () => {
  test('switches 5k nodes and 20k edges to WebGL while the reader stays responsive', async ({ page }) => {
    const graph = makeAllChaptersGraph()
    let releaseGraphResponse
    let markGraphRequested
    let markStatusRequested
    let graphRequestCount = 0
    const graphResponseGate = new Promise(resolve => { releaseGraphResponse = resolve })
    const graphRequested = new Promise(resolve => { markGraphRequested = resolve })
    const statusRequested = new Promise(resolve => { markStatusRequested = resolve })
    const episodes = Array.from({ length: EPISODE_COUNT }, (_, index) => ({
      index,
      title: `Chapter ${index + 1}: ${index === 0 ? 'A responsive graph' : `Graph topic ${index + 1}`}`,
      start_char: index * 160,
      end_char: (index + 1) * 160,
      char_count: 160,
      unit_type: 'chapter',
    }))
    const project = {
      project_id: projectId,
      name: 'All-chapters performance fixture',
      language: 'English',
      source_format: 'txt',
      reading_mode: 'chapter',
      document_kind: 'novel',
      extracted_upto: EPISODE_COUNT - 1,
      episodes,
      files: [{ filename: 'all-chapters-graph.txt' }],
    }

    await page.addInitScript(({ heartbeatInterval }) => {
      const now = performance.now()
      window.__bookMiroHeartbeat = { last: now, startedAt: now, samples: [] }
      window.__bookMiroCanvasLabels = { nodes: [], edges: [], hovers: [] }
      window.setInterval(() => {
        const heartbeat = window.__bookMiroHeartbeat
        const current = performance.now()
        heartbeat.samples.push(current - heartbeat.last)
        heartbeat.last = current
      }, heartbeatInterval)

      const contextPrototype = window.CanvasRenderingContext2D?.prototype
      if (contextPrototype) {
        const originalClearRect = contextPrototype.clearRect
        const originalFillText = contextPrototype.fillText
        contextPrototype.clearRect = function (...args) {
          const className = String(this.canvas?.className || '')
          if (
            className.includes('sigma-edgeLabels') ||
            className.includes('large-graph-edge-label-overlay')
          ) window.__bookMiroCanvasLabels.edges = []
          else if (
            className.includes('sigma-labels') ||
            className.includes('large-graph-node-label-overlay')
          ) window.__bookMiroCanvasLabels.nodes = []
          else if (className.includes('sigma-hovers')) window.__bookMiroCanvasLabels.hovers = []
          return originalClearRect.apply(this, args)
        }
        contextPrototype.fillText = function (value, ...args) {
          const className = String(this.canvas?.className || '')
          if (
            className.includes('sigma-edgeLabels') ||
            className.includes('large-graph-edge-label-overlay')
          ) {
            window.__bookMiroCanvasLabels.edges.push(String(value))
          } else if (
            className.includes('sigma-labels') ||
            className.includes('large-graph-node-label-overlay')
          ) {
            window.__bookMiroCanvasLabels.nodes.push(String(value))
          } else if (className.includes('sigma-hovers')) {
            window.__bookMiroCanvasLabels.hovers.push(String(value))
          }
          return originalFillText.call(this, value, ...args)
        }
      }
    }, { heartbeatInterval: HEARTBEAT_INTERVAL_MS })

    await page.route(`**/api/graph/project/${projectId}`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: project }),
    }))
    await page.route(`**/api/graph/episode/${projectId}/*`, route => {
      const index = Number(new URL(route.request().url()).pathname.split('/').pop()) || 0
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            index,
            title: episodes[index]?.title || `Chapter ${index + 1}`,
            text: `Entity ${index} keeps chapter ${index + 1} readable while the all-chapters graph is loading.`,
          },
        }),
      })
    })
    await page.route(`**/api/graph/data/${projectId}*`, async route => {
      graphRequestCount += 1
      markGraphRequested()
      await graphResponseGate
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            ...graph,
            mode: 'full',
            revision_episode: EPISODE_COUNT - 1,
            node_count: graph.nodes.length,
            edge_count: graph.edges.length,
          },
        }),
      })
    })
    await page.route(`**/api/graph/status/${projectId}`, route => {
      markStatusRequested()
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            running: false,
            extracted_upto: EPISODE_COUNT - 1,
            failed_episodes: [],
            error: null,
          },
        }),
      })
    })
    await page.route('**/api/graph/extract', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          running: false,
          extracted_upto: EPISODE_COUNT - 1,
          failed_episodes: [],
          error: null,
        },
      }),
    }))
    await page.route(`**/api/graph/search/${projectId}*`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          results: [{
            kind: 'body',
            id: 'body:11:0',
            title: episodes.at(-1).title,
            subtitle: '#12',
            snippet: 'Entity 4999 appears in the final chapter.',
            episode: EPISODE_COUNT - 1,
            start: 0,
            end: 11,
          }],
        },
      }),
    }))

    await page.goto(`/read/${projectId}`)

    await graphRequested
    try {
      // Metadata, chapter content, and controls must not wait for the large
      // persisted graph response.
      await expect(page.locator('.episode-title')).toContainText('A responsive graph', { timeout: 2_000 })
      await expect(page.locator('.graph-state')).toBeVisible()
      await statusRequested
      await page.waitForTimeout(50)
      expect(graphRequestCount).toBe(1)
    } finally {
      releaseGraphResponse()
    }

    // The default scope is deliberately a small SVG subgraph even though the
    // loaded book already contains the complete all-chapters graph.
    const currentScope = page.getByRole('button', { name: /Current chapter|仅当前章节/ })
    await expect(currentScope).toHaveClass(/active/)
    await expect(page.locator('.graph-svg')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.graph-node')).toHaveCount(CURRENT_NODE_COUNT)
    await expect(page.locator('.graph-link')).toHaveCount(CURRENT_EDGE_COUNT)
    await expect(page.locator('.large-graph-view')).toHaveCount(0)
    expect(graphRequestCount).toBe(1)

    // Measure the user-visible Current -> All transition. A 16 ms heartbeat
    // records main-thread stalls while Vue reconciles scope, WebGL imports,
    // Graphology syncs 25k records, and Sigma paints its first frame.
    await resetHeartbeat(page)
    const allScope = page.getByRole('button', { name: /All chapters|全部章节/ })
    const switchStartedAt = Date.now()
    await allScope.click()
    await expect(allScope).toHaveClass(/active/)

    // Search is intentionally entered before WebGL reports ready. If graph
    // setup monopolizes the main thread, this input assertion exposes it.
    const searchInput = page.locator('.search-input')
    const searchStartedAt = Date.now()
    await searchInput.fill('Entity 4999')
    await expect(searchInput).toHaveValue('Entity 4999')
    const searchFillMs = Date.now() - searchStartedAt
    expect(searchFillMs).toBeLessThan(1_000)
    await expect(page.locator('.search-result').filter({ hasText: 'Entity 4999' }).first()).toBeVisible({ timeout: 3_000 })
    const searchResultMs = Date.now() - switchStartedAt

    const largeGraph = page.locator('.large-graph-view')
    await expect(largeGraph).toBeVisible({ timeout: 15_000 })
    await expect(largeGraph).toHaveAttribute('data-node-count', String(ALL_NODE_COUNT))
    await expect(largeGraph).toHaveAttribute('data-edge-count', String(ALL_EDGE_COUNT))
    await expect(largeGraph).toHaveAttribute('data-renderer-status', 'ready', { timeout: 15_000 })
    await expect(largeGraph.locator('canvas').first()).toBeVisible()
    await expect(page.locator('.graph-svg')).toHaveCount(0)
    expect(graphRequestCount).toBe(1)
    const rendererReadyMs = Date.now() - switchStartedAt

    await expect.poll(() => readLabelCount(largeGraph, 'data-node-label-count')).toBe(ALL_NODE_COUNT)
    await expect(largeGraph).toHaveAttribute('data-node-label-status', 'ready')
    const initialNodeLabelCount = await readLabelCount(largeGraph, 'data-node-label-count')
    const initialEdgeLabelCount = await readLabelCount(largeGraph, 'data-edge-label-count')
    const labelsReadyMs = Date.now() - switchStartedAt
    expect(initialNodeLabelCount).toBe(ALL_NODE_COUNT)
    expect(initialEdgeLabelCount).toBe(0)
    expect(labelsReadyMs).toBeLessThan(3_000)
    const paintedNodeLabels = await page.evaluate(() => window.__bookMiroCanvasLabels.nodes)
    expect(paintedNodeLabels).toHaveLength(ALL_NODE_COUNT)
    expect(new Set(paintedNodeLabels).size).toBe(ALL_NODE_COUNT)

    // Give the heartbeat one turn after the ready mutation so the final graph
    // synchronization stall is included in the sample.
    await page.waitForTimeout(100)
    const switchHeartbeat = await readHeartbeat(page)
    console.log('all-chapters switch metrics', {
      searchFillMs,
      searchResultMs,
      rendererReadyMs,
      labelsReadyMs,
      switchHeartbeat,
    })
    expect(searchResultMs).toBeLessThan(2_000)
    expect(rendererReadyMs).toBeLessThan(3_000)
    expect(switchHeartbeat.samples).toBeGreaterThan(3)
    expect(switchHeartbeat.maxGap).toBeLessThan(500)

    // Dense graphs keep relationship labels opt-in. The massive renderer uses
    // an independent bounded overlay, so toggling it never starts Sigma's
    // per-frame full-edge scan.
    const edgeLabels = page.locator('.tool-btn').filter({ hasText: /Show Edge Labels|显示关系标签/ })
    await expect(edgeLabels).not.toHaveClass(/active/)

    await resetHeartbeat(page)
    const labelsOnStartedAt = Date.now()
    await edgeLabels.click()
    await expect(edgeLabels).toHaveClass(/active/)
    await expect.poll(() => readLabelCount(largeGraph, 'data-edge-label-count')).toBeGreaterThanOrEqual(1)
    const labelsOnMs = Date.now() - labelsOnStartedAt
    const restoredEdgeLabelCount = await readLabelCount(largeGraph, 'data-edge-label-count')
    expect(restoredEdgeLabelCount).toBeLessThanOrEqual(36)
    await page.waitForTimeout(100)
    const labelsOnHeartbeat = await readHeartbeat(page)
    expect(labelsOnMs).toBeLessThan(1_000)
    expect(labelsOnHeartbeat.maxGap).toBeLessThan(500)

    await resetHeartbeat(page)
    const labelsOffStartedAt = Date.now()
    await edgeLabels.click()
    await expect(edgeLabels).not.toHaveClass(/active/)
    await expect.poll(() => readLabelCount(largeGraph, 'data-edge-label-count')).toBe(0)
    const labelsOffMs = Date.now() - labelsOffStartedAt
    await page.waitForTimeout(100)
    const labelsOffHeartbeat = await readHeartbeat(page)
    expect(labelsOffMs).toBeLessThan(1_000)
    expect(labelsOffHeartbeat.maxGap).toBeLessThan(500)

    // A selected relationship remains labelled even while the global edge
    // label overlay is off, and its detail reads in canonical source -> target
    // order rather than as three unrelated metadata fields.
    await searchInput.fill(SEMANTIC_RELATIONSHIP)
    const semanticResult = page.locator('.search-result.edge').filter({ hasText: SEMANTIC_RELATIONSHIP }).first()
    await expect(semanticResult).toBeVisible({ timeout: 3_000 })
    await semanticResult.click()
    const relationshipStatement = page.locator('.detail-panel .relationship-statement:not(.compact)')
    await expect(relationshipStatement).toBeVisible()
    await expect(relationshipStatement.locator('.endpoint.source strong')).toHaveText(SEMANTIC_SOURCE_NAME)
    await expect(relationshipStatement.locator('.predicate strong')).toHaveText(SEMANTIC_RELATIONSHIP)
    await expect(relationshipStatement.locator('.endpoint.target strong')).toHaveText(SEMANTIC_TARGET_NAME)
    await expect(relationshipStatement.locator('.relationship-arrow')).toBeVisible()
    await expect(relationshipStatement).toHaveAttribute(
      'aria-label',
      `Source: ${SEMANTIC_SOURCE_NAME}. Relationship: ${SEMANTIC_RELATIONSHIP}. Target: ${SEMANTIC_TARGET_NAME}.`,
    )
    const relationshipCenters = await Promise.all([
      relationshipStatement.locator('.endpoint.source').boundingBox(),
      relationshipStatement.locator('.relationship-connector').boundingBox(),
      relationshipStatement.locator('.endpoint.target').boundingBox(),
    ])
    const [sourceCenter, connectorCenter, targetCenter] = relationshipCenters.map(box => (
      box.x + box.width / 2
    ))
    expect(sourceCenter).toBeLessThan(connectorCenter)
    expect(connectorCenter).toBeLessThan(targetCenter)
    await expect.poll(() => readLabelCount(largeGraph, 'data-edge-label-count')).toBeGreaterThanOrEqual(1)
    await expect.poll(() => page.evaluate(label => (
      window.__bookMiroCanvasLabels.edges.includes(label)
    ), SEMANTIC_RELATIONSHIP)).toBe(true)

    await page.locator('.detail-panel .detail-close').click()
    await expect(page.locator('.detail-panel')).toHaveCount(0)
    await expect.poll(() => readLabelCount(largeGraph, 'data-edge-label-count')).toBe(0)

    // Selecting a node must not make Sigma paint a duplicate hover label over
    // the complete progressive label layer.
    await searchInput.fill(SEMANTIC_SOURCE_NAME)
    const semanticNodeResult = page.locator('.search-result.node').filter({ hasText: SEMANTIC_SOURCE_NAME }).first()
    await expect(semanticNodeResult).toBeVisible({ timeout: 3_000 })
    await semanticNodeResult.click()
    await expect(page.locator('.detail-panel .node-name')).toHaveText(SEMANTIC_SOURCE_NAME)
    await page.waitForTimeout(50)
    await expect(largeGraph).toHaveAttribute('data-node-label-status', 'ready')
    expect(await page.evaluate(() => window.__bookMiroCanvasLabels.hovers)).toEqual([])
    await page.locator('.detail-panel .detail-close').click()
    await expect(page.locator('.detail-panel')).toHaveCount(0)

    console.log('all-chapters label metrics', {
      initialNodeLabelCount,
      initialEdgeLabelCount,
      labelsOnMs,
      labelsOnHeartbeat,
      restoredEdgeLabelCount,
      labelsOffMs,
      labelsOffHeartbeat,
    })

    // The graph remains interactive after its first canvas. Real toolbar,
    // resize, zoom, and pan actions must not reintroduce long main-thread work.
    await searchInput.press('Escape')
    await expect(page.locator('.search-results')).toHaveCount(0)
    await resetHeartbeat(page)
    const focusUnread = page.locator('.tool-btn').filter({ hasText: /Focus unread|只看未读/ })
    const toolbarStartedAt = Date.now()
    await focusUnread.click()
    await expect(focusUnread).toHaveClass(/active/)
    await page.locator('.graph-pane .icon-maximize').click()
    await expect(page.locator('.reader-body')).toHaveClass(/graph-maximized/)
    await page.locator('.graph-pane .icon-maximize').click()
    await expect(page.locator('.reader-body')).not.toHaveClass(/graph-maximized/)
    const toolbarMs = Date.now() - toolbarStartedAt
    expect(toolbarMs).toBeLessThan(2_500)

    const canvasBounds = await largeGraph.boundingBox()
    expect(canvasBounds).toBeTruthy()
    const cameraStartedAt = Date.now()
    await page.mouse.move(
      canvasBounds.x + canvasBounds.width / 2,
      canvasBounds.y + canvasBounds.height / 2,
    )
    const wheelStartedAt = Date.now()
    for (let index = 0; index < 12; index += 1) {
      await page.mouse.wheel(0, -40)
    }
    const wheelBurstMs = Date.now() - wheelStartedAt
    expect(wheelBurstMs).toBeLessThan(1_000)
    await page.mouse.down()
    await page.mouse.move(
      canvasBounds.x + canvasBounds.width / 2 + 80,
      canvasBounds.y + canvasBounds.height / 2 + 50,
      { steps: 3 },
    )
    await page.mouse.up()
    const cameraMs = Date.now() - cameraStartedAt
    expect(cameraMs).toBeLessThan(1_500)
    await expect(largeGraph).toHaveAttribute('data-renderer-status', 'ready')

    await page.waitForTimeout(250)
    await expect(largeGraph).toHaveAttribute('data-node-label-status', 'ready')
    await expect.poll(() => readLabelCount(largeGraph, 'data-node-label-count')).toBeGreaterThan(0)
    const interactionHeartbeat = await readHeartbeat(page)
    console.log('all-chapters interaction metrics', {
      toolbarMs,
      cameraMs,
      wheelBurstMs,
      interactionHeartbeat,
    })
    expect(interactionHeartbeat.samples).toBeGreaterThan(5)
    expect(interactionHeartbeat.maxGap).toBeLessThan(500)
  })

  test('standard WebGL path spreads a hub-heavy graph without a clustered pileup', async ({ page }) => {
    const graph = makeStandardDenseGraph()
    const episode = {
      index: 0,
      title: 'Dense standard WebGL graph',
      start_char: 0,
      end_char: 160,
      char_count: 160,
      unit_type: 'chapter',
    }
    const project = {
      project_id: standardDenseProjectId,
      name: 'Standard dense label fixture',
      language: 'English',
      source_format: 'txt',
      reading_mode: 'chapter',
      document_kind: 'novel',
      extracted_upto: 0,
      episodes: [episode],
      files: [{ filename: 'standard-dense-graph.txt' }],
    }

    await page.addInitScript(() => {
      window.__bookMiroStandardDenseLabels = []
      window.__bookMiroStandardDenseLabelFrame = {
        items: [],
        clearCount: 0,
        lastClearAt: performance.now(),
      }
      const now = performance.now()
      window.__bookMiroHeartbeat = { last: now, startedAt: now, samples: [] }
      window.setInterval(() => {
        const heartbeat = window.__bookMiroHeartbeat
        const current = performance.now()
        heartbeat.samples.push(current - heartbeat.last)
        heartbeat.last = current
      }, 16)
      const contextPrototype = window.CanvasRenderingContext2D?.prototype
      if (!contextPrototype) return
      const originalClearRect = contextPrototype.clearRect
      const originalFillText = contextPrototype.fillText
      contextPrototype.clearRect = function (...args) {
        if (String(this.canvas?.className || '').includes('sigma-labels')) {
          window.__bookMiroStandardDenseLabels = []
          window.__bookMiroStandardDenseLabelFrame.items = []
          window.__bookMiroStandardDenseLabelFrame.clearCount += 1
          window.__bookMiroStandardDenseLabelFrame.lastClearAt = performance.now()
        }
        return originalClearRect.apply(this, args)
      }
      contextPrototype.fillText = function (value, ...args) {
        if (String(this.canvas?.className || '').includes('sigma-labels')) {
          const text = String(value)
          const metrics = this.measureText(text)
          const fontSize = Number.parseFloat(/([\d.]+)px/.exec(this.font)?.[1] || '14')
          window.__bookMiroStandardDenseLabels.push(text)
          window.__bookMiroStandardDenseLabelFrame.items.push({
            text,
            x: Number(args[0]),
            y: Number(args[1]),
            width: metrics.width,
            ascent: metrics.actualBoundingBoxAscent || fontSize * 0.8,
            descent: metrics.actualBoundingBoxDescent || fontSize * 0.2,
            canvasWidth: this.canvas.clientWidth,
            canvasHeight: this.canvas.clientHeight,
          })
        }
        return originalFillText.call(this, value, ...args)
      }
    })

    await page.route(`**/api/graph/project/${standardDenseProjectId}`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: project }),
    }))
    await page.route(`**/api/graph/episode/${standardDenseProjectId}/*`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          ...episode,
          text: 'Every entity in this dense standard WebGL graph keeps its label.',
        },
      }),
    }))
    await page.route(`**/api/graph/data/${standardDenseProjectId}*`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          ...graph,
          mode: 'full',
          revision_episode: 0,
          node_count: graph.nodes.length,
          edge_count: graph.edges.length,
        },
      }),
    }))
    await page.route(`**/api/graph/status/${standardDenseProjectId}`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          running: false,
          extracted_upto: 0,
          failed_episodes: [],
          error: null,
        },
      }),
    }))
    await page.route('**/api/graph/extract', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          running: false,
          extracted_upto: 0,
          failed_episodes: [],
          error: null,
        },
      }),
    }))
    await page.route(`**/api/graph/search/${standardDenseProjectId}*`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { results: [] } }),
    }))

    await page.goto(`/read/${standardDenseProjectId}`)

    const largeGraph = page.locator('.large-graph-view')
    await expect(largeGraph).toBeVisible({ timeout: 15_000 })
    await expect(largeGraph).toHaveAttribute('data-node-count', String(STANDARD_DENSE_NODE_COUNT))
    await expect(largeGraph).toHaveAttribute('data-edge-count', String(STANDARD_DENSE_EDGE_COUNT))
    await expect(largeGraph).toHaveAttribute('data-layout-mode', 'worker')
    await expect(largeGraph).toHaveAttribute('data-renderer-status', 'ready')
    await expect(largeGraph).toHaveAttribute('data-node-label-status', 'ready')
    await expect.poll(() => readLabelCount(largeGraph, 'data-node-label-count')).toBe(
      STANDARD_DENSE_NODE_COUNT,
    )
    await expect.poll(() => page.evaluate(() => (
      window.__bookMiroStandardDenseLabels.length
    ))).toBe(STANDARD_DENSE_NODE_COUNT)

    const paintedLabels = await page.evaluate(() => window.__bookMiroStandardDenseLabels)
    const expectedLabels = graph.nodes.map(node => node.name).sort()
    expect(new Set(paintedLabels).size).toBe(STANDARD_DENSE_NODE_COUNT)
    expect([...paintedLabels].sort()).toEqual(expectedLabels)

    // The worker runs for a bounded 3.5-second window. Assess its final frame,
    // not the deliberately immediate deterministic first paint.
    await resetHeartbeat(page)
    await page.waitForTimeout(4_000)
    await expect.poll(() => page.evaluate(() => (
      performance.now() - window.__bookMiroStandardDenseLabelFrame.lastClearAt
    )), { timeout: 6_000 }).toBeGreaterThan(500)
    await expect.poll(() => page.evaluate(() => (
      window.__bookMiroStandardDenseLabelFrame.items.length
    ))).toBe(STANDARD_DENSE_NODE_COUNT)
    const layoutMetrics = await readStandardDenseLayoutMetrics(page)
    console.log('standard dense layout metrics', layoutMetrics)

    expect(layoutMetrics).not.toBeNull()
    expect(layoutMetrics.labelCount).toBe(STANDARD_DENSE_NODE_COUNT)
    expect(layoutMetrics.frameAgeMs).toBeGreaterThan(400)
    expect(layoutMetrics.frameCount).toBeGreaterThan(10)

    // Camera/framing: use the central 80% of nodes so one distant outlier
    // cannot make a collapsed graph appear to fill the canvas.
    expect(layoutMetrics.anchorInsideFraction).toBeGreaterThan(0.98)
    expect(layoutMetrics.robustSpanX).toBeGreaterThan(0.55)
    expect(layoutMetrics.robustSpanY).toBeGreaterThan(0.50)

    // Spatial occupancy and nearest-neighbour distance catch a pileup even
    // when the camera zooms to fit the graph's outermost points.
    expect(layoutMetrics.occupiedCellRatio).toBeGreaterThan(0.50)
    expect(layoutMetrics.effectiveCellRatio).toBeGreaterThan(0.35)
    expect(layoutMetrics.maxCellCount).toBeLessThanOrEqual(24)
    expect(layoutMetrics.maxCellShare).toBeLessThan(0.04)
    expect(layoutMetrics.nearestP10).toBeGreaterThan(8)
    expect(layoutMetrics.nearestMedian).toBeGreaterThan(12)
    expect(layoutMetrics.near12Fraction).toBeLessThan(0.25)

    // Label collision metrics remain diagnostic only. With all names painted,
    // ordinary long labels can overlap without their node anchors collapsing.
    expect(layoutMetrics.layoutHeartbeat.samples).toBeGreaterThan(50)
    expect(layoutMetrics.layoutHeartbeat.maxGap).toBeLessThan(500)
  })
})
