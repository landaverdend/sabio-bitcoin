import { Code2, ExternalLink, Loader2, MessageSquareQuote } from "lucide-react"

import { Markdown } from "@/components/Markdown"
import { channelLabel } from "@/lib/channels"
import { formatRelativeDate } from "@/lib/format-date"
import { cn } from "@/lib/utils"
import { ContextChip } from "@/pages/chat/ContextChip"
import type {
  ChatBlock,
  ChatMessage,
  CommunicationReference,
  SourceReference,
} from "@/pages/chat/hooks/use-chat"

// Small quiet monogram rather than a bot-in-a-circle icon -- Sabio is meant
// to read as one collaborator with a consistent mark, not a generic
// assistant avatar.
function SabioMark() {
  return (
    <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-sabio/25 bg-sabio/10 text-[11px] font-semibold text-sabio">
      S
    </span>
  )
}

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
          title={`Open ${source.path} at ${lines}`}
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
        aria-label={`Open ${source.path} on GitHub`}
        title="Open on GitHub"
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
  const content = (
    <>
      <MessageSquareQuote className="mt-0.5 size-3.5 shrink-0 text-sabio" />
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="truncate font-medium text-foreground">
            {source.author || "Unknown author"}
          </span>
          <span className="shrink-0 text-muted-foreground">
            · {channelLabel(source.channel)} · {formatRelativeDate(source.postedAt)}
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
          title="Open archived message"
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
        aria-label="Open original communication source"
        title="Open original source"
        className="flex shrink-0 items-center border-l px-2 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <ExternalLink className="size-3.5" />
      </a>
    </div>
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
    return (
      <div className="flex flex-col items-end gap-1.5">
        <p className="max-w-xl rounded-2xl bg-primary px-4 py-2.5 text-sm whitespace-pre-wrap text-primary-foreground">
          {message.text}
        </p>
        {message.context && message.context.length > 0 && (
          <div className="flex max-w-xl flex-wrap justify-end gap-1.5">
            {message.context.map((item) => (
              <ContextChip key={item.id} item={item} tone="on-page" />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex max-w-2xl items-start gap-3">
      <SabioMark />
      <div className="min-w-0 flex-1 space-y-2 pt-0.5">
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
          return <ToolChip key={i} block={block} />
        })}
      </div>
    </div>
  )
}
