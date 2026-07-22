import { useQueries, useQuery } from "@tanstack/react-query"

export type PersonSummary = {
  id: number
  display_name: string | null
  email: string | null
  github_username: string | null
  bitcointalk_username: string | null
  message_count: number
}

type PeopleResponse = {
  page: number
  page_size: number
  total: number
  people: PersonSummary[]
}

async function fetchPeople(page: number, q: string | undefined): Promise<PeopleResponse> {
  const params = new URLSearchParams({ page: String(page) })
  if (q) params.set("q", q)
  const res = await fetch(`/people?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch people: ${res.status}`)
  }
  return res.json()
}

function peopleQuery(page: number, q: string | undefined) {
  return {
    queryKey: ["people", q ?? null, page],
    queryFn: () => fetchPeople(page, q),
    staleTime: Infinity,
  }
}

/** Pages 1..pageCount, fetched in parallel and already-fetched pages served
 * from cache -- same "load more" shape as useRepoCommitPages. */
export function usePeoplePages(pageCount: number, q: string | undefined = undefined) {
  return useQueries({
    queries: Array.from({ length: pageCount }, (_, i) => peopleQuery(i + 1, q)),
  })
}

export function usePeople(page: number, q: string | undefined = undefined) {
  return useQuery(peopleQuery(page, q))
}
