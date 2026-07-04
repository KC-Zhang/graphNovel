import { createI18n } from 'vue-i18n'
import languages from '../../../locales/languages.json'

const localeFiles = import.meta.glob('../../../locales/!(languages).json', { eager: true })

const messages = {}
const availableLocales = []

for (const path in localeFiles) {
  const key = path.match(/\/([^/]+)\.json$/)[1]
  if (languages[key]) {
    messages[key] = localeFiles[path].default
    availableLocales.push({ key, label: languages[key].label })
  }
}

const fallbackLocale = 'zh'

const normalizeLocale = value => String(value || '').trim().toLowerCase().replace('_', '-')

const matchAvailableLocale = value => {
  const normalized = normalizeLocale(value)
  if (!normalized) return ''

  const availableKeys = Object.keys(messages)
  const exactMatch = availableKeys.find(key => normalizeLocale(key) === normalized)
  if (exactMatch) return exactMatch

  const baseLanguage = normalized.split('-')[0]
  return availableKeys.find(key => normalizeLocale(key) === baseLanguage) || ''
}

const getBrowserLocale = () => {
  if (typeof navigator === 'undefined') return ''

  const browserLocales = Array.isArray(navigator.languages) && navigator.languages.length
    ? navigator.languages
    : [navigator.language]

  return browserLocales.map(matchAvailableLocale).find(Boolean) || ''
}

const getInitialLocale = () => {
  const savedLocale = localStorage.getItem('locale')
  return matchAvailableLocale(savedLocale) || getBrowserLocale() || fallbackLocale
}

const initialLocale = getInitialLocale()
document.documentElement.lang = initialLocale

const i18n = createI18n({
  legacy: false,
  locale: initialLocale,
  fallbackLocale,
  messages
})

export { availableLocales }
export default i18n
