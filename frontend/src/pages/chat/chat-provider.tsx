import type { ReactNode } from "react"

import { useAuth } from "@/lib/auth"
import { ChatContext } from "@/pages/chat/chat-context"
import { useChat } from "@/pages/chat/hooks/use-chat"

export function ChatProvider({ children }: { children: ReactNode }) {
  const { pubkey } = useAuth()
  const chat = useChat(pubkey)

  return <ChatContext.Provider value={chat}>{children}</ChatContext.Provider>
}
