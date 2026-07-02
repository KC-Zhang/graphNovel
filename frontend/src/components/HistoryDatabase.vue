<template>
  <div 
    class="history-database"
    :class="{ 'no-projects': books.length === 0 && !loading }"
    ref="historyContainer"
  >
    <div v-if="books.length > 0 || loading" class="tech-grid-bg">
      <div class="grid-pattern"></div>
      <div class="gradient-overlay"></div>
    </div>

    <div class="section-header">
      <div class="section-line"></div>
      <span class="section-title">{{ $t('library.title') }}</span>
      <div class="section-line"></div>
    </div>

    <div v-if="books.length > 0" class="cards-container" :class="{ expanded: isExpanded }" :style="containerStyle">
      <div 
        v-for="(book, index) in books" 
        :key="book.project_id"
        class="project-card"
        :class="{ expanded: isExpanded, hovering: hoveringCard === index }"
        :style="getCardStyle(index)"
        @mouseenter="hoveringCard = index"
        @mouseleave="hoveringCard = null"
        @click="openBook(book)"
      >
        <div class="card-header">
          <span class="card-id">{{ statusLabel(book.status) }}</span>
          <span v-if="book.language" class="card-lang">{{ book.language }}</span>
        </div>

        <div class="card-files-wrapper">
          <div class="corner-mark top-left-only"></div>
          <div class="files-list" v-if="book.files && book.files.length > 0">
            <div 
              v-for="(file, fileIndex) in book.files.slice(0, 3)" 
              :key="fileIndex"
              class="file-item"
            >
              <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
              <span class="file-name">{{ truncateFilename(file.filename, 20) }}</span>
            </div>
            <div v-if="book.files.length > 3" class="files-more">
              {{ $t('history.moreFiles', { count: book.files.length - 3 }) }}
            </div>
          </div>
          <div class="files-empty" v-else>
            <span class="empty-file-icon">◇</span>
            <span class="empty-file-text">{{ $t('history.noFiles') }}</span>
          </div>
        </div>

        <h3 class="card-title">{{ book.name || $t('reader.untitled') }}</h3>
        <p class="card-desc">{{ $t('library.episodeCount', { count: (book.episodes && book.episodes.length) || 0 }) }}</p>

        <div class="card-footer">
          <div class="card-datetime">
            <span class="card-date">{{ formatDate(book.created_at) }}</span>
            <span class="card-time">{{ formatTime(book.created_at) }}</span>
          </div>
          <span class="card-progress" :class="progressClass(book.status)">
            <span class="status-dot">●</span> {{ statusLabel(book.status) }}
          </span>
        </div>

        <div class="card-bottom-line"></div>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <span class="loading-spinner"></span>
      <span class="loading-text">{{ $t('history.loadingText') }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, onActivated, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { listBooks } from '../api/book'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const books = ref([])
const loading = ref(true)
const isExpanded = ref(false)
const hoveringCard = ref(null)
const historyContainer = ref(null)
let observer = null
let isAnimating = false
let expandDebounceTimer = null
let pendingState = null

const CARDS_PER_ROW = 4
const CARD_WIDTH = 280
const CARD_HEIGHT = 280
const CARD_GAP = 24

const containerStyle = computed(() => {
  if (!isExpanded.value) return { minHeight: '420px' }
  const total = books.value.length
  if (total === 0) return { minHeight: '280px' }
  const rows = Math.ceil(total / CARDS_PER_ROW)
  const expandedHeight = rows * CARD_HEIGHT + (rows - 1) * CARD_GAP + 10
  return { minHeight: `${expandedHeight}px` }
})

const getCardStyle = (index) => {
  const total = books.value.length
  if (isExpanded.value) {
    const transition = 'transform 700ms cubic-bezier(0.23, 1, 0.32, 1), opacity 700ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.3s ease, border-color 0.3s ease'
    const row = Math.floor(index / CARDS_PER_ROW)
    const currentRowStart = row * CARDS_PER_ROW
    const currentRowCards = Math.min(CARDS_PER_ROW, total - currentRowStart)
    const rowWidth = currentRowCards * CARD_WIDTH + (currentRowCards - 1) * CARD_GAP
    const startX = -(rowWidth / 2) + (CARD_WIDTH / 2)
    const colInRow = index % CARDS_PER_ROW
    const x = startX + colInRow * (CARD_WIDTH + CARD_GAP)
    const y = 20 + row * (CARD_HEIGHT + CARD_GAP)
    return { transform: `translate(${x}px, ${y}px) rotate(0deg) scale(1)`, zIndex: 100 + index, opacity: 1, transition }
  } else {
    const transition = 'transform 700ms cubic-bezier(0.23, 1, 0.32, 1), opacity 700ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.3s ease, border-color 0.3s ease'
    const centerIndex = (total - 1) / 2
    const offset = index - centerIndex
    const x = offset * 35
    const y = 25 + Math.abs(offset) * 8
    const r = offset * 3
    const s = 0.95 - Math.abs(offset) * 0.05
    return { transform: `translate(${x}px, ${y}px) rotate(${r}deg) scale(${s})`, zIndex: 10 + index, opacity: 1, transition }
  }
}

const statusLabel = (status) => {
  const map = {
    created: t('library.statusReady'),
    graph_building: t('library.statusBuilding'),
    graph_completed: t('library.statusDone'),
    failed: t('library.statusFailed')
  }
  return map[status] || status
}

const progressClass = (status) => {
  if (status === 'graph_completed') return 'completed'
  if (status === 'graph_building') return 'in-progress'
  if (status === 'failed') return 'not-started'
  return 'not-started'
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  try { return new Date(dateStr).toISOString().slice(0, 10) } catch { return dateStr?.slice(0, 10) || '' }
}
const formatTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  } catch { return '' }
}

const getFileType = (filename) => {
  if (!filename) return 'other'
  const ext = filename.split('.').pop()?.toLowerCase()
  const typeMap = { pdf: 'pdf', txt: 'txt', md: 'txt', markdown: 'txt' }
  return typeMap[ext] || 'other'
}
const getFileTypeLabel = (filename) => {
  if (!filename) return 'FILE'
  return filename.split('.').pop()?.toUpperCase() || 'FILE'
}
const truncateFilename = (filename, maxLength) => {
  if (!filename) return t('history.unknownFile')
  if (filename.length <= maxLength) return filename
  const ext = filename.includes('.') ? '.' + filename.split('.').pop() : ''
  const nameWithoutExt = filename.slice(0, filename.length - ext.length)
  return nameWithoutExt.slice(0, maxLength - ext.length - 3) + '...' + ext
}

const openBook = (book) => {
  router.push({ name: 'Reader', params: { projectId: book.project_id } })
}

const loadBooks = async () => {
  try {
    loading.value = true
    const response = await listBooks(20)
    if (response.success) books.value = response.data || []
  } catch (e) {
    books.value = []
  } finally {
    loading.value = false
  }
}

const initObserver = () => {
  if (observer) observer.disconnect()
  observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      const shouldExpand = entry.isIntersecting
      pendingState = shouldExpand
      if (expandDebounceTimer) { clearTimeout(expandDebounceTimer); expandDebounceTimer = null }
      if (isAnimating) return
      if (shouldExpand === isExpanded.value) { pendingState = null; return }
      const delay = shouldExpand ? 50 : 200
      expandDebounceTimer = setTimeout(() => {
        if (isAnimating) return
        if (pendingState === null || pendingState === isExpanded.value) return
        isAnimating = true
        isExpanded.value = pendingState
        pendingState = null
        setTimeout(() => { isAnimating = false }, 750)
      }, delay)
    })
  }, { threshold: [0.4, 0.6, 0.8], rootMargin: '0px 0px -150px 0px' })
  if (historyContainer.value) observer.observe(historyContainer.value)
}

watch(() => route.path, (newPath) => { if (newPath === '/') loadBooks() })

onMounted(async () => {
  await nextTick()
  await loadBooks()
  setTimeout(() => initObserver(), 100)
})
onActivated(() => loadBooks())
onUnmounted(() => {
  if (observer) { observer.disconnect(); observer = null }
  if (expandDebounceTimer) { clearTimeout(expandDebounceTimer); expandDebounceTimer = null }
})
</script>

<style scoped>
.history-database { position: relative; width: 100%; min-height: 280px; margin-top: 40px; padding: 35px 0 40px; overflow: visible; }
.history-database.no-projects { min-height: auto; padding: 40px 0 20px; }
.tech-grid-bg { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
.grid-pattern {
  position: absolute; inset: 0;
  background-image: linear-gradient(to right, rgba(0,0,0,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(0,0,0,0.05) 1px, transparent 1px);
  background-size: 50px 50px; background-position: top left;
}
.gradient-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(to right, rgba(255,255,255,0.9) 0%, transparent 15%, transparent 85%, rgba(255,255,255,0.9) 100%), linear-gradient(to bottom, rgba(255,255,255,0.8) 0%, transparent 20%, transparent 80%, rgba(255,255,255,0.8) 100%);
  pointer-events: none;
}
.section-header { position: relative; z-index: 100; display: flex; align-items: center; justify-content: center; gap: 24px; margin-bottom: 24px; font-family: 'JetBrains Mono', monospace; padding: 0 40px; }
.section-line { flex: 1; height: 1px; background: linear-gradient(90deg, transparent, #E5E7EB, transparent); max-width: 300px; }
.section-title { font-size: 0.8rem; font-weight: 500; color: #9CA3AF; letter-spacing: 3px; text-transform: uppercase; }
.cards-container { position: relative; display: flex; justify-content: center; align-items: flex-start; padding: 0 40px; transition: min-height 700ms cubic-bezier(0.23, 1, 0.32, 1); }
.project-card {
  position: absolute; width: 280px; background: #FFF; border: 1px solid #E5E7EB; border-radius: 0; padding: 14px;
  cursor: pointer; box-shadow: 0 1px 2px 0 rgba(0,0,0,0.05);
  transition: box-shadow 0.3s ease, border-color 0.3s ease, transform 700ms cubic-bezier(0.23,1,0.32,1), opacity 700ms cubic-bezier(0.23,1,0.32,1);
}
.project-card:hover { box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05); border-color: rgba(0,0,0,0.4); z-index: 1000 !important; }
.project-card.hovering { z-index: 1000 !important; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #F3F4F6; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; }
.card-id { color: #6B7280; letter-spacing: 0.5px; font-weight: 500; }
.card-lang { color: #FF4500; font-weight: 600; }
.card-files-wrapper { position: relative; width: 100%; min-height: 48px; max-height: 110px; margin-bottom: 12px; padding: 8px 10px; background: linear-gradient(135deg, #f8f9fa 0%, #f1f3f4 100%); border-radius: 4px; border: 1px solid #e8eaed; overflow: hidden; }
.files-list { display: flex; flex-direction: column; gap: 4px; }
.files-more { display: flex; align-items: center; justify-content: center; padding: 3px 6px; font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; color: #6B7280; background: rgba(255,255,255,0.5); border-radius: 3px; }
.file-item { display: flex; align-items: center; gap: 8px; padding: 4px 6px; background: rgba(255,255,255,0.7); border-radius: 3px; transition: all 0.2s ease; }
.file-item:hover { background: rgba(255,255,255,1); transform: translateX(2px); }
.file-tag { display: inline-flex; align-items: center; justify-content: center; height: 16px; padding: 0 4px; border-radius: 2px; font-family: 'JetBrains Mono', monospace; font-size: 0.55rem; font-weight: 600; line-height: 1; text-transform: uppercase; flex-shrink: 0; min-width: 28px; }
.file-tag.pdf { background: #f2e6e6; color: #a65a5a; }
.file-tag.txt { background: #f0f0f0; color: #757575; }
.file-tag.other { background: #f3f4f6; color: #6b7280; }
.file-name { font-family: 'Inter', sans-serif; font-size: 0.7rem; color: #4b5563; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.files-empty { display: flex; align-items: center; justify-content: center; gap: 8px; height: 48px; color: #9CA3AF; }
.empty-file-icon { font-size: 1rem; opacity: 0.5; }
.empty-file-text { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; letter-spacing: 0.5px; }
.project-card:hover .card-files-wrapper { border-color: #d1d5db; background: linear-gradient(135deg, #fff 0%, #f8f9fa 100%); }
.corner-mark.top-left-only { position: absolute; top: 6px; left: 6px; width: 8px; height: 8px; border-top: 1.5px solid rgba(0,0,0,0.4); border-left: 1.5px solid rgba(0,0,0,0.4); pointer-events: none; z-index: 10; }
.card-title { font-family: 'Inter', sans-serif; font-size: 0.9rem; font-weight: 700; color: #111827; margin: 0 0 6px 0; line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: color 0.3s ease; }
.project-card:hover .card-title { color: #FF4500; }
.card-desc { font-family: 'Inter', sans-serif; font-size: 0.75rem; color: #6B7280; margin: 0 0 16px 0; line-height: 1.5; height: 34px; overflow: hidden; }
.card-footer { position: relative; display: flex; justify-content: space-between; align-items: center; padding-top: 12px; border-top: 1px solid #F3F4F6; font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: #9CA3AF; font-weight: 500; }
.card-datetime { display: flex; align-items: center; gap: 8px; }
.card-progress { display: flex; align-items: center; gap: 6px; letter-spacing: 0.5px; font-weight: 600; font-size: 0.65rem; }
.status-dot { font-size: 0.5rem; }
.card-progress.completed { color: #10B981; }
.card-progress.in-progress { color: #F59E0B; }
.card-progress.not-started { color: #9CA3AF; }
.card-bottom-line { position: absolute; bottom: 0; left: 0; height: 2px; width: 0; background-color: #000; transition: width 0.5s cubic-bezier(0.23,1,0.32,1); z-index: 20; }
.project-card:hover .card-bottom-line { width: 100%; }
.loading-state { display: flex; flex-direction: column; align-items: center; gap: 14px; padding: 48px; color: #9CA3AF; }
.loading-spinner { width: 24px; height: 24px; border: 2px solid #E5E7EB; border-top-color: #6B7280; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1200px) { .project-card { width: 240px; } }
@media (max-width: 768px) { .cards-container { padding: 0 20px; } .project-card { width: 200px; } }
</style>
