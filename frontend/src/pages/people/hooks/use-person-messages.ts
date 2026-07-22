import { useQueries, useQuery } from "@tanstack/react-query"

export type PersonMessage = {
  id: number
  channel: string
  title: string | null
  author: string | null
  posted_at: string | null
  url: string
  snippet: string | null
}

type PersonMessagesResponse = {
  page: number
  page_size: number
  total: number
  messages: PersonMessage[]
}

export type PersonMessageFilters = {
  q?: string
  channel?: string
}

async function fetchPersonMessages(
  id: string, page: number, filters: PersonMessageFilters,
): Promise<PersonMessagesResponse> {
  const params = new URLSearchParams({ page: String(page) })
  if (filters.q) params.set("q", filters.q)
  if (filters.channel) params.set("channel", filters.channel)
  const res = await fetch(`/people/${id}/messages?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch person messages: ${res.status}`)
  }
  return res.json()
}

function personMessagesQuery(id: string, page: number, filters: PersonMessageFilters) {
  return {
    queryKey: ["person-messages", id, filters.q ?? null, filters.channel ?? null, page],
    queryFn: () => fetchPersonMessages(id, page, filters),
    staleTime: Infinity,
  }
}

export function usePersonMessagePages(id: string, pageCount: number, filters: PersonMessageFilters = {}) {
  return useQueries({
    queries: Array.from({ length: pageCount }, (_, i) => personMessagesQuery(id, i + 1, filters)),
  })
}

export function usePersonMessages(id: string, page: number, filters: PersonMessageFilters = {}) {
  return useQuery(personMessagesQuery(id, page, filters))
}
