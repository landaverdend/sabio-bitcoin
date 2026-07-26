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
import { useCallback, useEffect, useRef, useState } from "react"

export type ToolCall = { detail?: string; done: boolean }

export type SourceReference = {
  repo: string
  path: string
  ref: string
  startLine: number
  endLine: number
  githubUrl: string
}

export type CommunicationReference = {
  messageId: string
  channel: string
  author: string | null
  title: string | null
  postedAt: string | null
  excerpt: string
  sourceUrl: string
}

export type ChatBlock =
  | { type: "text"; text: string }
  | { type: "tool"; tool: string; label: string; icon: LucideIcon; calls: ToolCall[] }
  | { type: "source"; source: SourceReference }
  | { type: "communication_source"; source: CommunicationReference }

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

export type ChatSessionSummary = {
  session_id: string
  title: string
  last_update_time: number
}

const SESSIONS_CHANGED_EVENT = "sabio:sessions-changed"

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
  | { type: "user_message"; message: string; context: ContextItem[] }
  | { type: "text"; author: string; text: string }
  | { type: "handoff"; to: string }
  | { type: "tool_call"; author: string; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; author: string; tool: string }
  | {
      type: "source"
      repo: string
      path: string
      ref: string
      start_line: number
      end_line: number
      github_url: string
    }
  | {
      type: "communication_source"
      message_id: string
      channel: string
      author: string | null
      title: string | null
      posted_at: string | null
      excerpt: string
      source_url: string
    }
  | { type: "error"; message: string }
  | { type: "done" }

function sourceReference(event: Extract<StreamEvent, { type: "source" }>): SourceReference {
  return {
    repo: event.repo,
    path: event.path,
    ref: event.ref,
    startLine: event.start_line,
    endLine: event.end_line,
    githubUrl: event.github_url,
  }
}

function communicationReference(
  event: Extract<StreamEvent, { type: "communication_source" }>,
): CommunicationReference {
  return {
    messageId: event.message_id,
    channel: event.channel,
    author: event.author,
    title: event.title,
    postedAt: event.posted_at,
    excerpt: event.excerpt,
    sourceUrl: event.source_url,
  }
}

// Rebuilds a full message list from a stored session's event history in one
// pass -- deliberately a separate pure fold rather than routing history
// through the same setMessages-based helpers the live stream uses below.
// Those assume they're always appending to "the current in-flight assistant
// turn"; a replay instead has user and assistant events interleaved across
// an entire conversation, so it re-implements the same merge rules (adjacent
// text coalesces, adjacent same-tool calls group) as a straight fold over
// the full list instead.
function reduceEvents(events: StreamEvent[]): ChatMessage[] {
  const messages: ChatMessage[] = []

  for (const event of events) {
    if (event.type === "error" || event.type === "done") continue
    if (event.type === "handoff") continue // internal routing, never surfaced (see sendMessage below)

    if (event.type === "user_message") {
      messages.push({
        role: "user",
        text: event.message,
        context: event.context.length > 0 ? event.context : undefined,
      })
      continue
    }

    let last = messages[messages.length - 1]
    if (!last || last.role !== "assistant") {
      last = { role: "assistant", blocks: [] }
      messages.push(last)
    }
    const blocks = last.blocks
    const lastBlock = blocks[blocks.length - 1]

    if (event.type === "text") {
      if (lastBlock?.type === "text") {
        lastBlock.text += event.text
      } else {
        blocks.push({ type: "text", text: event.text })
      }
    } else if (event.type === "tool_call") {
      const call: ToolCall = { detail: toolCallDetail(event.tool, event.args), done: true }
      if (lastBlock?.type === "tool" && lastBlock.tool === event.tool) {
        lastBlock.calls.push(call)
      } else {
        const { label, icon } = toolMeta(event.tool)
        blocks.push({ type: "tool", tool: event.tool, label, icon, calls: [call] })
      }
    } else if (event.type === "source") {
      blocks.push({ type: "source", source: sourceReference(event) })
    } else if (event.type === "communication_source") {
      blocks.push({
        type: "communication_source",
        source: communicationReference(event),
      })
    }
    // tool_result: a completed session's calls are already known-done (see
    // `done: true` above) -- there's no in-flight state left to mark.
  }

  return messages
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { credentials: "include", ...init })
  const contentType = res.headers.get("content-type") ?? ""

  if (!contentType.toLowerCase().includes("application/json")) {
    throw new Error(
      `API returned ${contentType || "an unknown content type"} for ${url} (${res.status})`,
    )
  }

  const body = (await res.json()) as T & { detail?: string }
  if (!res.ok) {
    throw new Error(body?.detail || `request failed: ${res.status}`)
  }
  return body
}

async function fetchSessions(): Promise<ChatSessionSummary[]> {
  return requestJson<ChatSessionSummary[]>("/chat/sessions")
}

async function fetchSessionMessages(sessionId: string): Promise<ChatMessage[]> {
  const result = await requestJson<{ session_id: string; events: StreamEvent[] }>(
    `/chat/sessions/${sessionId}`,
  )
  return reduceEvents(result.events)
}

export function useChat(pubkey: string | null, restoreLatest = true) {
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID())
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [sessionError, setSessionError] = useState<string | null>(null)
  // Not state -- aborting shouldn't itself trigger a re-render, only the
  // isStreaming flip that follows it.
  const abortControllerRef = useRef<AbortController | null>(null)

  // Restore the most recently active conversation after auth resolves. A
  // pubkey change is a hard tenant boundary: clear the prior user's local
  // state before fetching anything for the new identity.
  useEffect(() => {
    let cancelled = false
    setMessages([])
    setSessions([])
    setSessionId(crypto.randomUUID())
    setSessionError(null)

    if (!pubkey || !restoreLatest) {
      setIsLoadingHistory(false)
      return () => {
        cancelled = true
      }
    }

    setIsLoadingHistory(true)
    void (async () => {
      try {
        const stored = await fetchSessions()
        if (cancelled) return
        setSessions(stored)
        if (stored.length > 0) {
          const latest = stored[0]
          const restored = await fetchSessionMessages(latest.session_id)
          if (cancelled) return
          setSessionId(latest.session_id)
          setMessages(restored)
        }
      } catch (err) {
        if (!cancelled) {
          setSessionError(err instanceof Error ? err.message : "Could not load conversations")
        }
      } finally {
        if (!cancelled) setIsLoadingHistory(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [pubkey, restoreLatest])

  const refreshSessions = useCallback(async () => {
    if (!pubkey || !restoreLatest) return
    try {
      setSessions(await fetchSessions())
    } catch (err) {
      setSessionError(err instanceof Error ? err.message : "Could not refresh conversations")
    }
  }, [pubkey, restoreLatest])

  // CodeChatPanel deliberately owns an independent active chat, but those
  // conversations live in the same account. Refresh this shared list when
  // any chat hook finishes creating or updating a session.
  useEffect(() => {
    if (!restoreLatest) return
    const refresh = () => void refreshSessions()
    window.addEventListener(SESSIONS_CHANGED_EVENT, refresh)
    return () => window.removeEventListener(SESSIONS_CHANGED_EVENT, refresh)
  }, [refreshSessions, restoreLatest])

  const newSession = useCallback(() => {
    if (isStreaming) return
    setSessionId(crypto.randomUUID())
    setMessages([])
    setSessionError(null)
  }, [isStreaming])

  const loadSession = useCallback(
    async (nextSessionId: string) => {
      if (isStreaming || nextSessionId === sessionId) return
      setIsLoadingHistory(true)
      setSessionError(null)
      try {
        const restored = await fetchSessionMessages(nextSessionId)
        setSessionId(nextSessionId)
        setMessages(restored)
      } catch (err) {
        setSessionError(err instanceof Error ? err.message : "Could not load conversation")
      } finally {
        setIsLoadingHistory(false)
      }
    },
    [isStreaming, sessionId],
  )

  const deleteSession = useCallback(
    async (deletedSessionId: string) => {
      if (isStreaming) return
      setIsLoadingHistory(true)
      setSessionError(null)
      try {
        await requestJson<{ ok: boolean }>(`/chat/sessions/${deletedSessionId}`, {
          method: "DELETE",
        })
        const remaining = sessions.filter((session) => session.session_id !== deletedSessionId)
        setSessions(remaining)
        if (deletedSessionId === sessionId) {
          if (remaining.length > 0) {
            const next = remaining[0]
            setSessionId(next.session_id)
            setMessages(await fetchSessionMessages(next.session_id))
          } else {
            setSessionId(crypto.randomUUID())
            setMessages([])
          }
        }
      } catch (err) {
        setSessionError(err instanceof Error ? err.message : "Could not delete conversation")
      } finally {
        setIsLoadingHistory(false)
      }
    },
    [isStreaming, sessionId, sessions],
  )

  const appendBlock = useCallback((block: ChatBlock) => {
    setMessages((prev) => {
      const next = [...prev]
      const last = next[next.length - 1]
      if (!last || last.role !== "assistant") return prev
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
      if (!last || last.role !== "assistant") return prev
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
      if (!last || last.role !== "assistant") return prev
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
      setSessionError(null)
      setMessages((prev) => [
        ...prev,
        { role: "user", text, context: context.length > 0 ? context : undefined },
        { role: "assistant", blocks: [] },
      ])
      setIsStreaming(true)
      const controller = new AbortController()
      abortControllerRef.current = controller

      try {
        const res = await fetch("/chat/stream", {
          method: "POST",
          credentials: "include", // the login (Nostr auth) session cookie
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
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
            } else if (event.type === "user_message") {
              // User events are returned only by the history endpoint, not
              // by the live Runner stream.
            } else if (event.type === "handoff") {
              // Internal routing between Sabio's own sub-agents -- not
              // something the user should see or need to know about, so
              // this event is consumed without rendering anything.
            } else if (event.type === "tool_call") {
              appendToolCall(event.tool, event.args)
            } else if (event.type === "tool_result") {
              markLastToolDone()
            } else if (event.type === "source") {
              appendBlock({ type: "source", source: sourceReference(event) })
            } else if (event.type === "communication_source") {
              appendBlock({
                type: "communication_source",
                source: communicationReference(event),
              })
            } else if (event.type === "error") {
              appendBlock({ type: "text", text: `\n\n*Something went wrong: ${event.message}*` })
            }
          }
        }
      } catch (err) {
        // A user-initiated stop rejects the in-flight fetch/read with an
        // AbortError -- that's the expected outcome of stopStreaming below,
        // not a failure worth surfacing as "something went wrong".
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          appendBlock({
            type: "text",
            text: `\n\n*Something went wrong: ${err instanceof Error ? err.message : "unknown error"}*`,
          })
        }
      } finally {
        abortControllerRef.current = null
        markLastToolDone()
        setIsStreaming(false)
        window.dispatchEvent(new Event(SESSIONS_CHANGED_EVENT))
      }
    },
    [sessionId, appendBlock, appendToolCall, markLastToolDone],
  )

  // Aborting the fetch also drops the underlying HTTP connection, which is
  // enough on its own to stop the backend: Starlette detects the disconnect
  // and cancels the streaming generator's task, so the agent run itself
  // (further LLM calls, tool calls) stops rather than just the display of
  // it -- no separate "/chat/stop" endpoint needed.
  const stopStreaming = useCallback(() => {
    abortControllerRef.current?.abort()
  }, [])

  return {
    sessionId,
    sessions,
    messages,
    sendMessage,
    stopStreaming,
    isStreaming,
    isLoadingHistory,
    sessionError,
    newSession,
    loadSession,
    deleteSession,
  }
}
