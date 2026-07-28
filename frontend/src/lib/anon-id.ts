// A per-browser id for chat without a Nostr login -- generated once and
// persisted in localStorage, sent as X-Anon-Id so the backend has a stable
// user_id to scope anonymous sessions by (see backend/auth.py).
const STORAGE_KEY = "sabio_anon_id"

export function getAnonId(): string {
  const existing = localStorage.getItem(STORAGE_KEY)
  if (existing) return existing

  const created = crypto.randomUUID()
  localStorage.setItem(STORAGE_KEY, created)
  return created
}
