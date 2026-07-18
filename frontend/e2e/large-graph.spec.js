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

const readStandardDenseRenderState = page => page.evaluate(() => {
  const frame = window.__bookMiroStandardDenseLabelFrame
  const items = frame?.items || []
  if (!items.length) return null
  const boxes = items.map(item => ({
    ...item,
    left: item.x,
    right: item.x + item.width,
    top: item.y - item.ascent,
    bottom: item.y + item.descent,
  })).sort((left, right) => left.left - right.left)
  let overlapPairs = 0
  for (let leftIndex = 0; leftIndex < boxes.length; leftIndex += 1) {
    const left = boxes[leftIndex]
    for (let rightIndex = leftIndex + 1; rightIndex < boxes.length; rightIndex += 1) {
      const right = boxes[rightIndex]
      if (right.left >= left.right) break
      const overlapWidth = Math.min(left.right, right.right) - right.left
      const overlapHeight = Math.min(left.bottom, right.bottom) - Math.max(left.top, right.top)
      if (overlapWidth > 1 && overlapHeight > 1) overlapPairs += 1
    }
  }
  const graph = document.querySelector('.large-graph-view')
  const header = graph?.closest('.graph-panel')?.querySelector('.panel-header')
  const graphRect = graph?.getBoundingClientRect()
  const headerRect = header?.getBoundingClientRect()
  const topInset = graphRect && headerRect ? headerRect.bottom - graphRect.top : 0
  return {
    labelCount: items.length,
    uniqueLabelCount: new Set(items.map(item => item.text)).size,
    overlapPairs,
    allLabelsInside: boxes.every(item => (
      item.left >= 0 && item.right <= item.canvasWidth &&
      item.top >= topInset && item.bottom <= item.canvasHeight
    )),
    frameAgeMs: performance.now() - frame.lastClearAt,
    frameCount: frame.clearCount,
    lastClearAt: frame.lastClearAt,
    anchors: items
      .map(item => [item.text, { x: item.x, y: item.y }])
      .sort(([left], [right]) => left.localeCompare(right)),
    labelFonts: items
      .map(item => [item.text, { size: item.fontSize, font: item.font }])
      .sort(([left], [right]) => left.localeCompare(right)),
    edgeDraws: { ...(window.__bookMiroStandardDenseEdgeDraws || {}) },
  }
})

const maximumAnchorDelta = (before, after) => {
  const afterByLabel = new Map(after || [])
  let maximum = 0
  for (const [label, point] of before || []) {
    const next = afterByLabel.get(label)
    if (!next) return Number.POSITIVE_INFINITY
    maximum = Math.max(maximum, Math.hypot(next.x - point.x, next.y - point.y))
  }
  return maximum
}

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
    await expect(largeGraph.locator('canvas.sigma-nodes')).toBeVisible()
    await expect(page.locator('.graph-svg')).toHaveCount(0)
    expect(graphRequestCount).toBe(1)
    const rendererReadyMs = Date.now() - switchStartedAt

    await expect.poll(() => readLabelCount(largeGraph, 'data-node-label-count')).toBeGreaterThan(10)
    await expect(largeGraph).toHaveAttribute('data-node-label-status', 'ready')
    const initialNodeLabelCount = await readLabelCount(largeGraph, 'data-node-label-count')
    const initialEdgeLabelCount = await readLabelCount(largeGraph, 'data-edge-label-count')
    const labelsReadyMs = Date.now() - switchStartedAt
    expect(initialNodeLabelCount).toBeLessThan(500)
    expect(initialEdgeLabelCount).toBe(0)
    expect(labelsReadyMs).toBeLessThan(3_000)
    const paintedNodeLabels = await page.evaluate(() => window.__bookMiroCanvasLabels.nodes)
    expect(paintedNodeLabels).toHaveLength(initialNodeLabelCount)
    expect(new Set(paintedNodeLabels).size).toBe(initialNodeLabelCount)

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
    // WebGL program allocation is one unavoidable synchronous constructor
    // task at this fixture size. Keep the full timer gap below 550ms and the
    // actual blocked portion (minus the 16ms heartbeat interval) below 535ms.
    expect(switchHeartbeat.maxGap).toBeLessThan(550)
    expect(switchHeartbeat.maxBlockedFor).toBeLessThan(535)

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
    // the semantic label layer.
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

  test('standard WebGL path keeps links visible and freezes its settled topology', async ({ page }) => {
    const graph = makeStandardDenseGraph()
    const degreeById = new Map(graph.nodes.map(node => [node.id, 0]))
    for (const edge of graph.edges) {
      degreeById.set(edge.source, (degreeById.get(edge.source) || 0) + 1)
      degreeById.set(edge.target, (degreeById.get(edge.target) || 0) + 1)
    }
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
      window.__bookMiroStandardDenseEdgeDraws = {
        normalCalls: 0,
        vertexWork: 0,
        maxVertexWork: 0,
        lastVertexWork: 0,
        firstAt: 0,
        lastAt: 0,
      }
      const now = performance.now()
      window.__bookMiroHeartbeat = { last: now, startedAt: now, samples: [] }
      window.setInterval(() => {
        const heartbeat = window.__bookMiroHeartbeat
        const current = performance.now()
        heartbeat.samples.push(current - heartbeat.last)
        heartbeat.last = current
      }, 16)

      // Count only draw calls targeting Sigma's visible edge framebuffer.
      // Picking renders use a non-null framebuffer and therefore cannot make
      // this assertion pass while the relationship layer is actually absent.
      const recordEdgeDraw = (context, count, instances = 1) => {
        if (!String(context.canvas?.className || '').includes('sigma-edges')) return
        try {
          if (context.getParameter(context.FRAMEBUFFER_BINDING) !== null) return
        } catch {
          return
        }
        const work = Math.max(0, Number(count) || 0) * Math.max(1, Number(instances) || 1)
        if (!work) return
        const state = window.__bookMiroStandardDenseEdgeDraws
        const timestamp = performance.now()
        state.normalCalls += 1
        state.vertexWork += work
        state.maxVertexWork = Math.max(state.maxVertexWork, work)
        state.lastVertexWork = work
        if (!state.firstAt) state.firstAt = timestamp
        state.lastAt = timestamp
      }
      const patchDrawMethod = (prototype, method, instanceIndex = null) => {
        if (!prototype || !Object.prototype.hasOwnProperty.call(prototype, method)) return
        const descriptor = Object.getOwnPropertyDescriptor(prototype, method)
        const original = descriptor?.value
        if (typeof original !== 'function') return
        Object.defineProperty(prototype, method, {
          ...descriptor,
          value: function (...args) {
            recordEdgeDraw(this, args[2], instanceIndex === null ? 1 : args[instanceIndex])
            return original.apply(this, args)
          },
        })
      }
      const webglPrototype = window.WebGLRenderingContext?.prototype
      const webgl2Prototype = window.WebGL2RenderingContext?.prototype
      patchDrawMethod(webglPrototype, 'drawArrays')
      patchDrawMethod(webgl2Prototype, 'drawArrays')
      patchDrawMethod(webgl2Prototype, 'drawArraysInstanced', 3)

      const contextPrototype = window.CanvasRenderingContext2D?.prototype
      if (!contextPrototype) return
      const originalClearRect = contextPrototype.clearRect
      const originalFillText = contextPrototype.fillText
      contextPrototype.clearRect = function (...args) {
        if (
          String(this.canvas?.className || '').includes('sigma-labels') ||
          String(this.canvas?.className || '').includes('large-graph-node-label-overlay')
        ) {
          window.__bookMiroStandardDenseLabels = []
          window.__bookMiroStandardDenseLabelFrame.items = []
          window.__bookMiroStandardDenseLabelFrame.clearCount += 1
          window.__bookMiroStandardDenseLabelFrame.lastClearAt = performance.now()
        }
        return originalClearRect.apply(this, args)
      }
      contextPrototype.fillText = function (value, ...args) {
        if (
          String(this.canvas?.className || '').includes('sigma-labels') ||
          String(this.canvas?.className || '').includes('large-graph-node-label-overlay')
        ) {
          const text = String(value)
          const metrics = this.measureText(text)
          const fontSize = Number.parseFloat(/([\d.]+)px/.exec(this.font)?.[1] || '14')
          window.__bookMiroStandardDenseLabels.push(text)
          window.__bookMiroStandardDenseLabelFrame.items.push({
            text,
            x: Number(args[0]),
            y: Number(args[1]),
            font: this.font,
            fontSize,
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
    await expect.poll(() => readLabelCount(largeGraph, 'data-node-label-count')).toBeGreaterThan(5)
    await expect.poll(() => page.evaluate(() => (
      window.__bookMiroStandardDenseLabels.length
    ))).toBeGreaterThan(5)

    const paintedLabels = await page.evaluate(() => window.__bookMiroStandardDenseLabels)
    expect(paintedLabels.length).toBeLessThan(STANDARD_DENSE_NODE_COUNT)
    expect(new Set(paintedLabels).size).toBe(paintedLabels.length)

    // The relationship layer must issue visible-framebuffer draws while the
    // worker is actively moving nodes. Picking-buffer work is excluded by the
    // WebGL hook above.
    await resetHeartbeat(page)
    await expect(largeGraph).toHaveAttribute('data-layout-status', 'running', { timeout: 15_000 })
    const callsAtLayoutStart = await page.evaluate(() => (
      window.__bookMiroStandardDenseEdgeDraws.normalCalls
    ))
    await expect.poll(() => page.evaluate(() => (
      window.__bookMiroStandardDenseEdgeDraws.normalCalls
    )), { timeout: 5_000 }).toBeGreaterThan(callsAtLayoutStart)
    const earlyRender = await readStandardDenseRenderState(page)
    expect(earlyRender.edgeDraws.normalCalls).toBeGreaterThan(0)
    expect(earlyRender.edgeDraws.maxVertexWork).toBeGreaterThanOrEqual(
      STANDARD_DENSE_EDGE_COUNT * 3,
    )

    // Once the bounded worker window ends, LargeGraphView stops and kills its
    // supervisor, schedules one final render, and exposes the frozen state.
    await expect(largeGraph).toHaveAttribute('data-layout-status', 'frozen', { timeout: 20_000 })
    await expect(largeGraph).toHaveAttribute('data-node-label-status', 'ready')
    await expect.poll(() => page.evaluate(() => (
      window.__bookMiroStandardDenseLabelFrame.items.length
    ))).toBeGreaterThan(5)
    await expect.poll(() => page.evaluate(() => (
      performance.now() - window.__bookMiroStandardDenseLabelFrame.lastClearAt
    )), { timeout: 3_000 }).toBeGreaterThan(300)
    const frozenRender = await readStandardDenseRenderState(page)
    expect(frozenRender.labelCount).toBeGreaterThan(5)
    expect(frozenRender.labelCount).toBeLessThan(STANDARD_DENSE_NODE_COUNT)
    expect(frozenRender.uniqueLabelCount).toBe(frozenRender.labelCount)
    expect(frozenRender.overlapPairs).toBe(0)
    expect(frozenRender.allLabelsInside).toBe(true)

    // Sigma's custom label callback receives each node key and can select a
    // font per entity. Keep ordinary dense-graph labels at a compact 12px,
    // while ensuring hub labels grow continuously rather than jumping between
    // coarse degree buckets.
    const fontByLabel = new Map(frozenRender.labelFonts)
    const ordinaryFontSizes = graph.nodes
      .filter(node => degreeById.get(node.id) === 3 && fontByLabel.has(node.name))
      .map(node => fontByLabel.get(node.name)?.size)
    expect(ordinaryFontSizes.length).toBeGreaterThan(0)
    expect(ordinaryFontSizes.every(Number.isFinite)).toBe(true)
    expect(Math.min(...ordinaryFontSizes)).toBeCloseTo(12, 5)
    expect(Math.max(...ordinaryFontSizes)).toBeCloseTo(12, 5)

    const hubFontsByDegree = new Map()
    for (const node of graph.nodes) {
      const degree = degreeById.get(node.id)
      if (degree <= 3) continue
      const fontSize = fontByLabel.get(node.name)?.size
      if (!Number.isFinite(fontSize)) continue
      if (!hubFontsByDegree.has(degree)) hubFontsByDegree.set(degree, [])
      hubFontsByDegree.get(degree).push(fontSize)
    }
    const degreeFontSteps = [...hubFontsByDegree]
      .map(([degree, sizes]) => ({
        degree,
        size: sizes.reduce((sum, size) => sum + size, 0) / sizes.length,
      }))
      .sort((left, right) => left.degree - right.degree)
    expect(degreeFontSteps.length).toBeGreaterThan(0)
    expect(degreeFontSteps.every(step => Number.isFinite(step.size) && step.size > 12)).toBe(true)
    for (let index = 1; index < degreeFontSteps.length; index += 1) {
      expect(degreeFontSteps[index].size).toBeGreaterThan(degreeFontSteps[index - 1].size)
    }

    expect(frozenRender.edgeDraws.normalCalls).toBeGreaterThan(earlyRender.edgeDraws.normalCalls)
    expect(frozenRender.edgeDraws.lastVertexWork).toBeGreaterThanOrEqual(
      STANDARD_DENSE_EDGE_COUNT * 3,
    )

    // A frozen graph must remain visually stationary. Compare the complete
    // label-anchor map after one second rather than imposing a preferred
    // topology or uniform spatial distribution.
    await page.waitForTimeout(1_000)
    const oneSecondLater = await readStandardDenseRenderState(page)
    expect(oneSecondLater.labelCount).toBe(frozenRender.labelCount)
    expect(oneSecondLater.overlapPairs).toBe(0)
    expect(oneSecondLater.anchors).toHaveLength(frozenRender.anchors.length)
    const frozenAnchorDelta = maximumAnchorDelta(frozenRender.anchors, oneSecondLater.anchors)
    expect(frozenAnchorDelta).toBeLessThanOrEqual(0.25)

    // Zooming reveals more local context without reintroducing collisions.
    const settledAnchors = new Map(oneSecondLater.anchors)
    const focusAnchor = [...settledAnchors.values()][0]

    const graphBounds = await largeGraph.boundingBox()
    expect(graphBounds).toBeTruthy()
    await page.mouse.move(graphBounds.x + focusAnchor.x, graphBounds.y + focusAnchor.y)
    const frameBeforeZoom = oneSecondLater.frameCount
    const zoomStartedAt = Date.now()
    await page.mouse.wheel(0, -120)
    await expect.poll(() => page.evaluate(() => (
      window.__bookMiroStandardDenseLabelFrame.clearCount
    ))).toBeGreaterThan(frameBeforeZoom)
    await expect.poll(() => page.evaluate(() => (
      performance.now() - window.__bookMiroStandardDenseLabelFrame.lastClearAt
    )), { timeout: 3_000 }).toBeGreaterThan(300)
    const zoomedRender = await readStandardDenseRenderState(page)
    const zoomMs = Date.now() - zoomStartedAt
    const averageFontSize = render => render.labelFonts.reduce(
      (sum, [, font]) => sum + font.size,
      0,
    ) / render.labelFonts.length

    expect(zoomedRender.labelCount).toBeGreaterThan(5)
    expect(averageFontSize(zoomedRender)).toBeGreaterThan(averageFontSize(frozenRender) * 1.05)
    expect(zoomedRender.uniqueLabelCount).toBe(zoomedRender.labelCount)
    expect(zoomedRender.overlapPairs).toBe(0)
    expect(zoomedRender.allLabelsInside).toBe(true)
    expect(zoomMs).toBeLessThan(2_500)

    // Return to the settled overview and keep the collision contract intact.
    const frameBeforeRestore = zoomedRender.frameCount
    await page.mouse.wheel(0, 120)
    await expect.poll(() => page.evaluate(() => (
      window.__bookMiroStandardDenseLabelFrame.clearCount
    ))).toBeGreaterThan(frameBeforeRestore)
    await expect.poll(() => page.evaluate(() => (
      window.__bookMiroStandardDenseLabelFrame.items.length
    ))).toBeGreaterThan(5)
    await expect.poll(() => page.evaluate(() => (
      performance.now() - window.__bookMiroStandardDenseLabelFrame.lastClearAt
    )), { timeout: 3_000 }).toBeGreaterThan(300)
    const restoredRender = await readStandardDenseRenderState(page)
    expect(restoredRender.overlapPairs).toBe(0)
    expect(restoredRender.allLabelsInside).toBe(true)

    const layoutHeartbeat = await readHeartbeat(page)
    console.log('standard dense render metrics', {
      earlyEdgeCalls: earlyRender.edgeDraws.normalCalls,
      frozenEdgeCalls: frozenRender.edgeDraws.normalCalls,
      maxEdgeVertexWork: frozenRender.edgeDraws.maxVertexWork,
      degreeFontSteps,
      labelCounts: [frozenRender.labelCount, zoomedRender.labelCount, restoredRender.labelCount],
      zoomMs,
      frozenAnchorDelta,
      layoutHeartbeat,
    })
    expect(layoutHeartbeat.samples).toBeGreaterThan(50)
    expect(layoutHeartbeat.maxGap).toBeLessThan(500)
  })
})
