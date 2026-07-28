import {
  FileText,
  Folder,
  GitCommitHorizontal,
  GitPullRequest,
  Globe2,
  MessageSquare,
  Search,
  TicketCheck,
  UserSearch,
  Users,
  type LucideIcon,
} from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"

import {
  translate,
  useLocale,
  type TranslationKey,
  type Translator,
} from "@/lib/i18n"

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

export type WebReference = {
  title: string
  sourceUrl: string
}

export type ChatBlock =
  | { type: "text"; text: string }
  | { type: "tool"; tool: string; label: string; icon: LucideIcon; calls: ToolCall[] }
  | { type: "source"; source: SourceReference }
  | { type: "communication_source"; source: CommunicationReference }
  | { type: "web_source"; source: WebReference }

// A file or highlighted excerpt attached from the code panel -- content is
// sent to the backend to be inlined directly into the model's prompt (see
// backend/chat/content.py), not just referenced by path,
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

export type ImageAttachment = {
  id: string
  kind: "image"
  name: string
  mimeType: string
  size: number
  dataUrl: string
}

export type RepositoryAttachment = {
  id: string
  kind: "repository"
  repoId: string
  label: string
}

export type PersonAttachment = {
  id: string
  kind: "person"
  personId: number
  label: string
  githubUsername?: string
  bitcointalkUsername?: string
}

export type ChatAttachment =
  | ImageAttachment
  | RepositoryAttachment
  | PersonAttachment

export type ChatMessage =
  | { role: "user"; text: string; context?: ContextItem[]; attachments?: ChatAttachment[] }
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
const TOOL_META: Record<string, { labelKey: TranslationKey; icon: LucideIcon }> = {
  get_commits: { labelKey: "toolCommits", icon: GitCommitHorizontal },
  get_open_prs: { labelKey: "toolOpenPrs", icon: GitPullRequest },
  get_pr_detail: { labelKey: "toolReadPr", icon: GitPullRequest },
  get_issues: { labelKey: "toolIssues", icon: TicketCheck },
  get_contributor_stats: { labelKey: "toolContributors", icon: Users },
  list_directory: { labelKey: "toolBrowseFiles", icon: Folder },
  read_file: { labelKey: "toolReadFile", icon: FileText },
  search_code: { labelKey: "toolSearchCode", icon: Search },
  resolve: { labelKey: "toolResolveIdentity", icon: UserSearch },
  get_message: { labelKey: "toolReadMessage", icon: MessageSquare },
  get_thread: { labelKey: "toolReadThread", icon: MessageSquare },
  // Not "the mailing list" -- search_messages has no channel filter and
  // spans mailing list, its historical precursor lists, and BitcoinTalk in
  // one query, so a channel-specific label here would misrepresent what was
  // actually searched.
  search_messages: { labelKey: "toolSearchDiscussions", icon: Search },
  search_web: { labelKey: "toolSearchWeb", icon: Globe2 },
  now: { labelKey: "toolCurrentTime", icon: Globe2 },
}

function toolMeta(tool: string, t: Translator): { label: string; icon: LucideIcon } {
  const meta = TOOL_META[tool]
  return meta
    ? { label: t(meta.labelKey), icon: meta.icon }
    : { label: t("toolUsing", { tool }), icon: Search }
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
  search_web: "query",
}

function toolCallDetail(tool: string, args: Record<string, unknown>): string | undefined {
  const value = args[DETAIL_ARG[tool]]
  return typeof value === "string" ? value : undefined
}

type StreamEvent =
  | {
      type: "user_message"
      message: string
      context: ContextItem[]
      attachments?: ChatAttachment[]
    }
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
  | {
      type: "web_source"
      title: string
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

function webReference(
  event: Extract<StreamEvent, { type: "web_source" }>,
): WebReference {
  return {
    title: event.title,
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
function reduceEvents(events: StreamEvent[], t: Translator): ChatMessage[] {
  const messages: ChatMessage[] = []

  for (const event of events) {
    if (event.type === "error" || event.type === "done") continue
    if (event.type === "handoff") continue // internal routing, never surfaced (see sendMessage below)

    if (event.type === "user_message") {
      messages.push({
        role: "user",
        text: event.message,
        context: event.context.length > 0 ? event.context : undefined,
        attachments:
          event.attachments && event.attachments.length > 0
            ? event.attachments
            : undefined,
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
        const { label, icon } = toolMeta(event.tool, t)
        blocks.push({ type: "tool", tool: event.tool, label, icon, calls: [call] })
      }
    } else if (event.type === "source") {
      blocks.push({ type: "source", source: sourceReference(event) })
    } else if (event.type === "communication_source") {
      blocks.push({
        type: "communication_source",
        source: communicationReference(event),
      })
    } else if (event.type === "web_source") {
      blocks.push({ type: "web_source", source: webReference(event) })
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

async function fetchSessionMessages(sessionId: string, t: Translator): Promise<ChatMessage[]> {
  const result = await requestJson<{ session_id: string; events: StreamEvent[] }>(
    `/chat/sessions/${sessionId}`,
  )
  return reduceEvents(result.events, t)
}

export function useChat(pubkey: string | null, restoreLatest = true) {
  const { locale, t } = useLocale()
  const localeRef = useRef(locale)
  localeRef.current = locale
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID())
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [sessionError, setSessionError] = useState<string | null>(null)
  // The run id addresses the matching backend agent execution. Keeping it
  // beside the controller also prevents an old run's finally block from
  // clearing the state of a newer run sent immediately after Stop.
  const activeRunRef = useRef<{
    controller: AbortController
    runId: string
  } | null>(null)

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
          const restored = await fetchSessionMessages(
            latest.session_id,
            (key, values) => translate(localeRef.current, key, values),
          )
          if (cancelled) return
          setSessionId(latest.session_id)
          setMessages(restored)
        }
      } catch (err) {
        if (!cancelled) {
          setSessionError(
            err instanceof Error
              ? err.message
              : translate(localeRef.current, "errorLoadConversations"),
          )
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
      setSessionError(
        err instanceof Error
          ? err.message
          : translate(localeRef.current, "errorRefreshConversations"),
      )
    }
  }, [pubkey, restoreLatest])

  useEffect(() => {
    setMessages((current) =>
      current.map((message) =>
        message.role === "assistant"
          ? {
              ...message,
              blocks: message.blocks.map((block) =>
                block.type === "tool"
                  ? { ...block, label: toolMeta(block.tool, t).label }
                  : block,
              ),
            }
          : message,
      ),
    )
  }, [t])

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
        const restored = await fetchSessionMessages(nextSessionId, t)
        setSessionId(nextSessionId)
        setMessages(restored)
      } catch (err) {
        setSessionError(err instanceof Error ? err.message : t("errorLoadConversation"))
      } finally {
        setIsLoadingHistory(false)
      }
    },
    [isStreaming, sessionId, t],
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
            setMessages(await fetchSessionMessages(next.session_id, t))
          } else {
            setSessionId(crypto.randomUUID())
            setMessages([])
          }
        }
      } catch (err) {
        setSessionError(err instanceof Error ? err.message : t("errorDeleteConversation"))
      } finally {
        setIsLoadingHistory(false)
      }
    },
    [isStreaming, sessionId, sessions, t],
  )

  const renameSession = useCallback(
    async (targetSessionId: string, title: string) => {
      const trimmed = title.trim()
      if (!trimmed) return
      setSessionError(null)
      try {
        await requestJson<{ session_id: string; title: string }>(
          `/chat/sessions/${targetSessionId}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: trimmed }),
          },
        )
        setSessions((prev) =>
          prev.map((session) =>
            session.session_id === targetSessionId ? { ...session, title: trimmed } : session,
          ),
        )
      } catch (err) {
        setSessionError(err instanceof Error ? err.message : t("errorRenameConversation"))
      }
    },
    [t],
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
        const { label, icon } = toolMeta(tool, t)
        blocks.push({ type: "tool", tool, label, icon, calls: [call] })
      }
      next[next.length - 1] = { ...last, blocks }
      return next
    })
  }, [t])

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
    async (
      text: string,
      context: ContextItem[] = [],
      attachments: ChatAttachment[] = [],
    ) => {
      setSessionError(null)
      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          text,
          context: context.length > 0 ? context : undefined,
          attachments: attachments.length > 0 ? attachments : undefined,
        },
        { role: "assistant", blocks: [] },
      ])
      setIsStreaming(true)
      const controller = new AbortController()
      const runId = crypto.randomUUID()
      activeRunRef.current = { controller, runId }

      try {
        const res = await fetch("/chat/stream", {
          method: "POST",
          credentials: "include", // the login (Nostr auth) session cookie
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({
            session_id: sessionId,
            run_id: runId,
            locale,
            message: text,
            context: context.map((c) => ({
              path: c.path,
              start_line: c.startLine,
              end_line: c.endLine,
              content: c.content,
            })),
            attachments: attachments.map((attachment) => {
              if (attachment.kind === "image") {
                return {
                  kind: attachment.kind,
                  name: attachment.name,
                  mime_type: attachment.mimeType,
                  size: attachment.size,
                  data_url: attachment.dataUrl,
                }
              }
              if (attachment.kind === "repository") {
                return {
                  kind: attachment.kind,
                  repo_id: attachment.repoId,
                  label: attachment.label,
                }
              }
              return {
                kind: attachment.kind,
                person_id: attachment.personId,
                label: attachment.label,
                github_username: attachment.githubUsername,
                bitcointalk_username: attachment.bitcointalkUsername,
              }
            }),
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
          if (done || controller.signal.aborted) break
          buffer += decoder.decode(value, { stream: true })
          const frames = buffer.split("\n\n")
          buffer = frames.pop() ?? ""

          for (const frame of frames) {
            if (controller.signal.aborted) break
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
            } else if (event.type === "web_source") {
              appendBlock({ type: "web_source", source: webReference(event) })
            } else if (event.type === "error") {
              appendBlock({
                type: "text",
                text: `\n\n*${t("errorGeneric", { message: event.message })}*`,
              })
            }
          }
        }
      } catch (err) {
        // A user-initiated stop rejects the in-flight fetch/read with an
        // AbortError -- that's the expected outcome of stopStreaming below,
        // not a failure worth surfacing as "something went wrong".
        if (
          !controller.signal.aborted &&
          !(err instanceof DOMException && err.name === "AbortError")
        ) {
          appendBlock({
            type: "text",
            text: `\n\n*${t("errorGeneric", {
              message: err instanceof Error ? err.message : t("unknown"),
            })}*`,
          })
        }
      } finally {
        if (activeRunRef.current?.runId === runId) {
          activeRunRef.current = null
          markLastToolDone()
          setIsStreaming(false)
          window.dispatchEvent(new Event(SESSIONS_CHANGED_EVENT))
        }
      }
    },
    [sessionId, appendBlock, appendToolCall, locale, markLastToolDone, t],
  )

  const stopStreaming = useCallback(() => {
    const activeRun = activeRunRef.current
    if (!activeRun) return

    // Stop rendering immediately, then explicitly signal the matching
    // backend run. The run id keeps this request from accidentally stopping
    // a newer message in the same conversation.
    activeRunRef.current = null
    activeRun.controller.abort()
    markLastToolDone()
    setIsStreaming(false)
    window.dispatchEvent(new Event(SESSIONS_CHANGED_EVENT))
    void fetch("/chat/stop", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        run_id: activeRun.runId,
      }),
    }).catch(() => {
      // The local AbortController has already stopped this client stream.
      // A transient stop-endpoint failure should not replace the partial
      // answer with an unrelated error message.
    })
  }, [markLastToolDone, sessionId])

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
    renameSession,
  }
}
