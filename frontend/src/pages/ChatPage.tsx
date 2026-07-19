import { ArrowUp } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { MessageBubble } from "@/pages/chat/MessageBubble"
import { useChat } from "@/pages/chat/hooks/use-chat"

export default function ChatPage() {
  const { messages, sendMessage, isStreaming } = useChat()
  const [input, setInput] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  const submit = () => {
    const text = input.trim()
    if (!text || isStreaming) return
    setInput("")
    void sendMessage(text)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
            <h1 className="text-xl font-semibold">Chat</h1>
            <p className="text-muted-foreground">Ask Sabio about Bitcoin protocol development.</p>
          </div>
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-6">
            {messages.map((message, i) => (
              <MessageBubble key={i} message={message} />
            ))}
          </div>
        )}
      </div>

      <div className="border-t px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                submit()
              }
            }}
            placeholder="Message Sabio…"
            rows={1}
            className="max-h-40 min-h-9 flex-1 resize-none rounded-lg border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <Button size="icon" onClick={submit} disabled={!input.trim() || isStreaming}>
            <ArrowUp className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
