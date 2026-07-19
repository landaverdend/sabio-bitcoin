import { Loader2, Wrench } from "lucide-react"

import { Markdown } from "@/components/Markdown"
import { cn } from "@/lib/utils"
import type { ChatMessage } from "@/pages/chat/hooks/use-chat"

export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-xl rounded-lg bg-primary px-4 py-2.5 text-sm whitespace-pre-wrap text-primary-foreground">
          {message.text}
        </p>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-2xl rounded-lg bg-muted px-4 py-2.5">
        {message.blocks.length === 0 && (
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        )}
        {message.blocks.map((block, i) =>
          block.type === "text" ? (
            <Markdown key={i} className="[&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              {block.text}
            </Markdown>
          ) : (
            <div
              key={i}
              className={cn(
                "mb-2 flex items-center gap-1.5 text-xs text-muted-foreground last:mb-0",
                !block.done && "animate-pulse",
              )}
            >
              {block.done ? <Wrench className="size-3" /> : <Loader2 className="size-3 animate-spin" />}
              {block.label}
            </div>
          ),
        )}
      </div>
    </div>
  )
}
