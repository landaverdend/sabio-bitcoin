import type { ReactNode } from "react"

import { getAnonId } from "@/lib/anon-id"
import { useAuth } from "@/lib/auth"
import { ChatContext } from "@/pages/chat/chat-context"
import { useChat } from "@/pages/chat/hooks/use-chat"

export function ChatProvider({ children }: { children: ReactNode }) {
  const { pubkey } = useAuth()
  const chat = useChat(pubkey ?? getAnonId())

  return <ChatContext.Provider value={chat}>{children}</ChatContext.Provider>
}
