import { ExternalLink, MessageSquareQuote, X } from "lucide-react"

import { Markdown } from "@/components/Markdown"
import { Button } from "@/components/ui/button"
import { channelLabel } from "@/lib/channels"
import type { CommunicationReference } from "@/pages/chat/hooks/use-chat"
import { useCommunicationMessage } from "@/pages/chat/hooks/use-communication-message"

type CommunicationSourcePanelProps = {
  source: CommunicationReference
  onClose: () => void
}

function fullDate(iso: string | null): string {
  if (!iso) return "Unknown date"
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso))
}

export function CommunicationSourcePanel({
  source,
  onClose,
}: CommunicationSourcePanelProps) {
  const message = useCommunicationMessage(source.messageId)

  return (
    <aside className="flex h-full min-h-0 flex-col bg-background">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
        <MessageSquareQuote className="size-4 shrink-0 text-sabio" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium">
            {source.author || "Unknown author"}
          </p>
          <p className="truncate text-[11px] text-muted-foreground">
            {channelLabel(source.channel)} · {fullDate(source.postedAt)}
          </p>
        </div>
        <Button
          render={
            <a
              href={source.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Open original archived message"
              title="Open original source"
            />
          }
          variant="ghost"
          size="icon-sm"
        >
          <ExternalLink className="size-3.5" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onClose}
          aria-label="Close communication source"
        >
          <X className="size-3.5" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {message.isLoading && (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Loading archived message…
          </div>
        )}
        {message.isError && (
          <div className="flex h-full items-center justify-center p-4 text-center text-sm text-destructive">
            Could not load this archived message.
          </div>
        )}
        {message.data && (
          <article className="mx-auto max-w-3xl p-5">
            <div className="mb-5 border-b pb-4">
              <h2 className="text-lg font-semibold">
                {message.data.title || "(no subject)"}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {message.data.author || "Unknown author"}
                {message.data.email ? ` <${message.data.email}>` : ""}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {channelLabel(message.data.channel)} · {fullDate(message.data.posted_at)}
              </p>
            </div>
            <Markdown className="[&>*:first-child]:mt-0">
              {message.data.body}
            </Markdown>
          </article>
        )}
      </div>
    </aside>
  )
}
