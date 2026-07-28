import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"

import {
  LocaleContext,
  translate,
  type LocaleContextValue,
  type TranslationKey,
} from "@/lib/i18n"
import { applyAppLocale, getAppLocale, type AppLocale } from "@/lib/locale"

type TranslationValues = Record<string, string | number>

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<AppLocale>(getAppLocale)

  useEffect(() => {
    applyAppLocale(locale)
  }, [locale])

  const t = useCallback(
    (key: TranslationKey, values?: TranslationValues) => translate(locale, key, values),
    [locale],
  )
  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, t }),
    [locale, t],
  )

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}
