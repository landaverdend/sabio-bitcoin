import { GitBranch, History } from "lucide-react"
import { Link } from "react-router-dom"

import { useRepoSummary } from "@/hooks/use-repo-summary"
import { formatRelativeDate } from "@/lib/format-date"

export function RepoHeader() {
  const { data } = useRepoSummary()

  // Fixed height regardless of loading state so the panels below don't
  // jump once the summary arrives.
  return (
    <div className="flex h-10 shrink-0 items-center gap-4 border-b px-4 text-sm">
      {data && (
        <>
          <span className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
            <GitBranch className="size-4" />
            {data.branch}
          </span>
          <Link
            to={`/code/commit/${data.latest_commit.sha}`}
            className="min-w-0 flex-1 truncate text-muted-foreground hover:text-foreground"
          >
            <span className="text-foreground">{data.latest_commit.message}</span>
            {" · "}
            {data.latest_commit.short_sha} committed {formatRelativeDate(data.latest_commit.date)}
          </Link>
          <Link
            to="/code/commits"
            className="flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <History className="size-3.5" />
            {data.commit_count.toLocaleString()} commits
          </Link>
        </>
      )}
    </div>
  )
}
