import { X } from "lucide-react"

import { useLocale } from "@/lib/i18n"
import { cn } from "@/lib/utils"
import { getFileIcon } from "@/pages/code/file-icons"
import type { ContextItem } from "@/pages/chat/hooks/use-chat"

function basename(path: string): string {
  return path.split("/").pop() ?? path
}

type ContextChipProps = {
  item: ContextItem
  onRemove?: () => void
  /** Read-only chips (inside a sent message) sit on the primary-colored
   * bubble, so they need the inverted, more muted treatment; removable
   * chips (in the composer tray) sit on the page background. */
  tone?: "on-bubble" | "on-page"
}

export function ContextChip({ item, onRemove, tone = "on-page" }: ContextChipProps) {
  const { t } = useLocale()
  const Icon = getFileIcon(basename(item.path))
  const range = item.startLine ? `:${item.startLine}-${item.endLine}` : ""

  return (
    <span
      className={cn(
        "inline-flex max-w-48 items-center gap-1.5 rounded-md border px-2 py-1 text-xs",
        tone === "on-bubble"
          ? "border-primary-foreground/20 bg-primary-foreground/10 text-primary-foreground/90"
          : "border-border bg-muted/40 text-muted-foreground",
      )}
    >
      <Icon className="size-3 shrink-0" />
      <span className="truncate font-mono">
        {basename(item.path)}
        {range}
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={t("removeItem", { name: basename(item.path) })}
          className="ml-0.5 shrink-0 rounded-full p-0.5 hover:bg-foreground/10"
        >
          <X className="size-3" />
        </button>
      )}
    </span>
  )
}
