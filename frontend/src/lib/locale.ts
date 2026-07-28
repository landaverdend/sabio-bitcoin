export type AppLocale = "en" | "es"

const LOCALE_STORAGE_KEY = "sabio-ui-locale-v1"

function isAppLocale(value: string | null): value is AppLocale {
  return value === "en" || value === "es"
}

export function getAppLocale(): AppLocale {
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY)
    if (isAppLocale(stored)) return stored
  } catch {
    // Storage may be unavailable in privacy-restricted browser contexts.
  }

  if (document.documentElement.lang.toLowerCase().startsWith("es")) return "es"
  return window.navigator.language.toLowerCase().startsWith("es") ? "es" : "en"
}

export function applyAppLocale(locale: AppLocale): void {
  document.documentElement.lang = locale
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch {
    // The in-memory setting still works for the current page.
  }
}
