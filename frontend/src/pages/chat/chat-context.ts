import { createContext, useContext } from "react"

import type { useChat } from "@/pages/chat/hooks/use-chat"

export type ChatContextValue = ReturnType<typeof useChat>

export const ChatContext = createContext<ChatContextValue | null>(null)

export function useAppChat(): ChatContextValue {
  const context = useContext(ChatContext)
  if (!context) throw new Error("useAppChat must be used within ChatProvider")
  return context
}
