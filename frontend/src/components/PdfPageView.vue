<template>
  <div ref="root" class="pdf-page-view" :class="{ loading, failed: error }">
    <div v-if="loading" class="pdf-page-status">{{ $t('reader.pdfPageLoading') }}</div>
    <div v-else-if="error" class="pdf-page-status error">{{ error }}</div>
    <div ref="surface" class="pdf-page-surface" :style="surfaceStyle">
      <canvas ref="canvas" class="pdf-page-canvas"></canvas>
      <div ref="textLayer" class="textLayer pdf-text-layer" @click="onTextLayerClick"></div>
      <div class="pdf-native-link-layer">
        <template v-for="link in nativeLinks" :key="link.id">
          <a
            v-if="link.url"
            class="pdf-native-link external"
            :href="link.url"
            target="_blank"
            rel="noopener noreferrer"
            :style="link.style"
            :title="$t('reader.pdfExternalLink')"
            :aria-label="$t('reader.pdfExternalLink')"
          ></a>
          <button
            v-else
            type="button"
            class="pdf-native-link internal"
            :style="link.style"
            :data-target-page="link.pageNumber"
            :title="$t('reader.pdfInternalLink', { page: link.pageNumber })"
            :aria-label="$t('reader.pdfInternalLink', { page: link.pageNumber })"
            @click.stop="onNativeLinkClick(link)"
          ></button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as pdfjs from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/web/pdf_viewer.css'
import { createPdfAnnotationPlan } from '../utils/pdfAnnotations'

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl

const props = defineProps({
  sourceUrl: { type: String, required: true },
  pageNumber: { type: Number, required: true },
  highlightText: { type: String, default: '' },
  links: { type: Array, default: () => [] },
})

const emit = defineEmits(['link-click', 'page-link-click', 'rendered'])
const { t } = useI18n()
const root = ref(null)
const surface = ref(null)
const canvas = ref(null)
const textLayer = ref(null)
const loading = ref(true)
const error = ref('')
const pageWidth = ref(0)
const pageHeight = ref(0)
const nativeLinks = ref([])
const surfaceStyle = computed(() => ({
  width: pageWidth.value ? `${pageWidth.value}px` : undefined,
  height: pageHeight.value ? `${pageHeight.value}px` : undefined,
}))

const documents = new Map()
const getDocument = (url) => {
  if (!documents.has(url)) {
    const task = pdfjs.getDocument({ url })
    documents.set(url, task.promise.catch((err) => {
      documents.delete(url)
      throw err
    }))
  }
  return documents.get(url)
}

let resizeObserver
let renderTask
let textRenderTask
let renderToken = 0
let resizeTimer
let textSpans = []
let textSpanTexts = []
let lastRequestedWidth = 0

const safeExternalUrl = (value) => {
  const url = String(value || '').trim()
  return /^(?:https?:|mailto:)/i.test(url) ? url : ''
}

const resolveDestinationPage = async (document, destination) => {
  try {
    const explicit = typeof destination === 'string'
      ? await document.getDestination(destination)
      : destination
    if (!Array.isArray(explicit) || explicit.length === 0) return null
    const pageRef = explicit[0]
    if (Number.isInteger(pageRef)) return pageRef + 1
    return (await document.getPageIndex(pageRef)) + 1
  } catch (e) {
    return null
  }
}

const buildNativeLinks = async (document, page, viewport, token) => {
  try {
    const annotations = await page.getAnnotations({ intent: 'display' })
    const links = await Promise.all(annotations
      .filter(annotation => annotation.subtype === 'Link' && Array.isArray(annotation.rect))
      .map(async (annotation, index) => {
        const [x1, y1] = viewport.convertToViewportPoint(annotation.rect[0], annotation.rect[1])
        const [x2, y2] = viewport.convertToViewportPoint(annotation.rect[2], annotation.rect[3])
        const left = Math.min(x1, x2)
        const top = Math.min(y1, y2)
        const width = Math.abs(x2 - x1)
        const height = Math.abs(y2 - y1)
        if (width < 1 || height < 1) return null

        const url = safeExternalUrl(annotation.url || annotation.unsafeUrl)
        const pageNumber = url ? null : await resolveDestinationPage(document, annotation.dest)
        if (!url && !pageNumber) return null
        return {
          id: annotation.id || `${props.pageNumber}-${index}`,
          url,
          pageNumber,
          style: {
            left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${height}px`,
          },
        }
      }))
    if (token === renderToken) nativeLinks.value = links.filter(Boolean)
  } catch (e) {
    // A malformed optional annotation should never make the PDF page itself
    // unreadable. Keep the canvas/text layer and omit only its native links.
    if (token === renderToken) nativeLinks.value = []
  }
}

const applyAnnotations = async () => {
  const plan = createPdfAnnotationPlan(textSpanTexts, props.links, props.highlightText)
  const highlights = []

  textSpans.forEach((span, spanIndex) => {
    span.classList.remove('pdf-quote-mark', 'pdf-text-link', 'pdf-link-edge', 'pdf-link-seen')
    delete span.dataset.pdfLinkIndex
    delete span.dataset.edgeId
    const fragment = document.createDocumentFragment()
    for (const segment of plan.spans[spanIndex] || []) {
      if (segment.linkIndex < 0 && !segment.highlight) {
        fragment.append(document.createTextNode(segment.text))
        continue
      }

      const annotation = document.createElement('span')
      annotation.classList.add('pdf-annotation-segment')
      annotation.textContent = segment.text
      if (segment.highlight) {
        annotation.classList.add('pdf-quote-mark')
        highlights.push(annotation)
      }
      if (segment.linkIndex >= 0) {
        const link = props.links[segment.linkIndex]
        annotation.classList.add('pdf-text-link')
        annotation.dataset.pdfLinkIndex = String(segment.linkIndex)
        if (link?.type === 'edge') {
          annotation.classList.add('pdf-link-edge')
          annotation.dataset.edgeId = link.id
        }
        if (link?.seen) annotation.classList.add('pdf-link-seen')
      }
      fragment.append(annotation)
    }
    span.replaceChildren(fragment)
  })

  if (plan.hasHighlight && highlights.length) {
    await nextTick()
    highlights[0].scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

const onTextLayerClick = (event) => {
  const span = event.target.closest('[data-pdf-link-index]')
  if (!span) return
  const link = props.links[Number(span.dataset.pdfLinkIndex)]
  if (link) emit('link-click', link)
}

const onNativeLinkClick = (link) => {
  if (link?.pageNumber) emit('page-link-click', { pageNumber: link.pageNumber })
}

const renderPage = async () => {
  const token = ++renderToken
  if (!root.value || !canvas.value || !textLayer.value || !props.sourceUrl || !props.pageNumber) return
  loading.value = true
  error.value = ''
  nativeLinks.value = []
  try {
    renderTask?.cancel()
    textRenderTask?.cancel()
    const document = await getDocument(props.sourceUrl)
    const page = await document.getPage(props.pageNumber)
    if (token !== renderToken) return

    const baseViewport = page.getViewport({ scale: 1 })
    const available = Math.max(240, root.value.clientWidth || 640)
    lastRequestedWidth = available
    const scale = available / baseViewport.width
    const viewport = page.getViewport({ scale })
    const nativeLinksPromise = buildNativeLinks(document, page, viewport, token)
    const outputScale = Math.min(window.devicePixelRatio || 1, 2)
    const targetCanvas = canvas.value
    const context = targetCanvas.getContext('2d', { alpha: false })
    targetCanvas.width = Math.floor(viewport.width * outputScale)
    targetCanvas.height = Math.floor(viewport.height * outputScale)
    targetCanvas.style.width = `${viewport.width}px`
    targetCanvas.style.height = `${viewport.height}px`
    pageWidth.value = viewport.width
    pageHeight.value = viewport.height
    // TextLayer's CSS normally inherits this from `.pdfViewer .page`. This
    // standalone reader surface has neither wrapper, so set it explicitly to
    // keep hit targets and highlights aligned with the canvas.
    textLayer.value.style.setProperty('--total-scale-factor', String(viewport.scale))
    textLayer.value.style.setProperty('--scale-round-x', '1px')
    textLayer.value.style.setProperty('--scale-round-y', '1px')

    renderTask = page.render({
      canvasContext: context,
      viewport,
      transform: outputScale === 1 ? null : [outputScale, 0, 0, outputScale, 0, 0],
    })
    await renderTask.promise
    if (token !== renderToken) return

    textLayer.value.replaceChildren()
    const textContent = await page.getTextContent()
    textRenderTask = new pdfjs.TextLayer({
      textContentSource: textContent,
      container: textLayer.value,
      viewport,
    })
    await textRenderTask.render()
    if (token !== renderToken) return
    textSpans = textRenderTask.textDivs || [...textLayer.value.querySelectorAll('span')]
    textSpanTexts = textSpans.map(span => span.textContent || '')
    await applyAnnotations()
    await nativeLinksPromise
    loading.value = false
    emit('rendered', { pageNumber: props.pageNumber })
  } catch (err) {
    if (err?.name === 'RenderingCancelledException') return
    loading.value = false
    error.value = t('reader.pdfPageError')
  }
}

watch(() => [props.sourceUrl, props.pageNumber], renderPage)
watch(() => [props.highlightText, props.links], applyAnnotations, { deep: true })

onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    const width = Math.max(240, root.value?.clientWidth || 640)
    if (Math.abs(width - lastRequestedWidth) < 8) return
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(renderPage, 100)
  })
  resizeObserver.observe(root.value)
  renderPage()
})

onBeforeUnmount(() => {
  renderToken += 1
  clearTimeout(resizeTimer)
  resizeObserver?.disconnect()
  renderTask?.cancel()
  textRenderTask?.cancel()
  for (const documentPromise of documents.values()) {
    documentPromise.then(document => document.destroy()).catch(() => {})
  }
  documents.clear()
})
</script>

<style scoped>
.pdf-page-view {
  position: relative;
  width: 100%;
  min-height: 260px;
  display: flex;
  justify-content: center;
  background: #e9e9e9;
}
.pdf-page-surface {
  position: relative;
  flex: 0 0 auto;
  background: #fff;
  box-shadow: 0 4px 18px rgba(0,0,0,0.16);
}
.pdf-page-canvas { display: block; }
.pdf-text-layer { inset: 0; }
.pdf-native-link-layer { position: absolute; inset: 0; z-index: 2; pointer-events: none; }
.pdf-native-link {
  position: absolute; box-sizing: border-box; padding: 0; border: 0;
  display: block; pointer-events: auto; cursor: pointer; background: transparent;
  border-radius: 2px; outline: none;
}
.pdf-native-link:hover,
.pdf-native-link:focus-visible {
  background: rgba(0,78,137,0.12);
  box-shadow: inset 0 -2px 0 rgba(0,78,137,0.75), 0 0 0 1px rgba(0,78,137,0.24);
}
.pdf-page-status {
  position: absolute;
  z-index: 3;
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(255,255,255,0.92);
  color: #555;
  font: 12px/1.4 system-ui, sans-serif;
  box-shadow: 0 2px 10px rgba(0,0,0,0.08);
}
.pdf-page-status.error { color: #C5283D; }
.pdf-page-view.loading .pdf-page-surface { visibility: hidden; }
:deep(.pdf-annotation-segment) {
  position: static !important;
  display: inline;
  color: transparent;
  font: inherit;
  letter-spacing: inherit;
  word-spacing: inherit;
  white-space: inherit;
  transform: none !important;
  -webkit-user-select: text;
  user-select: text;
}
:deep(.pdf-quote-mark) {
  background: rgba(255,193,7,0.52) !important;
  box-shadow: 0 0 0 2px rgba(255,193,7,0.38);
}
:deep(.pdf-text-link) {
  cursor: pointer;
  border-bottom: 2px solid #7B2D8E;
  background: rgba(123,45,142,0.10);
}
:deep(.pdf-text-link.pdf-link-edge) {
  border-bottom-color: #E91E63;
  background: rgba(233,30,99,0.10);
}
:deep(.pdf-text-link.pdf-link-seen) {
  border-bottom: 2px solid rgba(123,45,142,0.58);
  background: rgba(123,45,142,0.07);
}
:deep(.pdf-text-link.pdf-link-seen.pdf-link-edge) {
  border-bottom-color: rgba(233,30,99,0.58);
  background: rgba(233,30,99,0.07);
}
:deep(.pdf-text-link.pdf-link-seen:hover) { background: rgba(123,45,142,0.14); }
:deep(.pdf-text-link.pdf-link-seen.pdf-link-edge:hover) { background: rgba(233,30,99,0.14); }
</style>
