import {
  ChevronLeft,
  ChevronRight,
  Code2,
  ExternalLink,
  GitPullRequest,
  Globe2,
  Loader2,
  MessageSquareQuote,
} from "lucide-react"
import { useState } from "react"

import { Markdown } from "@/components/Markdown"
import { channelLabel } from "@/lib/channels"
import { formatRelativeDate } from "@/lib/format-date"
import { useLocale } from "@/lib/i18n"
import { cn } from "@/lib/utils"
import { ChatAttachment } from "@/pages/chat/ChatAttachment"
import { ContextChip } from "@/pages/chat/ContextChip"
import type {
  ChatBlock,
  ChatAttachment as ChatAttachmentValue,
  ChatMessage,
  CommunicationReference,
  ContextItem,
  GitHubDiscussionReference,
  SourceReference,
  WebReference,
} from "@/pages/chat/hooks/use-chat"

const REFERENCES_PER_PAGE = 5

type ReferenceBlock = Extract<
  ChatBlock,
  {
    type:
      | "source"
      | "communication_source"
      | "github_discussion_source"
      | "web_source"
  }
>

type UserReference =
  | { key: string; type: "context"; item: ContextItem }
  | {
      key: string
      type: "attachment"
      attachment: Exclude<ChatAttachmentValue, { kind: "image" }>
    }

function StreamStatus() {
  const { t } = useLocale()

  return (
    <span
      role="status"
      aria-live="polite"
      className="flex w-fit items-center gap-1.5 py-1 text-xs text-muted-foreground"
    >
      <Loader2 className="size-3.5 animate-spin text-sabio" />
      {t("stillResearching")}
    </span>
  )
}

function isReferenceBlock(block: ChatBlock): block is ReferenceBlock {
  return (
    block.type === "source" ||
    block.type === "communication_source" ||
    block.type === "github_discussion_source" ||
    block.type === "web_source"
  )
}

function paginationWindow(itemCount: number, requestedPage: number) {
  const pageCount = Math.max(1, Math.ceil(itemCount / REFERENCES_PER_PAGE))
  const page = Math.min(requestedPage, pageCount - 1)
  const start = page * REFERENCES_PER_PAGE
  const end = Math.min(start + REFERENCES_PER_PAGE, itemCount)
  return { page, pageCount, start, end }
}

function ReferencePagination({
  itemCount,
  requestedPage,
  onPageChange,
}: {
  itemCount: number
  requestedPage: number
  onPageChange: (page: number) => void
}) {
  const { t } = useLocale()
  if (itemCount <= REFERENCES_PER_PAGE) return null

  const { page, pageCount, start, end } = paginationWindow(itemCount, requestedPage)
  return (
    <nav
      className="flex items-center justify-end gap-1.5 pt-0.5 text-xs text-muted-foreground"
      aria-label={t("referencedEvidence")}
    >
      <span className="mr-1 tabular-nums">
        {t("referencesRange", { start: start + 1, end, total: itemCount })}
      </span>
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page === 0}
        aria-label={t("previousReferences")}
        className="rounded-md border p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
      >
        <ChevronLeft className="size-3.5" />
      </button>
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page === pageCount - 1}
        aria-label={t("nextReferences")}
        className="rounded-md border p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
      >
        <ChevronRight className="size-3.5" />
      </button>
    </nav>
  )
}

// One row per tool, not one per call -- a repo-scoped tool (get_commits,
// get_open_prs, ...) fires once for each configured repo, and a wall of
// identical rows animating together reads as noise. Collapsed into a single
// row whose suffix does double duty: a live "n/total" progress count while
// any call is still in flight, replaced by what was actually checked (e.g.
// "core, knots") once everything settles -- so the count isn't just a
// number, it's the answer to "checked where, exactly?".
function ToolChip({ block }: { block: Extract<ChatBlock, { type: "tool" }> }) {
  const total = block.calls.length
  const doneCalls = block.calls.filter((c) => c.done)
  const allDone = doneCalls.length === total
  const details = doneCalls.map((c) => c.detail).filter((d): d is string => !!d)

  let suffix: string | null = null
  if (total > 1) {
    suffix = allDone && details.length === total ? details.join(", ") : `${doneCalls.length}/${total}`
  }

  return (
    <div
      className={cn(
        "flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
        allDone ? "border-border text-muted-foreground" : "border-sabio/30 bg-sabio/10 text-sabio",
      )}
    >
      {allDone ? <block.icon className="size-3" /> : <Loader2 className="size-3 animate-spin" />}
      {block.label}
      {suffix && <span className={allDone ? "text-muted-foreground/70" : "text-sabio/70"}>· {suffix}</span>}
    </div>
  )
}

function SourceChip({
  source,
  onOpen,
}: {
  source: SourceReference
  onOpen?: (source: SourceReference) => void
}) {
  const { t } = useLocale()
  const lines =
    source.startLine === source.endLine
      ? `L${source.startLine}`
      : `L${source.startLine}–${source.endLine}`

  const content = (
    <>
      <Code2 className="size-3.5 shrink-0 text-sabio" />
      <span className="min-w-0 flex-1 truncate">
        <span className="font-medium text-foreground">{source.path}</span>
        <span className="ml-1.5 text-muted-foreground">{lines}</span>
      </span>
    </>
  )

  return (
    <div className="flex max-w-full items-stretch overflow-hidden rounded-lg border bg-muted/20 text-xs">
      {onOpen ? (
        <button
          type="button"
          onClick={() => onOpen(source)}
          className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2 text-left hover:bg-accent"
          title={t("openPathAtLines", { path: source.path, lines })}
        >
          {content}
        </button>
      ) : (
        <a
          href={source.githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2 hover:bg-accent"
        >
          {content}
        </a>
      )}
      <a
        href={source.githubUrl}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={t("openPathOnGitHub", { path: source.path })}
        title={t("openOnGitHub")}
        className="flex shrink-0 items-center border-l px-2 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <ExternalLink className="size-3.5" />
      </a>
    </div>
  )
}

function CommunicationSourceChip({
  source,
  onOpen,
}: {
  source: CommunicationReference
  onOpen?: (source: CommunicationReference) => void
}) {
  const { locale, t } = useLocale()
  const content = (
    <>
      <MessageSquareQuote className="mt-0.5 size-3.5 shrink-0 text-sabio" />
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="truncate font-medium text-foreground">
            {source.author || t("unknownAuthor")}
          </span>
          <span className="shrink-0 text-muted-foreground">
            · {channelLabel(source.channel, locale)} ·{" "}
            {formatRelativeDate(source.postedAt, locale)}
          </span>
        </span>
        {source.title && (
          <span className="mt-0.5 block truncate text-muted-foreground">
            {source.title}
          </span>
        )}
        <span className="mt-1 line-clamp-2 block text-muted-foreground">
          “{source.excerpt}”
        </span>
      </span>
    </>
  )

  return (
    <div className="flex max-w-full items-stretch overflow-hidden rounded-lg border bg-muted/20 text-xs">
      {onOpen ? (
        <button
          type="button"
          onClick={() => onOpen(source)}
          className="flex min-w-0 flex-1 items-start gap-2 px-2.5 py-2 text-left hover:bg-accent"
          title={t("openArchivedMessage")}
        >
          {content}
        </button>
      ) : (
        <a
          href={source.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex min-w-0 flex-1 items-start gap-2 px-2.5 py-2 hover:bg-accent"
        >
          {content}
        </a>
      )}
      <a
        href={source.sourceUrl}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={t("openOriginalSource")}
        title={t("openOriginalSource")}
        className="flex shrink-0 items-center border-l px-2 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <ExternalLink className="size-3.5" />
      </a>
    </div>
  )
}

function WebSourceChip({ source }: { source: WebReference }) {
  const { t } = useLocale()
  let hostname = source.sourceUrl
  try {
    hostname = new URL(source.sourceUrl).hostname.replace(/^www\./, "")
  } catch {
    // The backend only emits validated HTTP(S) URLs. Keep the full URL as a
    // defensive display fallback if an old persisted event is malformed.
  }

  return (
    <a
      href={source.sourceUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="flex max-w-full items-center gap-2 rounded-lg border bg-muted/20 px-2.5 py-2 text-xs hover:bg-accent"
      title={t("openSourceOn", { host: hostname })}
    >
      <Globe2 className="size-3.5 shrink-0 text-sabio" />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">{source.title}</span>
        <span className="block truncate text-muted-foreground">{hostname}</span>
      </span>
      <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" />
    </a>
  )
}

function GitHubDiscussionSourceChip({
  source,
}: {
  source: GitHubDiscussionReference
}) {
  const { locale, t } = useLocale()
  const location =
    source.path && source.line
      ? `${source.path}:L${source.line}`
      : source.path

  return (
    <a
      href={source.sourceUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="flex max-w-full items-start gap-2 rounded-lg border bg-muted/20 px-2.5 py-2 text-xs hover:bg-accent"
      title={t("openOnGitHub")}
    >
      <GitPullRequest className="mt-0.5 size-3.5 shrink-0 text-sabio" />
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="truncate font-medium text-foreground">
            {source.author || t("unknownAuthor")}
          </span>
          <span className="shrink-0 text-muted-foreground">
            · {source.repo}#{source.prNumber} ·{" "}
            {formatRelativeDate(source.createdAt, locale)}
          </span>
        </span>
        {source.prTitle && (
          <span className="mt-0.5 block truncate text-muted-foreground">
            {source.prTitle}
          </span>
        )}
        {location && (
          <span className="mt-0.5 block truncate font-mono text-muted-foreground">
            {location}
          </span>
        )}
        <span className="mt-1 line-clamp-2 block text-muted-foreground">
          “{source.excerpt}”
        </span>
      </span>
      <ExternalLink className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
    </a>
  )
}

function UserMessageBubble({
  message,
}: {
  message: Extract<ChatMessage, { role: "user" }>
}) {
  const [requestedPage, setRequestedPage] = useState(0)
  const images = message.attachments?.filter((attachment) => attachment.kind === "image") ?? []
  const entityAttachments =
    message.attachments?.filter((attachment) => attachment.kind !== "image") ?? []
  const references: UserReference[] = []

  for (const item of message.context ?? []) {
    references.push({ key: `context:${item.id}`, type: "context", item })
  }
  for (const attachment of entityAttachments) {
    references.push({
      key: `attachment:${attachment.id}`,
      type: "attachment",
      attachment,
    })
  }

  const { start, end } = paginationWindow(references.length, requestedPage)
  const visibleReferences = references.slice(start, end)

  return (
    <div className="flex flex-col items-end gap-1.5">
      {images.length > 0 && (
        <div className="flex max-w-xl flex-wrap justify-end gap-2">
          {images.map((attachment) => (
            <ChatAttachment key={attachment.id} attachment={attachment} />
          ))}
        </div>
      )}
      <p className="max-w-xl rounded-2xl bg-primary px-4 py-2.5 text-sm whitespace-pre-wrap text-primary-foreground">
        {message.text}
      </p>
      {references.length > 0 && (
        <div className="max-w-xl">
          <div className="flex flex-wrap justify-end gap-1.5">
            {visibleReferences.map((reference) => {
              if (reference.type === "context") {
                return (
                  <ContextChip
                    key={reference.key}
                    item={reference.item}
                    tone="on-page"
                  />
                )
              }
              return (
                <ChatAttachment
                  key={reference.key}
                  attachment={reference.attachment}
                  compact
                />
              )
            })}
          </div>
          <ReferencePagination
            itemCount={references.length}
            requestedPage={requestedPage}
            onPageChange={setRequestedPage}
          />
        </div>
      )}
    </div>
  )
}

function ChatBlockView({
  block,
  onOpenSource,
  onOpenCommunication,
}: {
  block: ChatBlock
  onOpenSource?: (source: SourceReference) => void
  onOpenCommunication?: (source: CommunicationReference) => void
}) {
  if (block.type === "text") {
    return (
      <Markdown className="[&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
        {block.text}
      </Markdown>
    )
  }
  if (block.type === "source") {
    return <SourceChip source={block.source} onOpen={onOpenSource} />
  }
  if (block.type === "communication_source") {
    return (
      <CommunicationSourceChip
        source={block.source}
        onOpen={onOpenCommunication}
      />
    )
  }
  if (block.type === "github_discussion_source") {
    return <GitHubDiscussionSourceChip source={block.source} />
  }
  if (block.type === "web_source") {
    return <WebSourceChip source={block.source} />
  }
  return <ToolChip block={block} />
}

function AssistantMessageBubble({
  message,
  isStreaming,
  onOpenSource,
  onOpenCommunication,
}: {
  message: Extract<ChatMessage, { role: "assistant" }>
  isStreaming: boolean
  onOpenSource?: (source: SourceReference) => void
  onOpenCommunication?: (source: CommunicationReference) => void
}) {
  const [requestedPage, setRequestedPage] = useState(0)
  const contentBlocks: Array<{ block: ChatBlock; index: number }> = []
  const referenceBlocks: Array<{ block: ReferenceBlock; index: number }> = []

  message.blocks.forEach((block, index) => {
    if (isReferenceBlock(block)) {
      referenceBlocks.push({ block, index })
    } else {
      contentBlocks.push({ block, index })
    }
  })

  const { start, end } = paginationWindow(referenceBlocks.length, requestedPage)
  const visibleReferences = referenceBlocks.slice(start, end)
  const hasPendingToolCalls = contentBlocks.some(
    ({ block }) =>
      block.type === "tool" && block.calls.some((call) => !call.done),
  )
  const showStreamStatus = isStreaming && !hasPendingToolCalls

  return (
    <div className="max-w-2xl space-y-2">
      {contentBlocks.map(({ block, index }) => (
        <ChatBlockView
          key={index}
          block={block}
          onOpenSource={onOpenSource}
          onOpenCommunication={onOpenCommunication}
        />
      ))}
      {visibleReferences.map(({ block, index }) => (
        <ChatBlockView
          key={index}
          block={block}
          onOpenSource={onOpenSource}
          onOpenCommunication={onOpenCommunication}
        />
      ))}
      <ReferencePagination
        itemCount={referenceBlocks.length}
        requestedPage={requestedPage}
        onPageChange={setRequestedPage}
      />
      {showStreamStatus && <StreamStatus />}
    </div>
  )
}

export function MessageBubble({
  message,
  isStreaming = false,
  onOpenSource,
  onOpenCommunication,
}: {
  message: ChatMessage
  isStreaming?: boolean
  onOpenSource?: (source: SourceReference) => void
  onOpenCommunication?: (source: CommunicationReference) => void
}) {
  if (message.role === "user") {
    return <UserMessageBubble message={message} />
  }
  return (
    <AssistantMessageBubble
      message={message}
      isStreaming={isStreaming}
      onOpenSource={onOpenSource}
      onOpenCommunication={onOpenCommunication}
    />
  )
}
