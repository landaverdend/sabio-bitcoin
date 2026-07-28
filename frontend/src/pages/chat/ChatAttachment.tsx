import { GitBranch, UserRound, X } from "lucide-react"

import { useLocale } from "@/lib/i18n"
import { cn } from "@/lib/utils"
import type { ChatAttachment as ChatAttachmentValue } from "@/pages/chat/hooks/use-chat"

function EntityAttachment({
  attachment,
  onRemove,
}: {
  attachment: Exclude<ChatAttachmentValue, { kind: "image" }>
  onRemove?: () => void
}) {
  const { t } = useLocale()
  const Icon = attachment.kind === "repository" ? GitBranch : UserRound
  const detail =
    attachment.kind === "repository"
      ? t("repository")
      : attachment.githubUsername
        ? `@${attachment.githubUsername}`
        : t("person")

  return (
    <span className="inline-flex max-w-56 items-center gap-2 rounded-lg border bg-muted/40 px-2.5 py-1.5 text-xs">
      <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-background">
        <Icon className="size-3.5 text-sabio" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">{attachment.label}</span>
        <span className="block truncate text-muted-foreground">{detail}</span>
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="shrink-0 rounded-full p-0.5 text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
          aria-label={t("removeItem", { name: attachment.label })}
        >
          <X className="size-3" />
        </button>
      )}
    </span>
  )
}

function ImageAttachment({
  attachment,
  onRemove,
  compact,
}: {
  attachment: Extract<ChatAttachmentValue, { kind: "image" }>
  onRemove?: () => void
  compact?: boolean
}) {
  const { t } = useLocale()
  return (
    <span
      className={cn(
        "group relative block overflow-hidden rounded-xl border bg-muted",
        compact ? "size-16" : "h-40 w-56 max-w-full",
      )}
    >
      <img
        src={attachment.dataUrl}
        alt={attachment.name}
        className="size-full object-cover"
      />
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="absolute right-1.5 top-1.5 rounded-full bg-background/90 p-1 text-foreground shadow-sm hover:bg-background"
          aria-label={t("removeItem", { name: attachment.name })}
        >
          <X className="size-3.5" />
        </button>
      )}
    </span>
  )
}

export function ChatAttachment({
  attachment,
  onRemove,
  compact = false,
}: {
  attachment: ChatAttachmentValue
  onRemove?: () => void
  compact?: boolean
}) {
  if (attachment.kind === "image") {
    return <ImageAttachment attachment={attachment} onRemove={onRemove} compact={compact} />
  }
  return <EntityAttachment attachment={attachment} onRemove={onRemove} />
}
