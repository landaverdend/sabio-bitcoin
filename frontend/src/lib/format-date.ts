import type { AppLocale } from "@/lib/locale"

export function formatRelativeDate(iso: string | null, locale: AppLocale = "en"): string {
  if (!iso) {
    if (locale === "es") return "fecha desconocida"
    return "unknown date"
  }

  const days = Math.floor((Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24))
  if (locale === "es") {
    if (days < 1) return "hoy"
    if (days === 1) return "ayer"
    if (days < 30) return `hace ${days} días`

    const months = Math.floor(days / 30)
    if (months < 12) {
      const unit = months === 1 ? "mes" : "meses"
      return `hace ${months} ${unit}`
    }

    const years = Math.floor(days / 365)
    const unit = years === 1 ? "año" : "años"
    return `hace ${years} ${unit}`
  }

  if (days < 1) return "today"
  if (days === 1) return "yesterday"
  if (days < 30) return `${days} days ago`

  const months = Math.floor(days / 30)
  if (months < 12) {
    const unit = months === 1 ? "month" : "months"
    return `${months} ${unit} ago`
  }

  const years = Math.floor(days / 365)
  const unit = years === 1 ? "year" : "years"
  return `${years} ${unit} ago`
}
