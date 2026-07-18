import { ChevronLeft, Copy, GitCommitHorizontal } from "lucide-react"
import { useMemo, useState } from "react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { useRepoCommitPages } from "@/hooks/use-repo-commits"
import type { CommitInfo } from "@/hooks/use-repo-summary"
import { useRepoSummary } from "@/hooks/use-repo-summary"
import { formatRelativeDate } from "@/lib/format-date"
import { AuthorFilter } from "@/pages/code/AuthorFilter"
import type { DateRange } from "@/pages/code/DateFilter"
import { DateFilter } from "@/pages/code/DateFilter"

function groupByDay(commits: CommitInfo[]): [string, CommitInfo[]][] {
  const groups = new Map<string, CommitInfo[]>()
  for (const commit of commits) {
    const label = new Date(commit.date).toLocaleDateString(undefined, {
      month: "long",
      day: "numeric",
      year: "numeric",
    })
    const group = groups.get(label)
    if (group) group.push(commit)
    else groups.set(label, [commit])
  }
  return [...groups.entries()]
}

export default function CommitsPage() {
  const [pageCount, setPageCount] = useState(1)
  const [author, setAuthor] = useState<string | null>(null)
  const [dateRange, setDateRange] = useState<DateRange | null>(null)
  const { data: summary } = useRepoSummary()
  const pages = useRepoCommitPages(pageCount, "core", "HEAD", {
    author: author ?? undefined,
    since: dateRange?.since,
    until: dateRange?.until,
  })

  const commits = useMemo(() => pages.flatMap((p) => p.data?.commits ?? []), [pages])
  const groups = useMemo(() => groupByDay(commits), [commits])
  const total = pages[0]?.data?.total ?? 0
  const isLoading = pages.some((p) => p.isLoading)
  const hasMore = commits.length < total

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="flex shrink-0 flex-col gap-3 border-b px-6 py-4">
        <Link
          to="/code"
          className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="size-4" />
          Code
        </Link>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">Commits</h1>
          {summary && (
            <span className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground">
              {summary.branch}
            </span>
          )}
          <AuthorFilter
            selected={author}
            onSelect={(next) => {
              setAuthor(next)
              setPageCount(1)
            }}
          />
          <DateFilter
            selected={dateRange}
            onSelect={(next) => {
              setDateRange(next)
              setPageCount(1)
            }}
          />
        </div>
      </div>

      <div className="flex-1 px-6 py-4">
        {groups.map(([label, dayCommits]) => (
          <div key={label} className="mb-6">
            <h2 className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <GitCommitHorizontal className="size-4" />
              Commits on {label}
            </h2>
            <div className="overflow-hidden rounded-md border">
              {dayCommits.map((commit, i) => (
                <div
                  key={commit.sha}
                  className={`flex items-center gap-3 px-4 py-3 ${i > 0 ? "border-t" : ""}`}
                >
                  <Link to={`/code/commit/${commit.sha}`} className="min-w-0 flex-1 hover:underline">
                    <p className="truncate text-sm font-medium">{commit.message}</p>
                    <p className="text-xs text-muted-foreground no-underline">
                      {commit.author} committed {formatRelativeDate(commit.date)}
                    </p>
                  </Link>
                  <button
                    type="button"
                    onClick={() => navigator.clipboard.writeText(commit.sha)}
                    className="flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-xs text-muted-foreground hover:bg-accent"
                    title="Copy full SHA"
                  >
                    {commit.short_sha}
                    <Copy className="size-3" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))}

        {hasMore && (
          <Button
            variant="outline"
            disabled={isLoading}
            onClick={() => setPageCount((n) => n + 1)}
          >
            {isLoading ? "Loading…" : "Load more commits"}
          </Button>
        )}
      </div>
    </div>
  )
}
