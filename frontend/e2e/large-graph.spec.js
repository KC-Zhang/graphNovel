import { expect, test } from '@playwright/test'

const projectId = 'proj_aaaaaaaaaaaa'

const makeLargeGraph = () => {
  const nodes = Array.from({ length: 600 }, (_, index) => ({
    id: `entity-${index}`,
    name: `Entity ${index}`,
    type: index % 2 ? 'Concept' : 'Person',
    first_episode: 0,
    mentions: [{ episode: 0, quote: `Entity ${index}` }],
  }))
  const edges = Array.from({ length: 1200 }, (_, index) => ({
    id: `relationship-${index}`,
    source: `entity-${index % nodes.length}`,
    target: `entity-${(index * 17 + 1) % nodes.length}`,
    label: `connects ${index}`,
    fact: `Entity ${index % nodes.length} is connected in the stress-test graph.`,
    first_episode: 0,
    mentions: [{ episode: 0, quote: `Entity ${index % nodes.length}` }],
  }))
  return { nodes, edges }
}

test.describe('large graph renderer', () => {
  test('uses WebGL for a huge graph without blocking core reader controls', async ({ page }) => {
    const graph = makeLargeGraph()
    let releaseGraphResponse
    let graphReleasedAt = 0
    let markGraphRequested
    let markStatusRequested
    let graphRequestCount = 0
    const graphResponseGate = new Promise(resolve => { releaseGraphResponse = resolve })
    const graphRequested = new Promise(resolve => { markGraphRequested = resolve })
    const statusRequested = new Promise(resolve => { markStatusRequested = resolve })
    const project = {
      project_id: projectId,
      name: 'Large graph acceptance fixture',
      language: 'English',
      source_format: 'txt',
      reading_mode: 'chapter',
      document_kind: 'novel',
      extracted_upto: 0,
      episodes: [{
        index: 0,
        title: 'Chapter 1: A responsive graph',
        start_char: 0,
        end_char: 124,
        char_count: 124,
        unit_type: 'chapter',
      }],
      files: [{ filename: 'large-graph.txt' }],
    }

    await page.route(`**/api/graph/project/${projectId}`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: project }),
    }))
    await page.route(`**/api/graph/episode/${projectId}/0`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          index: 0,
          title: project.episodes[0].title,
          text: 'Entity 0 introduces the knowledge graph. Entity 1 keeps the reader interactive while the graph lays itself out.',
        },
      }),
    }))
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
            revision_episode: 0,
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
          data: { running: false, extracted_upto: 0, failed_episodes: [], error: null },
        }),
      })
    })
    await page.route('**/api/graph/extract', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { running: false, extracted_upto: 0, failed_episodes: [], error: null },
      }),
    }))
    await page.route(`**/api/graph/search/${projectId}*`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { results: [] } }),
    }))

    await page.goto(`/read/${projectId}`)

    await graphRequested
    try {
      // Reader metadata, controls, and the graph loading state must be usable
      // while a large initial graph response is still in flight.
      await expect(page.locator('.episode-title')).toContainText('A responsive graph', { timeout: 2_000 })
      await expect(page.locator('.graph-state')).toBeVisible()
      await statusRequested
      await page.waitForTimeout(50)
      expect(graphRequestCount).toBe(1)
    } finally {
      graphReleasedAt = Date.now()
      releaseGraphResponse()
    }

    const largeGraph = page.locator('.large-graph-view')
    await expect(largeGraph).toBeVisible({ timeout: 30_000 })
    await expect(largeGraph).toHaveAttribute('data-node-count', '600')
    await expect(largeGraph).toHaveAttribute('data-edge-count', '1200')
    await expect(largeGraph).toHaveAttribute('data-renderer-status', 'ready', { timeout: 30_000 })
    expect(Date.now() - graphReleasedAt).toBeLessThan(2_000)
    await expect(largeGraph.locator('canvas').first()).toBeVisible()
    await expect(page.locator('.graph-svg')).toHaveCount(0)

    // ForceAtlas2 runs in a worker. Reader and graph toolbar interactions must
    // remain available while that layout is still settling.
    const interactionStarted = Date.now()
    const searchInput = page.locator('.search-input')
    await searchInput.fill('Entity 42')
    await expect(searchInput).toHaveValue('Entity 42')
    await expect(page.locator('.search-results')).toBeVisible()
    expect(Date.now() - interactionStarted).toBeLessThan(2_500)
    await searchInput.press('Escape')
    await expect(page.locator('.search-results')).toHaveCount(0)

    const focusUnread = page.locator('.tool-btn').filter({ hasText: /Focus unread|只看未读/ })
    await focusUnread.click()
    await expect(focusUnread).toHaveClass(/active/)

    await page.locator('.graph-pane .icon-maximize').click()
    await expect(page.locator('.reader-body')).toHaveClass(/graph-maximized/)
    await page.locator('.graph-pane .icon-maximize').click()
    await expect(page.locator('.reader-body')).not.toHaveClass(/graph-maximized/)

    const mainThreadDelay = await page.evaluate(() => new Promise(resolve => {
      const started = performance.now()
      setTimeout(() => resolve(performance.now() - started), 0)
    }))
    expect(mainThreadDelay).toBeLessThan(1_000)
  })
})
