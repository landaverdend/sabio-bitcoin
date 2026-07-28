import { useQuery } from "@tanstack/react-query"

import { getAnonId } from "@/lib/anon-id"

export type CommunicationMessage = {
  id: number | string
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
  const path = messageId.startsWith("irc_event:")
    ? `/irc/events/${encodeURIComponent(messageId)}`
    : `/comms/messages/${encodeURIComponent(messageId)}`
  const res = await fetch(path, {
    credentials: "include",
    headers: { "X-Anon-Id": getAnonId() },
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
