import { useQuery } from "@tanstack/react-query"
import type { PersonSummary } from "@/pages/people/hooks/use-people"

export type PersonChannel = {
  channel: string
  count: number
}

export type Person = Omit<PersonSummary, "message_count"> & {
  channels: PersonChannel[]
}

async function fetchPerson(id: string): Promise<Person> {
  const res = await fetch(`/people/${id}`)
  if (!res.ok) {
    throw new Error(`failed to fetch person: ${res.status}`)
  }
  return res.json()
}

export function usePerson(id: string) {
  return useQuery({
    queryKey: ["person", id],
    queryFn: () => fetchPerson(id),
    staleTime: Infinity,
  })
}
