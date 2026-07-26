import { ChevronLeft, ExternalLink, GitCommitHorizontal, Search } from "lucide-react"
import { useMemo, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"

import { ListSkeleton } from "@/components/ListRowSkeleton"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsPanel, TabsTab } from "@/components/ui/tabs"
import { channelLabel } from "@/lib/channels"
import { formatRelativeDate } from "@/lib/format-date"
import { useRepoCommitPages, useRepoCommits } from "@/pages/code/hooks/use-repo-commits"
import { PersonAvatar } from "@/pages/people/PersonAvatar"
import { usePerson } from "@/pages/people/hooks/use-person"
import { usePersonMessagePages } from "@/pages/people/hooks/use-person-messages"

const COMMITS_TAB = "commits"

function personName(name: string | null, github: string | null, bitcointalk: string | null, email: string | null) {
  return name || github || bitcointalk || email || "Unknown"
}

export default function PersonDetailPage() {
  const { id = "" } = useParams()
  const { data: person, isLoading: personLoading } = usePerson(id)
  const [searchParams, setSearchParams] = useSearchParams()

  // github_username, not display_name: the /repo/commits author filter is
  // an exact GitHub login/email match (see backend/repo.py's get_commits
  // docstring), so a free-text display name would just never match anything
  // real. A person with no linked GitHub identity has no reliable way to
  // filter commits by them at all, so the query is disabled entirely rather
  // than sent unfiltered (which would return -- and appear to attribute --
  // the whole repo's history to them).
  const hasGithubIdentity = !!person?.github_username

  // Unfiltered-by-search existence check -- always the full commit count
  // for this person, regardless of what's typed into the Commits tab's own
  // search box, since whether the tab exists at all shouldn't flicker based
  // on a search that happens to match nothing. Same query key as the
  // display fetch below when no search is active, so TanStack Query dedupes
  // them into a single request in the common case.
  const commitExistence = useRepoCommits(
    1, "core", "HEAD", { author: person?.github_username ?? undefined }, hasGithubIdentity,
  )
  const commitTotalForExistence = hasGithubIdentity ? (commitExistence.data?.total ?? 0) : 0
  const commitsSettled = !hasGithubIdentity || !commitExistence.isLoading

  const [commitSearch, setCommitSearch] = useState("")
  const commitQuery = commitSearch.trim() || undefined
  const [commitPageCount, setCommitPageCount] = useState(1)
  const commitPages = useRepoCommitPages(
    commitPageCount,
    "core",
    "HEAD",
    { author: person?.github_username ?? undefined, q: commitQuery },
    hasGithubIdentity,
  )
  const commits = useMemo(() => commitPages.flatMap((p) => p.data?.commits ?? []), [commitPages])
  const commitTotal = commitPages[0]?.data?.total ?? 0
  const commitsLoading = commitPages.some((p) => p.isLoading)
  const hasMoreCommits = commits.length < commitTotal

  const tabs = useMemo(() => {
    if (!person) return []
    const list: { key: string; label: string; count: number }[] = []
    if (commitTotalForExistence > 0) {
      list.push({ key: COMMITS_TAB, label: "Commits", count: commitTotalForExistence })
    }
    for (const c of person.channels) {
      list.push({ key: c.channel, label: channelLabel(c.channel), count: c.count })
    }
    return list
  }, [person, commitTotalForExistence])

  const requestedTab = searchParams.get("tab")
  const activeTab = tabs.some((t) => t.key === requestedTab) ? (requestedTab as string) : (tabs[0]?.key ?? "")

  const [messageSearch, setMessageSearch] = useState("")
  const messageQuery = messageSearch.trim() || undefined
  const [messagePageCount, setMessagePageCount] = useState(1)
  // Zero pages (no fetch) while on the Commits tab -- only one channel's
  // messages are ever shown at a time, so there's nothing to fetch there.
  const effectiveMessagePageCount = activeTab === COMMITS_TAB ? 0 : messagePageCount
  const messagePages = usePersonMessagePages(id, effectiveMessagePageCount, {
    channel: activeTab === COMMITS_TAB ? undefined : activeTab,
    q: messageQuery,
  })
  const messages = useMemo(() => messagePages.flatMap((p) => p.data?.messages ?? []), [messagePages])
  const messageTotal = messagePages[0]?.data?.total ?? 0
  const messagesLoading = messagePages.some((p) => p.isLoading)
  const hasMoreMessages = messages.length < messageTotal

  const selectTab = (key: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set("tab", key)
      return next
    })
    setMessageSearch("")
    setMessagePageCount(1)
    setCommitSearch("")
    setCommitPageCount(1)
  }

  if (personLoading || !commitsSettled) {
    return (
      <div className="flex h-full min-h-0 flex-col overflow-y-auto">
        <div className="flex shrink-0 flex-col gap-4 border-b px-6 py-4">
          <Skeleton className="h-4 w-16" />
          <div className="flex items-center gap-3">
            <Skeleton className="size-10 shrink-0 rounded-full" />
            <div className="space-y-2">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-3 w-56" />
            </div>
          </div>
        </div>
        <div className="flex-1 px-6 py-4">
          <Skeleton className="mb-3 h-8 w-64" />
          <div className="overflow-hidden rounded-md border">
            <ListSkeleton rows={6} trailing />
          </div>
        </div>
      </div>
    )
  }
  if (!person) {
    return <p className="p-6 text-sm text-destructive">Person not found.</p>
  }

  const name = personName(person.display_name, person.github_username, person.bitcointalk_username, person.email)

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="flex shrink-0 flex-col gap-4 border-b px-6 py-4">
        <Link to="/people" className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ChevronLeft className="size-4" />
          People
        </Link>
        <div className="flex items-center gap-3">
          <PersonAvatar name={name} size="lg" />
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold">{name}</h1>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
              {person.email && <span>{person.email}</span>}
              {person.github_username && <span>GitHub: {person.github_username}</span>}
              {person.bitcointalk_username && <span>BitcoinTalk: {person.bitcointalk_username}</span>}
            </div>
          </div>
        </div>

        {person.identities.length > 1 && (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span className="shrink-0">Also known as:</span>
            {person.identities
              .filter((i) => i.id !== person.id)
              .map((identity) => (
                <span key={identity.id} className="rounded-full border px-2 py-0.5">
                  {identity.email ?? identity.github_username ?? identity.bitcointalk_username ?? identity.display_name}
                </span>
              ))}
          </div>
        )}
      </div>

      <div className="flex-1 px-6 py-4">
        {tabs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No activity found for this person.</p>
        ) : (
          <Tabs value={activeTab} onValueChange={(value) => selectTab(value as string)}>
            <TabsList>
              {tabs.map((t) => (
                <TabsTab key={t.key} value={t.key}>
                  {t.key === COMMITS_TAB && <GitCommitHorizontal className="size-3.5" />}
                  {t.label}
                  <span className="text-xs text-muted-foreground">{t.count.toLocaleString()}</span>
                </TabsTab>
              ))}
            </TabsList>

            {tabs.map((t) => (
              <TabsPanel key={t.key} value={t.key}>
                {t.key === COMMITS_TAB ? (
                  <>
                    <div className="mb-3 flex max-w-sm items-center gap-2 rounded-md border px-2.5 py-1.5">
                      <Search className="size-3.5 shrink-0 text-muted-foreground" />
                      <input
                        value={commitSearch}
                        onChange={(e) => {
                          setCommitSearch(e.target.value)
                          setCommitPageCount(1)
                        }}
                        placeholder="Search commit messages..."
                        className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                      />
                    </div>
                    <div className="overflow-hidden rounded-md border">
                      {commitsLoading && commits.length === 0 ? (
                        <ListSkeleton rows={5} trailing />
                      ) : (
                        <>
                          {commits.map((commit, i) => (
                            <Link
                              key={commit.sha}
                              to={`/code/commit/${commit.sha}`}
                              className={`flex items-center gap-3 px-4 py-3 hover:bg-accent ${i > 0 ? "border-t" : ""}`}
                            >
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-sm font-medium">{commit.message}</p>
                                <p className="text-xs text-muted-foreground">
                                  committed {formatRelativeDate(commit.date)}
                                </p>
                              </div>
                              <span className="shrink-0 font-mono text-xs text-muted-foreground">
                                {commit.short_sha}
                              </span>
                            </Link>
                          ))}
                          {commits.length === 0 && (
                            <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                              {commitQuery ? `No commits matching "${commitQuery}".` : "No commits found."}
                            </p>
                          )}
                        </>
                      )}
                    </div>
                    {hasMoreCommits && (
                      <Button
                        variant="outline"
                        className="mt-3"
                        disabled={commitsLoading}
                        onClick={() => setCommitPageCount((n) => n + 1)}
                      >
                        {commitsLoading ? "Loading…" : "Load more"}
                      </Button>
                    )}
                  </>
                ) : (
                  <>
                    <div className="mb-3 flex max-w-sm items-center gap-2 rounded-md border px-2.5 py-1.5">
                      <Search className="size-3.5 shrink-0 text-muted-foreground" />
                      <input
                        value={messageSearch}
                        onChange={(e) => {
                          setMessageSearch(e.target.value)
                          setMessagePageCount(1)
                        }}
                        placeholder={`Search ${t.label}...`}
                        className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                      />
                    </div>
                    <div className="overflow-hidden rounded-md border">
                      {messagesLoading && messages.length === 0 ? (
                        <ListSkeleton rows={5} lines={3} />
                      ) : (
                        <>
                          {messages.map((message, i) => (
                            <a
                              key={message.id}
                              href={message.url}
                              target="_blank"
                              rel="noreferrer"
                              className={`flex items-start gap-3 px-4 py-3 hover:bg-accent ${i > 0 ? "border-t" : ""}`}
                            >
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-sm font-medium">{message.title || "(no subject)"}</p>
                                <p className="text-xs text-muted-foreground">
                                  {formatRelativeDate(message.posted_at)}
                                </p>
                                {message.snippet && (
                                  <p className="mt-1 truncate text-xs text-muted-foreground">{message.snippet}</p>
                                )}
                              </div>
                              <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" />
                            </a>
                          ))}
                          {messages.length === 0 && (
                            <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                              {messageQuery ? `No posts matching "${messageQuery}".` : "No posts found."}
                            </p>
                          )}
                        </>
                      )}
                    </div>
                    {hasMoreMessages && (
                      <Button
                        variant="outline"
                        className="mt-3"
                        disabled={messagesLoading}
                        onClick={() => setMessagePageCount((n) => n + 1)}
                      >
                        {messagesLoading ? "Loading…" : "Load more"}
                      </Button>
                    )}
                  </>
                )}
              </TabsPanel>
            ))}
          </Tabs>
        )}
      </div>
    </div>
  )
}
