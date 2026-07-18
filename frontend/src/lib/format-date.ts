export function formatRelativeDate(iso: string | null): string {
  if (!iso) return "unknown date"
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24))
  if (days < 1) return "today"
  if (days === 1) return "yesterday"
  if (days < 30) return `${days} days ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months} month${months > 1 ? "s" : ""} ago`
  const years = Math.floor(days / 365)
  return `${years} year${years > 1 ? "s" : ""} ago`
}
