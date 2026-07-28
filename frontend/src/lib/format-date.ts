import type { AppLocale } from "@/lib/locale"

export function formatRelativeDate(iso: string | null, locale: AppLocale = "en"): string {
  if (!iso) return locale === "es" ? "fecha desconocida" : "unknown date"
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24))
  if (days < 1) return locale === "es" ? "hoy" : "today"
  if (days === 1) return locale === "es" ? "ayer" : "yesterday"
  if (days < 30) return locale === "es" ? `hace ${days} días` : `${days} days ago`
  const months = Math.floor(days / 30)
  if (months < 12) {
    return locale === "es"
      ? `hace ${months} ${months === 1 ? "mes" : "meses"}`
      : `${months} month${months > 1 ? "s" : ""} ago`
  }
  const years = Math.floor(days / 365)
  return locale === "es"
    ? `hace ${years} ${years === 1 ? "año" : "años"}`
    : `${years} year${years > 1 ? "s" : ""} ago`
}
