import { ArrowUp, Loader2, Plus, Square, Trash2 } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { useIsMobile } from "@/hooks/use-mobile"
import { useLocale, type TranslationKey } from "@/lib/i18n"
import { cn } from "@/lib/utils"
import { AttachmentMenu } from "@/pages/chat/AttachmentMenu"
import { ChatAttachment as ChatAttachmentPreview } from "@/pages/chat/ChatAttachment"
import { CommunicationSourcePanel } from "@/pages/chat/CommunicationSourcePanel"
import { MessageBubble } from "@/pages/chat/MessageBubble"
import { SourceCodePanel } from "@/pages/chat/SourceCodePanel"
import { useAppChat } from "@/pages/chat/chat-context"
import type {
  ChatAttachment,
  CommunicationReference,
  SourceReference,
} from "@/pages/chat/hooks/use-chat"

// Grounded in what Sabio can actually do (repos + comms tools) rather than
// generic chatbot filler -- each one maps to a real, answerable query.
const STARTERS = [
  "starterChanges",
  "starterContributors",
  "starterPullRequests",
  "starterDiscussions",
] as const satisfies readonly TranslationKey[]

const ACCEPTED_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
])
const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const MAX_IMAGES = 4
const MAX_ATTACHMENTS = 8

function fileToDataUrl(file: File, errorMessage: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.addEventListener("load", () => resolve(String(reader.result)))
    reader.addEventListener("error", () =>
      reject(reader.error ?? new Error(errorMessage)),
    )
    reader.readAsDataURL(file)
  })
}

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
  const { t } = useLocale()
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
  const [attachments, setAttachments] = useState<ChatAttachment[]>([])
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const [isReadingImages, setIsReadingImages] = useState(false)
  const [isDraggingImages, setIsDraggingImages] = useState(false)
  const [selectedEvidence, setSelectedEvidence] = useState<SelectedEvidence | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const isMobile = useIsMobile()

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  useEffect(() => {
    setSelectedEvidence(null)
    setAttachments([])
    setAttachmentError(null)
  }, [sessionId])

  const openCodeSource = useCallback((source: SourceReference) => {
    setSelectedEvidence({ kind: "code", source })
  }, [])

  const openCommunicationSource = useCallback((source: CommunicationReference) => {
    setSelectedEvidence({ kind: "communication", source })
  }, [])

  const addImages = useCallback(
    async (files: File[]) => {
      const currentImageCount = attachments.filter(
        (attachment) => attachment.kind === "image",
      ).length
      const availableImageSlots = MAX_IMAGES - currentImageCount
      const availableAttachmentSlots = MAX_ATTACHMENTS - attachments.length
      const availableSlots = Math.min(availableImageSlots, availableAttachmentSlots)

      if (availableSlots <= 0) {
        setAttachmentError(
          currentImageCount >= MAX_IMAGES
            ? t("imageLimit", { count: MAX_IMAGES })
            : t("attachmentLimit", { count: MAX_ATTACHMENTS }),
        )
        return
      }

      const images = files.filter((file) => ACCEPTED_IMAGE_TYPES.has(file.type))
      if (images.length !== files.length) {
        setAttachmentError(t("imageTypesError"))
      } else {
        setAttachmentError(null)
      }
      const oversized = images.find((file) => file.size > MAX_IMAGE_BYTES)
      if (oversized) {
        setAttachmentError(t("imageTooLarge", { name: oversized.name }))
        return
      }

      const selected = images.slice(0, availableSlots)
      if (selected.length === 0) return
      if (images.length > availableSlots) {
        setAttachmentError(
          availableSlots === 1
            ? t("attachmentRemaining")
            : t("attachmentsRemaining", { count: availableSlots }),
        )
      }

      setIsReadingImages(true)
      try {
        const nextImages: ChatAttachment[] = await Promise.all(
          selected.map(async (file) => ({
            id: crypto.randomUUID(),
            kind: "image" as const,
            name: file.name,
            mimeType: file.type,
            size: file.size,
            dataUrl: await fileToDataUrl(file, t("imageReadError")),
          })),
        )
        setAttachments((current) => [...current, ...nextImages])
      } catch {
        setAttachmentError(t("imageUnreadable"))
      } finally {
        setIsReadingImages(false)
        if (imageInputRef.current) imageInputRef.current.value = ""
      }
    },
    [attachments, t],
  )

  const submit = (text: string) => {
    const trimmed = text.trim()
    if (
      (!trimmed && attachments.length === 0) ||
      isStreaming ||
      isLoadingHistory ||
      isReadingImages
    ) {
      return
    }
    setInput("")
    const message =
      trimmed ||
      (attachments.some((attachment) => attachment.kind === "image")
        ? t("imageQuestion")
        : t("contextQuestion"))
    const sentAttachments = attachments
    setAttachments([])
    setAttachmentError(null)
    void sendMessage(message, [], sentAttachments)
  }

  let conversationContent: ReactNode
  if (isLoadingHistory && messages.length === 0) {
    conversationContent = (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
    )
  } else if (messages.length === 0) {
    conversationContent = (
      <div className="mx-auto flex h-full max-w-xl flex-col items-center justify-center gap-5 p-6 text-center">
        <div className="space-y-1.5">
          <h1 className="text-xl font-semibold tracking-tight">{t("askSabio")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("chatDescription")}
          </p>
        </div>
        <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
          {STARTERS.map((promptKey) => (
            <button
              key={promptKey}
              type="button"
              onClick={() => submit(t(promptKey))}
              className="rounded-md border px-3 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              {t(promptKey)}
            </button>
          ))}
        </div>
      </div>
    )
  } else {
    conversationContent = (
      <div className="mx-auto flex max-w-3xl flex-col gap-5 px-6 py-6">
        {messages.map((message, index) => (
          <MessageBubble
            key={index}
            message={message}
            onOpenSource={openCodeSource}
            onOpenCommunication={openCommunicationSource}
          />
        ))}
      </div>
    )
  }

  const chatPane = (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <div className="flex h-12 items-center gap-2 border-b px-3 md:hidden">
        <select
          value={sessions.some((session) => session.session_id === sessionId) ? sessionId : ""}
          onChange={(event) => {
            if (event.target.value) void loadSession(event.target.value)
          }}
          disabled={isStreaming || isLoadingHistory}
          aria-label={t("conversation")}
          className="min-w-0 flex-1 truncate rounded-md border bg-background px-2 py-1.5 text-sm"
        >
          <option value="">{t("newConversation")}</option>
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
          aria-label={t("newConversation")}
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
            aria-label={t("deleteConversation")}
            className="text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="size-4" />
          </Button>
        )}
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {conversationContent}
      </div>

      <div className="shrink-0 border-t bg-background px-4 py-4 sm:px-6">
        {(attachmentError || sessionError) && (
          <p className="mx-auto mb-2 max-w-3xl text-sm text-destructive">
            {attachmentError || sessionError}
          </p>
        )}
        <div
          onDragEnter={(event) => {
            if (event.dataTransfer.types.includes("Files")) setIsDraggingImages(true)
          }}
          onDragOver={(event) => {
            if (event.dataTransfer.types.includes("Files")) {
              event.preventDefault()
              event.dataTransfer.dropEffect = "copy"
            }
          }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
              setIsDraggingImages(false)
            }
          }}
          onDrop={(event) => {
            event.preventDefault()
            setIsDraggingImages(false)
            void addImages(Array.from(event.dataTransfer.files))
          }}
          className={cn(
            "relative mx-auto max-w-3xl rounded-xl border bg-card p-2 shadow-sm transition-colors",
            isDraggingImages && "border-sabio bg-sabio/5 ring-3 ring-sabio/15",
          )}
        >
          <input
            ref={imageInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            className="hidden"
            onChange={(event) => void addImages(Array.from(event.target.files ?? []))}
          />
          {attachments.length > 0 && (
            <div className="flex max-h-36 flex-wrap gap-2 overflow-y-auto px-1 pb-2">
              {attachments.map((attachment) => (
                <ChatAttachmentPreview
                  key={attachment.id}
                  attachment={attachment}
                  compact
                  onRemove={() =>
                    setAttachments((current) =>
                      current.filter((item) => item.id !== attachment.id),
                    )
                  }
                />
              ))}
            </div>
          )}
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPaste={(event) => {
              const files = Array.from(event.clipboardData.files)
              if (files.some((file) => file.type.startsWith("image/"))) {
                event.preventDefault()
                void addImages(files)
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                submit(input)
              }
            }}
            placeholder={t("messageSabio")}
            rows={1}
            className="max-h-40 min-h-12 w-full resize-none bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground"
          />
          <div className="flex items-center gap-2">
            <AttachmentMenu
              disabled={isStreaming || isLoadingHistory || isReadingImages}
              attachments={attachments}
              onChooseImages={() => imageInputRef.current?.click()}
              onAdd={(attachment) => {
                if (attachments.length >= MAX_ATTACHMENTS) {
                  setAttachmentError(t("attachmentLimit", { count: MAX_ATTACHMENTS }))
                  return
                }
                setAttachmentError(null)
                setAttachments((current) => [...current, attachment])
              }}
            />
            {isReadingImages && (
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                {t("addingImage")}
              </span>
            )}
            <span className="flex-1" />
            {isStreaming ? (
              <Button
                size="icon"
                onClick={stopStreaming}
                className="rounded-full bg-sabio text-sabio-foreground hover:bg-sabio/90"
                aria-label={t("stopGenerating")}
              >
                <Square className="size-3.5 fill-current" />
              </Button>
            ) : (
              <Button
                size="icon"
                onClick={() => submit(input)}
                disabled={
                  (!input.trim() && attachments.length === 0) ||
                  isLoadingHistory ||
                  isReadingImages
                }
                className={cn(
                  "rounded-full",
                  (input.trim() || attachments.length > 0) &&
                    "bg-sabio text-sabio-foreground hover:bg-sabio/90",
                )}
                aria-label={t("sendMessage")}
              >
                <ArrowUp className="size-4" />
              </Button>
            )}
          </div>
          {isDraggingImages && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-xl bg-background/90 text-sm font-medium text-sabio">
              {t("dropImages")}
            </div>
          )}
        </div>
        <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted-foreground">
          {t("disclaimer")}
        </p>
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
            <SheetTitle className="sr-only">{t("referencedEvidence")}</SheetTitle>
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
