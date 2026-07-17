import { expect, test } from '@playwright/test'

const projectId = 'proj_aaaaaaaaaaaa'
const EPISODE_COUNT = 12
const CURRENT_NODE_COUNT = 96
const CURRENT_EDGE_COUNT = 240
const ALL_NODE_COUNT = 5_000
const ALL_EDGE_COUNT = 20_000
const HEARTBEAT_INTERVAL_MS = 16

const episodeFor = (index) => (
  index < CURRENT_NODE_COUNT
    ? 0
    : 1 + ((index - CURRENT_NODE_COUNT) % (EPISODE_COUNT - 1))
)

const makeAllChaptersGraph = () => {
  const nodes = Array.from({ length: ALL_NODE_COUNT }, (_, index) => {
    const episode = episodeFor(index)
    return {
      id: `entity-${index}`,
      name: `Entity ${index}`,
      type: index % 3 === 0 ? 'Person' : index % 3 === 1 ? 'Concept' : 'Place',
      first_episode: episode,
      last_episode: episode,
      mentions: [{ episode, quote: `Entity ${index}` }],
    }
  })

  const edges = Array.from({ length: ALL_EDGE_COUNT }, (_, index) => {
    const isCurrent = index < CURRENT_EDGE_COUNT
    const sourceIndex = isCurrent
      ? index % CURRENT_NODE_COUNT
      : index % ALL_NODE_COUNT
    let targetIndex = isCurrent
      ? (index * 17 + 1) % CURRENT_NODE_COUNT
      : (index * 37 + Math.floor(index / ALL_NODE_COUNT) + 1) % ALL_NODE_COUNT
    if (targetIndex === sourceIndex) targetIndex = (targetIndex + 1) % ALL_NODE_COUNT
    const episode = isCurrent
      ? 0
      : 1 + ((index - CURRENT_EDGE_COUNT) % (EPISODE_COUNT - 1))
    return {
      id: `relationship-${index}`,
      source: `entity-${sourceIndex}`,
      target: `entity-${targetIndex}`,
      label: `connects ${index}`,
      fact: `Stress-test relationship ${index}`,
      first_episode: episode,
      last_episode: episode,
      mentions: [{ episode, quote: `Relationship ${index}` }],
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
      window.setInterval(() => {
        const heartbeat = window.__bookMiroHeartbeat
        const current = performance.now()
        heartbeat.samples.push(current - heartbeat.last)
        heartbeat.last = current
      }, heartbeatInterval)
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

    // Give the heartbeat one turn after the ready mutation so the final graph
    // synchronization stall is included in the sample.
    await page.waitForTimeout(100)
    const switchHeartbeat = await readHeartbeat(page)
    console.log('all-chapters switch metrics', {
      searchFillMs,
      searchResultMs,
      rendererReadyMs,
      switchHeartbeat,
    })
    expect(searchResultMs).toBeLessThan(2_000)
    expect(rendererReadyMs).toBeLessThan(3_000)
    expect(switchHeartbeat.samples).toBeGreaterThan(3)
    expect(switchHeartbeat.maxGap).toBeLessThan(500)

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
})
