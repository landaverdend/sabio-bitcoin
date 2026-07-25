import { useQuery } from "@tanstack/react-query"
import type { PersonSummary } from "@/pages/people/hooks/use-people"

export type PersonChannel = {
  channel: string
  count: number
}

export type PersonIdentity = {
  id: number
  display_name: string | null
  email: string | null
  github_username: string | null
  bitcointalk_username: string | null
}

export type Person = Omit<PersonSummary, "message_count" | "linked_count"> & {
  channels: PersonChannel[]
  // Every raw people row folded into this profile, this one included --
  // see backend/people.py's canonical_person_id grouping.
  identities: PersonIdentity[]
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
