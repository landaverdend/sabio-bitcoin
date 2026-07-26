import { ArrowUp, Loader2, Plus, Square, Trash2 } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { useIsMobile } from "@/hooks/use-mobile"
import { useAuth } from "@/lib/auth"
import { cn } from "@/lib/utils"
import { CommunicationSourcePanel } from "@/pages/chat/CommunicationSourcePanel"
import { MessageBubble } from "@/pages/chat/MessageBubble"
import { SourceCodePanel } from "@/pages/chat/SourceCodePanel"
import { useAppChat } from "@/pages/chat/chat-context"
import type {
  CommunicationReference,
  SourceReference,
} from "@/pages/chat/hooks/use-chat"

// Grounded in what Sabio can actually do (repos + comms tools) rather than
// generic chatbot filler -- each one maps to a real, answerable query.
const STARTERS = [
  "What changed in the last week of commits?",
  "Who are the most active contributors right now?",
  "Any open PRs worth a look?",
  "What's being discussed on the mailing list lately?",
]

type SelectedEvidence =
  | { kind: "code"; source: SourceReference }
  | { kind: "communication"; source: CommunicationReference }

function EvidencePanel({
  selected,
  onClose,
}: {
  selected: SelectedEvidence
  onClose: () => void
}) {
  if (selected.kind === "code") {
    return <SourceCodePanel source={selected.source} onClose={onClose} />
  }
  return <CommunicationSourcePanel source={selected.source} onClose={onClose} />
}

export default function ChatPage() {
  const { pubkey, login } = useAuth()
  const {
    sessionId,
    sessions,
    messages,
    sendMessage,
    stopStreaming,
    isStreaming,
    isLoadingHistory,
    sessionError,
    newSession,
    loadSession,
    deleteSession,
  } = useAppChat()
  const [input, setInput] = useState("")
  const [authError, setAuthError] = useState<string | null>(null)
  const [selectedEvidence, setSelectedEvidence] = useState<SelectedEvidence | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const isMobile = useIsMobile()

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  useEffect(() => {
    setSelectedEvidence(null)
  }, [sessionId])

  const openCodeSource = useCallback((source: SourceReference) => {
    setSelectedEvidence({ kind: "code", source })
  }, [])

  const openCommunicationSource = useCallback((source: CommunicationReference) => {
    setSelectedEvidence({ kind: "communication", source })
  }, [])

  const submit = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming || isLoadingHistory) return
    // Not signed in -- prompt the same Nostr login the sidebar offers
    // instead of letting this hit the chat endpoint's 401 and surface as a
    // generic "something went wrong". Doesn't auto-send afterward; hit send
    // again once connected.
    if (!pubkey) {
      setAuthError(null)
      login().catch((err: Error) => setAuthError(err.message))
      return
    }
    setInput("")
    void sendMessage(trimmed)
  }

  const chatPane = (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <div className="flex h-12 items-center gap-2 border-b px-3 md:hidden">
        <select
          value={sessions.some((session) => session.session_id === sessionId) ? sessionId : ""}
          onChange={(event) => {
            if (event.target.value) void loadSession(event.target.value)
          }}
          disabled={!pubkey || isStreaming || isLoadingHistory}
          aria-label="Conversation"
          className="min-w-0 flex-1 truncate rounded-md border bg-background px-2 py-1.5 text-sm"
        >
          <option value="">New conversation</option>
          {sessions.map((session) => (
            <option key={session.session_id} value={session.session_id}>
              {session.title}
            </option>
          ))}
        </select>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={newSession}
          disabled={isStreaming || isLoadingHistory}
          aria-label="New conversation"
        >
          <Plus className="size-4" />
        </Button>
        {sessions.some((session) => session.session_id === sessionId) && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={() => void deleteSession(sessionId)}
            disabled={isStreaming || isLoadingHistory}
            aria-label="Delete conversation"
            className="text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="size-4" />
          </Button>
        )}
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {isLoadingHistory && messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
          </div>
        ) : messages.length === 0 ? (
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
              <MessageBubble
                key={i}
                message={message}
                onOpenSource={openCodeSource}
                onOpenCommunication={openCommunicationSource}
              />
            ))}
          </div>
        )}
      </div>

      <div className="border-t px-6 py-4">
        {(authError || sessionError) && (
          <p className="mx-auto mb-2 max-w-3xl text-sm text-destructive">
            {authError || sessionError}
          </p>
        )}
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
          {isStreaming ? (
            <Button
              size="icon"
              onClick={stopStreaming}
              className="rounded-full bg-sabio text-sabio-foreground hover:bg-sabio/90"
              aria-label="Stop generating"
            >
              <Square className="size-3.5 fill-current" />
            </Button>
          ) : (
            <Button
              size="icon"
              onClick={() => submit(input)}
              disabled={!input.trim() || isLoadingHistory}
              className={cn(
                "rounded-full",
                input.trim() && "bg-sabio text-sabio-foreground hover:bg-sabio/90",
              )}
            >
              <ArrowUp className="size-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  )

  if (isMobile) {
    return (
      <>
        {chatPane}
        <Sheet
          open={selectedEvidence !== null}
          onOpenChange={(open) => {
            if (!open) setSelectedEvidence(null)
          }}
        >
          <SheetContent
            side="right"
            showCloseButton={false}
            className="w-[96vw] max-w-none gap-0 p-0"
          >
            <SheetTitle className="sr-only">Referenced evidence</SheetTitle>
            {selectedEvidence && (
              <EvidencePanel
                selected={selectedEvidence}
                onClose={() => setSelectedEvidence(null)}
              />
            )}
          </SheetContent>
        </Sheet>
      </>
    )
  }

  return (
    <ResizablePanelGroup orientation="horizontal" className="min-h-0">
      <ResizablePanel id="main-chat" minSize={420}>
        {chatPane}
      </ResizablePanel>
      {selectedEvidence && (
        <>
          <ResizableHandle withHandle />
          <ResizablePanel
            id="chat-evidence"
            defaultSize="44%"
            minSize={360}
            maxSize="65%"
          >
            <EvidencePanel
              selected={selectedEvidence}
              onClose={() => setSelectedEvidence(null)}
            />
          </ResizablePanel>
        </>
      )}
    </ResizablePanelGroup>
  )
}
