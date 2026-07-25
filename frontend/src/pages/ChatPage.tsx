import { ArrowUp } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { MessageBubble } from "@/pages/chat/MessageBubble"
import { useChat } from "@/pages/chat/hooks/use-chat"

// Grounded in what Sabio can actually do (repos + comms tools) rather than
// generic chatbot filler -- each one maps to a real, answerable query.
const STARTERS = [
  "What changed in the last week of commits?",
  "Who are the most active contributors right now?",
  "Any open PRs worth a look?",
  "What's being discussed on the mailing list lately?",
]

export default function ChatPage() {
  const { messages, sendMessage, isStreaming } = useChat()
  const [input, setInput] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  const submit = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming) return
    setInput("")
    void sendMessage(trimmed)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="mx-auto flex h-full max-w-xl flex-col items-center justify-center gap-6 p-6 text-center">
            <div className="space-y-1.5">
              <h1 className="text-2xl font-semibold tracking-tight">Ask Sabio</h1>
              <p className="text-muted-foreground">
                Bitcoin protocol intelligence — commits, PRs, and community discussion, in one place.
              </p>
            </div>
            <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
              {STARTERS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => submit(prompt)}
                  className="rounded-xl border px-3.5 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:border-sabio/30 hover:bg-sabio/5 hover:text-foreground"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-5 px-6 py-6">
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
                submit(input)
              }
            }}
            placeholder="Message Sabio…"
            rows={1}
            className="max-h-40 min-h-10 flex-1 resize-none rounded-2xl border bg-transparent px-3.5 py-2.5 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus-visible:border-sabio/40 focus-visible:ring-3 focus-visible:ring-sabio/15"
          />
          <Button
            size="icon"
            onClick={() => submit(input)}
            disabled={!input.trim() || isStreaming}
            className={cn(
              "rounded-full",
              input.trim() && "bg-sabio text-sabio-foreground hover:bg-sabio/90",
            )}
          >
            <ArrowUp className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
