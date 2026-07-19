import { useCallback, useState } from "react"

export type ChatBlock =
  | { type: "text"; text: string }
  | { type: "tool"; label: string; done: boolean }

export type ChatMessage =
  | { role: "user"; text: string }
  | { role: "assistant"; blocks: ChatBlock[] }

const TOOL_LABELS: Record<string, string> = {
  get_commits: "Looking up commits",
  get_open_prs: "Checking open PRs",
  get_pr_detail: "Reading a PR",
  get_issues: "Checking issues",
  get_contributor_stats: "Checking contributor stats",
  list_directory: "Browsing files",
  read_file: "Reading a file",
  search_code: "Searching code",
  resolve: "Resolving identity",
  get_message: "Reading a message",
  get_thread: "Reading a thread",
  search_messages: "Searching the mailing list",
}

const AGENT_LABELS: Record<string, string> = {
  sabio_repos: "the repos specialist",
  sabio_comms: "the comms specialist",
}

function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? `Using ${tool}`
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

  const markLastToolDone = useCallback(() => {
    setMessages((prev) => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (last.role !== "assistant") return prev
      const blocks = [...last.blocks]
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i]
        if (b.type === "tool" && !b.done) {
          blocks[i] = { ...b, done: true }
          break
        }
      }
      next[next.length - 1] = { ...last, blocks }
      return next
    })
  }, [])

  const sendMessage = useCallback(
    async (text: string) => {
      setMessages((prev) => [...prev, { role: "user", text }, { role: "assistant", blocks: [] }])
      setIsStreaming(true)

      try {
        const res = await fetch("/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, message: text }),
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
              appendBlock({
                type: "tool",
                label: `Consulting ${AGENT_LABELS[event.to] ?? event.to}`,
                done: false,
              })
            } else if (event.type === "tool_call") {
              appendBlock({ type: "tool", label: toolLabel(event.tool), done: false })
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
    [sessionId, appendBlock, markLastToolDone],
  )

  return { messages, sendMessage, isStreaming }
}
