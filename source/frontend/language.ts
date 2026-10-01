import { computed, readonly, ref } from 'vue'

export type ChildCenterLanguage = 'bg' | 'en'

const LANGUAGE_KEY = 'preferredLanguage'

function normalizeLanguage(value: unknown): ChildCenterLanguage {
  return value === 'bg' ? 'bg' : 'en'
}

const selectedLanguage = ref<ChildCenterLanguage>(
  typeof window === 'undefined' ? 'en' : normalizeLanguage(window.localStorage.getItem(LANGUAGE_KEY)),
)

if (typeof window !== 'undefined') {
  window.addEventListener('language-changed', (event) => {
    const detail = event instanceof CustomEvent ? event.detail : null
    selectedLanguage.value = normalizeLanguage(detail?.language)
  })
}

export function getChildCenterLanguage(): ChildCenterLanguage {
  return selectedLanguage.value
}

export function setChildCenterLanguage(language: ChildCenterLanguage): void {
  selectedLanguage.value = language
  window.localStorage.setItem(LANGUAGE_KEY, language)
  window.dispatchEvent(new CustomEvent('language-changed', { detail: { language } }))
}

export function useChildCenterLanguage() {
  const language = readonly(selectedLanguage)
  const locale = computed(() => selectedLanguage.value === 'bg' ? 'bg-BG' : 'en-GB')
  const t = (bg: string, en: string) => selectedLanguage.value === 'bg' ? bg : en
  const toggleLanguage = () => setChildCenterLanguage(
    selectedLanguage.value === 'bg' ? 'en' : 'bg',
  )
  return { language, locale, t, toggleLanguage }
}
