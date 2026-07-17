<template>
  <div ref="root" class="pdf-page-view" :class="{ loading, failed: error }">
    <div v-if="loading" class="pdf-page-status">{{ $t('reader.pdfPageLoading') }}</div>
    <div v-else-if="error" class="pdf-page-status error">{{ error }}</div>
    <div ref="surface" class="pdf-page-surface" :style="surfaceStyle">
      <canvas ref="canvas" class="pdf-page-canvas"></canvas>
      <div ref="textLayer" class="textLayer pdf-text-layer" @click="onTextLayerClick"></div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as pdfjs from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/web/pdf_viewer.css'

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl

const props = defineProps({
  sourceUrl: { type: String, required: true },
  pageNumber: { type: Number, required: true },
  highlightText: { type: String, default: '' },
  links: { type: Array, default: () => [] },
})

const emit = defineEmits(['link-click', 'rendered'])
const { t } = useI18n()
const root = ref(null)
const surface = ref(null)
const canvas = ref(null)
const textLayer = ref(null)
const loading = ref(true)
const error = ref('')
const pageWidth = ref(0)
const pageHeight = ref(0)
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
let lastRequestedWidth = 0

const normalizeForMatch = (value) => String(value || '')
  .normalize('NFKC')
  .toLocaleLowerCase()
  .replace(/\s+/g, ' ')
  .trim()

const buildTextIndex = () => {
  let normalized = ''
  const spanAt = []
  textSpans.forEach((span, spanIndex) => {
    const value = normalizeForMatch(span.textContent)
    if (!value) return
    if (normalized && !normalized.endsWith(' ')) {
      normalized += ' '
      spanAt.push(spanIndex)
    }
    for (const char of value) {
      normalized += char
      spanAt.push(spanIndex)
    }
  })
  return { normalized, spanAt }
}

const markMatch = (index, query, className, linkIndex = null) => {
  const needle = normalizeForMatch(query)
  if (!needle) return []
  const start = index.normalized.indexOf(needle)
  if (start < 0) return []
  const end = start + needle.length - 1
  const first = index.spanAt[start]
  const last = index.spanAt[Math.min(end, index.spanAt.length - 1)]
  if (!Number.isFinite(first) || !Number.isFinite(last)) return []
  const marked = []
  for (let i = first; i <= last; i += 1) {
    const span = textSpans[i]
    if (!span) continue
    span.classList.add(className)
    if (linkIndex !== null) span.dataset.pdfLinkIndex = String(linkIndex)
    marked.push(span)
  }
  return marked
}

const applyAnnotations = async () => {
  textSpans.forEach((span) => {
    span.classList.remove('pdf-quote-mark', 'pdf-text-link', 'pdf-link-edge', 'pdf-link-seen')
    delete span.dataset.pdfLinkIndex
    delete span.dataset.edgeId
  })
  const index = buildTextIndex()
  props.links.forEach((link, linkIndex) => {
    const marked = markMatch(index, link.quote || link.text || link.name, 'pdf-text-link', linkIndex)
    if (link.type === 'edge') marked.forEach((span) => {
      span.classList.add('pdf-link-edge')
      span.dataset.edgeId = link.id
    })
    if (link.seen) marked.forEach(span => span.classList.add('pdf-link-seen'))
  })
  const highlights = markMatch(index, props.highlightText, 'pdf-quote-mark')
  if (highlights.length) {
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

const renderPage = async () => {
  const token = ++renderToken
  if (!root.value || !canvas.value || !textLayer.value || !props.sourceUrl || !props.pageNumber) return
  loading.value = true
  error.value = ''
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
    const outputScale = Math.min(window.devicePixelRatio || 1, 2)
    const targetCanvas = canvas.value
    const context = targetCanvas.getContext('2d', { alpha: false })
    targetCanvas.width = Math.floor(viewport.width * outputScale)
    targetCanvas.height = Math.floor(viewport.height * outputScale)
    targetCanvas.style.width = `${viewport.width}px`
    targetCanvas.style.height = `${viewport.height}px`
    pageWidth.value = viewport.width
    pageHeight.value = viewport.height

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
    await applyAnnotations()
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
  border-bottom: 1px dotted #aaa;
  background: transparent;
}
</style>
