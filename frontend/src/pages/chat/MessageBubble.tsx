import { Loader2 } from "lucide-react"

import { Markdown } from "@/components/Markdown"
import { cn } from "@/lib/utils"
import type { ChatMessage } from "@/pages/chat/hooks/use-chat"

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

export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-xl rounded-2xl bg-primary px-4 py-2.5 text-sm whitespace-pre-wrap text-primary-foreground">
          {message.text}
        </p>
      </div>
    )
  }

  return (
    <div className="flex max-w-2xl items-start gap-3">
      <SabioMark />
      <div className="min-w-0 flex-1 space-y-2 pt-0.5">
        {message.blocks.length === 0 && <ThinkingDots />}
        {message.blocks.map((block, i) =>
          block.type === "text" ? (
            <Markdown key={i} className="[&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              {block.text}
            </Markdown>
          ) : (
            <div
              key={i}
              className={cn(
                "flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
                block.done
                  ? "border-border text-muted-foreground"
                  : "border-sabio/30 bg-sabio/10 text-sabio",
              )}
            >
              {block.done ? (
                <block.icon className="size-3" />
              ) : (
                <Loader2 className="size-3 animate-spin" />
              )}
              {block.label}
            </div>
          ),
        )}
      </div>
    </div>
  )
}
