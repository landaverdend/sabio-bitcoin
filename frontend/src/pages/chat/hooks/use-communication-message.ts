import { useQuery } from "@tanstack/react-query"

export type CommunicationMessage = {
  id: number
  channel: string
  external_id: string
  author: string | null
  email: string | null
  title: string | null
  body: string
  url: string
  posted_at: string | null
  thread_id: string | null
  person_id: number | null
}

async function fetchCommunicationMessage(messageId: string): Promise<CommunicationMessage> {
  const res = await fetch(`/comms/messages/${encodeURIComponent(messageId)}`, {
    credentials: "include",
  })
  if (!res.ok) {
    throw new Error(`failed to fetch archived message: ${res.status}`)
  }
  return res.json()
}

export function useCommunicationMessage(messageId: string) {
  return useQuery({
    queryKey: ["communication-message", messageId],
    queryFn: () => fetchCommunicationMessage(messageId),
    staleTime: Infinity,
  })
}
