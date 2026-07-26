import {
  FileText,
  Folder,
  GitCommitHorizontal,
  GitPullRequest,
  MessageSquare,
  Search,
  TicketCheck,
  UserSearch,
  Users,
  type LucideIcon,
} from "lucide-react"
import { useCallback, useState } from "react"

export type ToolCall = { detail?: string; done: boolean }

export type ChatBlock =
  | { type: "text"; text: string }
  | { type: "tool"; tool: string; label: string; icon: LucideIcon; calls: ToolCall[] }

// A file or highlighted excerpt attached from the code panel -- content is
// sent to the backend to be inlined directly into the model's prompt (see
// backend/chat.py's ContextItem/_build_prompt), not just referenced by path,
// so the model is guaranteed to see exactly what was attached.
export type ContextItem = {
  id: string
  path: string
  startLine?: number
  endLine?: number
  content: string
  // A whole-file attach fetches content over the network (~1s to GitHub's
  // API for anything not already cached) -- the chip appears immediately
  // (this flag never affects its rendering, see ContextChip) while the
  // fetch runs behind it, patched in place once the real content arrives.
  // Purely a send-time guard (see CodeChatPanel's hasPendingContext): don't
  // let a message go out with an empty excerpt for something still in
  // flight. A selection excerpt already has its content from the open
  // editor, so it never needs this.
  loading?: boolean
}

export type ChatMessage =
  | { role: "user"; text: string; context?: ContextItem[] }
  | { role: "assistant"; blocks: ChatBlock[] }

// Sabio is presented to the user as a single collaborator, not a router
// dispatching to named sub-agents -- these labels describe what's being
// looked up, never who's looking it up, and the "handoff" events that name
// the internal sub-agents are deliberately never surfaced (see handleEvent
// below).
const TOOL_META: Record<string, { label: string; icon: LucideIcon }> = {
  get_commits: { label: "Looking up commits", icon: GitCommitHorizontal },
  get_open_prs: { label: "Checking open PRs", icon: GitPullRequest },
  get_pr_detail: { label: "Reading a PR", icon: GitPullRequest },
  get_issues: { label: "Checking issues", icon: TicketCheck },
  get_contributor_stats: { label: "Checking contributor stats", icon: Users },
  list_directory: { label: "Browsing files", icon: Folder },
  read_file: { label: "Reading a file", icon: FileText },
  search_code: { label: "Searching code", icon: Search },
  resolve: { label: "Resolving identity", icon: UserSearch },
  get_message: { label: "Reading a message", icon: MessageSquare },
  get_thread: { label: "Reading a thread", icon: MessageSquare },
  // Not "the mailing list" -- search_messages has no channel filter and
  // spans mailing list, its historical precursor lists, and BitcoinTalk in
  // one query, so a channel-specific label here would misrepresent what was
  // actually searched.
  search_messages: { label: "Searching discussions", icon: Search },
}

function toolMeta(tool: string): { label: string; icon: LucideIcon } {
  return TOOL_META[tool] ?? { label: `Using ${tool}`, icon: Search }
}

// Which argument best answers "what specifically did this call do" once a
// tool's repeated calls are grouped into one row (see appendToolCall).
// Repo-scoped tools (get_commits, ...) fire once per configured repo for a
// single question, so repo_name is what varies between those calls --
// content-scoped tools (search_code, resolve, ...) instead fire multiple
// times against the *same* repo/scope with a different query or path each
// time, so repo_name would just repeat the same word once per call (e.g.
// "knots, knots, knots" for a multi-term code search) while the argument
// that actually distinguishes the calls goes unshown.
const DETAIL_ARG: Record<string, string> = {
  get_commits: "repo_name",
  get_open_prs: "repo_name",
  get_pr_detail: "repo_name",
  get_issues: "repo_name",
  get_contributor_stats: "repo_name",
  list_directory: "path",
  read_file: "path",
  search_code: "query",
  resolve: "query",
  get_message: "message_id",
  get_thread: "message_id",
  search_messages: "query",
}

function toolCallDetail(tool: string, args: Record<string, unknown>): string | undefined {
  const value = args[DETAIL_ARG[tool]]
  return typeof value === "string" ? value : undefined
}

type StreamEvent =
  | { type: "text"; author: string; text: string }
  | { type: "handoff"; to: string }
  | { type: "tool_call"; author: string; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; author: string; tool: string }
  | { type: "error"; message: string }
  | { type: "done" }

export function useChat() {
  // Session only needs to survive this tab -- no accounts/persistence yet,
  // so a fresh id per mount (lost on reload) is enough for now.
  const [sessionId] = useState(() => crypto.randomUUID())
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)

  const appendBlock = useCallback((block: ChatBlock) => {
    setMessages((prev) => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (last.role !== "assistant") return prev
      const blocks = [...last.blocks]
      const lastBlock = blocks[blocks.length - 1]
      // Consecutive text parts (root's own text plus a sub-agent's) read as
      // one continuous reply -- Sabio is meant to synthesize, not hand back
      // multiple separately-voiced messages.
      if (block.type === "text" && lastBlock?.type === "text") {
        blocks[blocks.length - 1] = { type: "text", text: lastBlock.text + block.text }
      } else {
        blocks.push(block)
      }
      next[next.length - 1] = { ...last, blocks }
      return next
    })
  }, [])

  // Grouped by tool, not one row per call: a repo-scoped tool fires once per
  // configured repo for a single question, and a wall of identical "Looking
  // up commits" rows animating at once reads as noise rather than one piece
  // of work in progress. Only merges with the *immediately preceding* block
  // (same rationale as appendBlock's text-merging above) -- two separate,
  // non-adjacent calls to the same tool later in the answer are genuinely
  // separate steps and stay visually distinct.
  const appendToolCall = useCallback((tool: string, args: Record<string, unknown>) => {
    setMessages((prev) => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (last.role !== "assistant") return prev
      const blocks = [...last.blocks]
      const lastBlock = blocks[blocks.length - 1]
      const call: ToolCall = { detail: toolCallDetail(tool, args), done: false }

      if (lastBlock?.type === "tool" && lastBlock.tool === tool) {
        blocks[blocks.length - 1] = { ...lastBlock, calls: [...lastBlock.calls, call] }
      } else {
        const { label, icon } = toolMeta(tool)
        blocks.push({ type: "tool", tool, label, icon, calls: [call] })
      }
      next[next.length - 1] = { ...last, blocks }
      return next
    })
  }, [])

  const markLastToolDone = useCallback(() => {
    setMessages((prev) => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (last.role !== "assistant") return prev
      const blocks = [...last.blocks]
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i]
        if (b.type !== "tool") continue
        const callIdx = b.calls.findIndex((c) => !c.done)
        if (callIdx === -1) continue
        const calls = [...b.calls]
        calls[callIdx] = { ...calls[callIdx], done: true }
        blocks[i] = { ...b, calls }
        break
      }
      next[next.length - 1] = { ...last, blocks }
      return next
    })
  }, [])

  const sendMessage = useCallback(
    async (text: string, context: ContextItem[] = []) => {
      setMessages((prev) => [
        ...prev,
        { role: "user", text, context: context.length > 0 ? context : undefined },
        { role: "assistant", blocks: [] },
      ])
      setIsStreaming(true)

      try {
        const res = await fetch("/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            message: text,
            context: context.map((c) => ({
              path: c.path,
              start_line: c.startLine,
              end_line: c.endLine,
              content: c.content,
            })),
          }),
        })
        if (!res.ok || !res.body) {
          throw new Error(`chat request failed: ${res.status}`)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const frames = buffer.split("\n\n")
          buffer = frames.pop() ?? ""

          for (const frame of frames) {
            const line = frame.split("\n").find((l) => l.startsWith("data: "))
            if (!line) continue
            const event = JSON.parse(line.slice("data: ".length)) as StreamEvent

            if (event.type === "text") {
              appendBlock({ type: "text", text: event.text })
            } else if (event.type === "handoff") {
              // Internal routing between Sabio's own sub-agents -- not
              // something the user should see or need to know about, so
              // this event is consumed without rendering anything.
            } else if (event.type === "tool_call") {
              appendToolCall(event.tool, event.args)
            } else if (event.type === "tool_result") {
              markLastToolDone()
            } else if (event.type === "error") {
              appendBlock({ type: "text", text: `\n\n*Something went wrong: ${event.message}*` })
            }
          }
        }
      } catch (err) {
        appendBlock({
          type: "text",
          text: `\n\n*Something went wrong: ${err instanceof Error ? err.message : "unknown error"}*`,
        })
      } finally {
        markLastToolDone()
        setIsStreaming(false)
      }
    },
    [sessionId, appendBlock, appendToolCall, markLastToolDone],
  )

  return { messages, sendMessage, isStreaming }
}
