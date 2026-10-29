import { computed, onUnmounted, ref, type Ref } from 'vue'
import { useApplicationHost } from '@3mm/application-ui/v1'
import en from './locales/en.json'
import bg from './locales/bg.json'
import { provideLocale, translate, useLocale, type Catalogs } from './locale'
import { domainKeys, stateKeys } from './messages'

// Adding a language requires its catalogue here; Bulgarian is only a reference.
export const catalogs: Catalogs = { en, bg }
function strings(locale: Readonly<Ref<string>>) {
  const t = (key: string) => translate(catalogs, locale.value, key)
  return { t, locale,
    domainMessageKey: (value: unknown) => typeof value === 'string' && Object.hasOwn(domainKeys, value)
      ? domainKeys[value] : typeof value === 'string' && value.startsWith('commerce_') && Object.hasOwn(en,value) ? value : 'request_refused_refresh_the_data',
    stateLabel: (value: string) => Object.hasOwn(stateKeys, value) ? t(stateKeys[value]) : value,
  }
}
export function provideApplicationLocale(input: Readonly<Ref<string | undefined>>) {
  const presentation = useApplicationHost().presentation
  const current = ref(presentation.getInfo().locale)
  const unsubscribe = presentation.subscribe(info => { current.value = info.locale })
  onUnmounted(unsubscribe)
  // The real Core loader supplies the same live prop; standalone host consumers
  // use its public presentation facade. Neither creates an application preference.
  const locale = computed(() => input.value ?? current.value)
  provideLocale(locale)
  return strings(locale)
}
export function useApplicationStrings() { return strings(useLocale()) }
