import ReactMarkdown from "react-markdown"
import rehypeSanitize from "rehype-sanitize"
import remarkBreaks from "remark-breaks"
import remarkGfm from "remark-gfm"

import { cn } from "@/lib/utils"

type MarkdownProps = {
  children: string
  className?: string
}

// Shared renderer for markdown coming from outside the app -- commit
// messages, chat responses, BitcoinTalk/mailing-list posts. rehype-sanitize
// strips scripts/event handlers/etc since none of that content is trusted.
export function Markdown({ children, className }: MarkdownProps) {
  return (
    <div
      className={cn(
        "prose prose-sm dark:prose-invert max-w-none",
        "prose-pre:bg-muted/40 prose-pre:border",
        "prose-code:before:content-none prose-code:after:content-none prose-code:bg-muted prose-code:rounded prose-code:px-1 prose-code:py-0.5 prose-code:font-normal",
        className,
      )}
    >
      <ReactMarkdown
        // remark-breaks: commit messages/forum posts routinely use manual
        // line breaks (indented ACK lists, quoted replies) without blank
        // lines between them -- plain CommonMark would reflow those into
        // one run-on paragraph, which is worse than the raw text was.
        remarkPlugins={[remarkGfm, remarkBreaks]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a: ({ ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
