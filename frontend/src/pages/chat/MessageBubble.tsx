import {
  Code2,
  ExternalLink,
  GitPullRequest,
  Globe2,
  Loader2,
  MessageSquareQuote,
} from "lucide-react"

import { Markdown } from "@/components/Markdown"
import { channelLabel } from "@/lib/channels"
import { formatRelativeDate } from "@/lib/format-date"
import { useLocale } from "@/lib/i18n"
import { cn } from "@/lib/utils"
import { ChatAttachment } from "@/pages/chat/ChatAttachment"
import { ContextChip } from "@/pages/chat/ContextChip"
import type {
  ChatBlock,
  ChatMessage,
  CommunicationReference,
  GitHubDiscussionReference,
  SourceReference,
  WebReference,
} from "@/pages/chat/hooks/use-chat"

function ThinkingDots() {
  return (
    <span className="flex items-center gap-0.5 py-1.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="size-1.5 rounded-full bg-muted-foreground/50 [animation:pulse_1.2s_ease-in-out_infinite]"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
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

export function MessageBubble({
  message,
  onOpenSource,
  onOpenCommunication,
}: {
  message: ChatMessage
  onOpenSource?: (source: SourceReference) => void
  onOpenCommunication?: (source: CommunicationReference) => void
}) {
  if (message.role === "user") {
    const images = message.attachments?.filter((attachment) => attachment.kind === "image") ?? []
    const references =
      message.attachments?.filter((attachment) => attachment.kind !== "image") ?? []

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
        {((message.context && message.context.length > 0) || references.length > 0) && (
          <div className="flex max-w-xl flex-wrap justify-end gap-1.5">
            {message.context?.map((item) => (
              <ContextChip key={item.id} item={item} tone="on-page" />
            ))}
            {references.map((attachment) => (
              <ChatAttachment key={attachment.id} attachment={attachment} compact />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="max-w-2xl space-y-2">
      {message.blocks.length === 0 && <ThinkingDots />}
      {message.blocks.map((block, i) => {
        if (block.type === "text") {
          return (
            <Markdown key={i} className="[&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              {block.text}
            </Markdown>
          )
        }
        if (block.type === "source") {
          return <SourceChip key={i} source={block.source} onOpen={onOpenSource} />
        }
        if (block.type === "communication_source") {
          return (
            <CommunicationSourceChip
              key={i}
              source={block.source}
              onOpen={onOpenCommunication}
            />
          )
        }
        if (block.type === "github_discussion_source") {
          return <GitHubDiscussionSourceChip key={i} source={block.source} />
        }
        if (block.type === "web_source") {
          return <WebSourceChip key={i} source={block.source} />
        }
        return <ToolChip key={i} block={block} />
      })}
    </div>
  )
}
