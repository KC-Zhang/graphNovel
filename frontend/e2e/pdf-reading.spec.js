import { expect, test } from '@playwright/test'
import { existsSync } from 'node:fs'

const academicPdf = process.env.BOOKMIRO_ACADEMIC_PDF || ''

test.describe('PDF page reading', () => {
  test.skip(!academicPdf || !existsSync(academicPdf), 'Set BOOKMIRO_ACADEMIC_PDF to an academic PDF fixture')

  test.beforeEach(async ({ page }) => {
    await page.route('**/api/graph/extract', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { running: false, extracted_upto: -1 } }),
    }))
    await page.route('**/api/graph/status/**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { running: false, extracted_upto: 1000, failed_episodes: [], error: null },
      }),
    }))
    await page.route('**/api/graph/data/**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          nodes: [
            { id: 'agentopia', name: 'Agentopia', type: 'Concept', first_episode: 0, mentions: [] },
            { id: 'llm', name: 'LLM', type: 'concept', first_episode: 0, mentions: [] },
          ],
          edges: [{
            id: 'agentopia-enhances-llm',
            source: 'agentopia',
            target: 'llm',
            label: 'enhances',
            fact: 'Agentopia enhances underlying LLMs through life reward training.',
            first_episode: 0,
            mentions: [],
          }],
        },
      }),
    }))
  })

  test('preserves academic pages and keeps navigation, search, progress, and compact layout', async ({ page }) => {
    await page.goto('/')
    await page.locator('input[type="file"]').setInputFiles(academicPdf)
    await page.locator('.start-engine-btn').click()

    await expect(page.locator('.reading-mode-panel')).toBeVisible({ timeout: 120_000 })
    const pageMode = page.locator('.reading-mode-switch button').filter({ hasText: /By page|按页面/ })
    if (!(await pageMode.getAttribute('class'))?.includes('active')) await pageMode.click()

    const projectId = new URL(page.url()).pathname.split('/').pop()
    const projectResponse = await page.request.get(`http://127.0.0.1:5001/api/graph/project/${projectId}`)
    const project = (await projectResponse.json()).data
    expect(project.page_count).toBe(44)
    const previews = page.locator('.chapter-preview-item')
    await expect(previews).toHaveCount(Math.min(30, project.page_count), { timeout: 60_000 })
    await expect(previews.first()).toContainText(/Page 1|第 1 页/)
    await page.locator('.review-actions .retry-btn:not(.secondary)').click()

    const canvas = page.locator('.pdf-page-canvas')
    await expect(canvas).toBeVisible({ timeout: 30_000 })
    await expect.poll(async () => canvas.evaluate(el => [el.width, el.height])).not.toEqual([0, 0])

    await page.locator('.nav-arrow').filter({ hasText: '›' }).click()
    await expect(page.locator('.episode-title')).toContainText(/Page 2|第 2 页/)
    await expect(canvas).toBeVisible()

    const episodeResponse = await page.request.get(`http://127.0.0.1:5001/api/graph/episode/${projectId}/1`)
    const episode = (await episodeResponse.json()).data
    const searchTerm = String(episode.text || '').match(/[A-Za-z]{7,}/)?.[0]
    expect(searchTerm).toBeTruthy()
    await page.locator('.search-input').fill(searchTerm)
    await expect(page.locator('.search-result.body').first()).toBeVisible({ timeout: 30_000 })
    await page.locator('.search-result.body').first().click()
    await expect(page.locator('.pdf-text-layer .pdf-quote-mark').first()).toBeVisible({ timeout: 20_000 })

    const reader = page.locator('.book-text')
    await reader.evaluate(el => { el.scrollTop = el.scrollHeight })
    await page.waitForTimeout(1400)
    const progressBefore = await page.locator('.read-ring-text').textContent()
    expect(Number(progressBefore)).toBeGreaterThan(0)
    await page.locator('.nav-arrow').filter({ hasText: '›' }).click()
    await page.locator('.nav-arrow').filter({ hasText: '‹' }).click()
    await expect(page.locator('.read-ring-text')).toHaveText(progressBefore)

    const relationship = page.locator('.links text').filter({ hasText: 'enhances' })
    await expect(relationship).toBeVisible()
    await relationship.click()
    const statement = page.locator('.detail-panel .relationship-statement')
    await expect(statement).toContainText(/Source|来源实体/)
    await expect(statement).toContainText(/Relationship|关系/)
    await expect(statement).toContainText(/Target|目标实体/)
    await expect(statement).toContainText('Agentopia')
    await expect(statement).toContainText('enhances')
    await expect(statement).toContainText('LLM')
    await expect(statement).not.toContainText('→')

    await page.setViewportSize({ width: 800, height: 800 })
    await expect(page.locator('.reader-body')).not.toHaveClass(/single-pane/)
    const resizer = page.locator('.pane-resizer')
    const resizerBox = await resizer.boundingBox()
    await page.mouse.move(resizerBox.x + 2, resizerBox.y + 20)
    await page.mouse.down()
    await page.mouse.move(120, resizerBox.y + 20)
    await page.mouse.up()
    await expect(page.locator('.reader-body')).not.toHaveClass(/single-pane/)
    await expect(page.locator('.graph-pane')).toBeVisible()
    expect(await page.locator('.book-pane').evaluate(el => el.getBoundingClientRect().width)).toBeGreaterThanOrEqual(319)

    await page.setViewportSize({ width: 600, height: 800 })
    await expect(page.locator('.reader-body')).toHaveClass(/single-pane/)
    await expect(page.locator('.pane-action').filter({ hasText: /Open graph|打开图谱/ })).toBeVisible()
    const noHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
    expect(noHorizontalOverflow).toBe(true)
    await page.locator('.pane-action').filter({ hasText: /Open graph|打开图谱/ }).click()
    await expect(page.locator('.graph-pane')).toBeVisible()
    await page.locator('.graph-pane .icon-maximize').click()
    await expect(page.locator('.book-pane')).toBeVisible()
  })
})
