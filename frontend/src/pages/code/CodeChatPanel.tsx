import { ArrowUp, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth"
import { cn } from "@/lib/utils"
import { ContextChip } from "@/pages/chat/ContextChip"
import { MessageBubble } from "@/pages/chat/MessageBubble"
import type { ContextItem } from "@/pages/chat/hooks/use-chat"
import { useChat } from "@/pages/chat/hooks/use-chat"
import { FilePickerButton } from "@/pages/code/FilePickerButton"

type CodeChatPanelProps = {
  contextItems: ContextItem[]
  onRemoveContext: (id: string) => void
  onClearContext: () => void
  onClose: () => void
  repoName: string
  browseRef: string
  openPaths: string[]
  onAddFile: (path: string) => void
}

// Its own useChat() session, independent of the main /chat page -- a
// question about the code you're currently looking at doesn't need (or
// want) to share history with a general conversation elsewhere in the app.
export function CodeChatPanel({
  contextItems,
  onRemoveContext,
  onClearContext,
  onClose,
  repoName,
  browseRef,
  openPaths,
  onAddFile,
}: CodeChatPanelProps) {
  const { pubkey, login } = useAuth()
  const { messages, sendMessage, isStreaming } = useChat(pubkey, false)
  const [input, setInput] = useState("")
  const [authError, setAuthError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  const hasPendingContext = contextItems.some((c) => c.loading)

  const submit = () => {
    const text = input.trim()
    // A message needs either real text or something attached to be worth
    // sending -- but attaching a range and hitting send with no question
    // typed is a real flow ("explain this"), not an empty submission.
    // hasPendingContext: a file's content may still be in flight (see
    // CodePage's handleAddFile) -- sending before it arrives would attach
    // an empty excerpt instead of what was actually picked.
    if ((!text && contextItems.length === 0) || isStreaming || hasPendingContext) return
    if (!pubkey) {
      setAuthError(null)
      login().catch((err: Error) => setAuthError(err.message))
      return
    }
    setInput("")
    void sendMessage(text || "Explain the attached code.", contextItems)
    onClearContext()
  }

  return (
    <div className="flex h-full flex-col border-l">
      <div className="flex h-9 shrink-0 items-center justify-between border-b px-3 text-xs font-medium text-muted-foreground">
        Ask Sabio
        <button type="button" onClick={onClose} className="rounded p-1 hover:bg-accent hover:text-foreground">
          <X className="size-3.5" />
        </button>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-1.5 p-6 text-center">
            <p className="text-sm text-muted-foreground">
              Ask about this file, or highlight a range and add it below.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-4 p-3">
            {messages.map((message, i) => (
              <MessageBubble key={i} message={message} />
            ))}
          </div>
        )}
      </div>

      <div className="border-t p-3">
        {authError && <p className="mb-2 text-xs text-destructive">{authError}</p>}
        {contextItems.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {contextItems.map((item) => (
              <ContextChip key={item.id} item={item} onRemove={() => onRemoveContext(item.id)} />
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <FilePickerButton
            repoName={repoName}
            browseRef={browseRef}
            openPaths={openPaths}
            onSelectFile={onAddFile}
          />
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                submit()
              }
            }}
            placeholder="Ask about this code…"
            rows={1}
            className="max-h-32 min-h-9 flex-1 resize-none rounded-xl border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-sabio/40 focus-visible:ring-3 focus-visible:ring-sabio/15"
          />
          <Button
            size="icon"
            onClick={submit}
            disabled={(!input.trim() && contextItems.length === 0) || isStreaming || hasPendingContext}
            className={cn("rounded-full", input.trim() && "bg-sabio text-sabio-foreground hover:bg-sabio/90")}
          >
            <ArrowUp className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
