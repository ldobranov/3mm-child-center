import { inject, provide, readonly, ref, type InjectionKey, type Ref } from 'vue'

export type Catalogs = Readonly<Record<string, Readonly<Record<string, string>>>>
const localeKey: InjectionKey<Readonly<Ref<string>>> = Symbol('application-locale')

// The owner of this value is the host/preview caller, never an application store.
export function provideLocale(locale: Readonly<Ref<string>>) { provide(localeKey, readonly(locale)) }
export function useLocale(): Readonly<Ref<string>> { return inject(localeKey, ref('en')) }

export function translate(catalogs: Catalogs, locale: string, key: string): string {
  const normalized = locale.trim().replace(/_/g, '-').toLowerCase()
  const candidates = [...new Set([normalized, normalized.split('-')[0], 'en'])]
  for (const language of candidates) {
    if (!Object.hasOwn(catalogs, language)) continue
    const catalog = catalogs[language]
    if (Object.hasOwn(catalog, key) && typeof catalog[key] === 'string' && catalog[key].length) return catalog[key]
  }
  // An absent English source key is an authoring error, not a Bulgarian fallback.
  return key
}
