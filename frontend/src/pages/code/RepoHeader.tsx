import { ArrowLeft, GitCommitHorizontal, History } from "lucide-react"
import { Link } from "react-router-dom"

import { formatRelativeDate } from "@/lib/format-date"
import { BranchSwitcher } from "@/pages/code/BranchSwitcher"
import { useRepoBranches } from "@/pages/code/hooks/use-repo-branches"
import { useRepoCommit } from "@/pages/code/hooks/use-repo-commit"
import { useRepoSummary } from "@/pages/code/hooks/use-repo-summary"

type RepoHeaderProps = {
  browseRef: string
}

export function RepoHeader({ browseRef }: RepoHeaderProps) {
  const { data: branchesData } = useRepoBranches()
  const matchedBranch = branchesData?.branches.find((b) => b.ref === browseRef)
  const isHead = browseRef === "HEAD"
  // A ref is "on a branch" (normal header + switcher) if it's HEAD or
  // matches a known branch tip; anything else is a specific historical
  // commit pinned via "browse repository at this point in the history",
  // which gets a distinct banner instead (no switcher -- you're not "on" a
  // branch there, matching GitHub's own tree-at-a-commit view).
  const isKnownBranch = isHead || !!matchedBranch

  const { data } = useRepoSummary("core", browseRef)
  const { data: commit } = useRepoCommit(browseRef, "core", !isKnownBranch)

  // Fixed height regardless of loading state so the panels below don't
  // jump once data arrives.
  if (!isKnownBranch) {
    return (
      <div className="flex h-10 shrink-0 items-center gap-4 border-b bg-accent/40 px-4 text-sm">
        <span className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
          <GitCommitHorizontal className="size-4" />
          Browsing at
          <span className="font-mono text-foreground">{commit?.short_sha ?? browseRef.slice(0, 7)}</span>
        </span>
        {commit && (
          <span className="min-w-0 flex-1 truncate text-muted-foreground">
            <span className="text-foreground">{commit.message}</span>
            {" · "}
            {commit.author} committed {formatRelativeDate(commit.date)}
          </span>
        )}
        <Link
          to="/code"
          className="flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" />
          Back to {branchesData?.branches.find((b) => b.is_default)?.name ?? "default branch"}
        </Link>
      </div>
    )
  }

  const currentBranchName = matchedBranch?.name ?? data?.branch ?? "master"
  const commitsHref =
    matchedBranch && !matchedBranch.is_default ? `/code/commits/${matchedBranch.ref}` : "/code/commits"

  return (
    <div className="flex h-10 shrink-0 items-center gap-4 border-b px-4 text-sm">
      {data && (
        <>
          <BranchSwitcher current={currentBranchName} defaultHref="/code" branchBasePath="/code/tree" />
          <Link
            to={`/code/commit/${data.latest_commit.sha}`}
            className="min-w-0 flex-1 truncate text-muted-foreground hover:text-foreground"
          >
            <span className="text-foreground">{data.latest_commit.message}</span>
            {" · "}
            {data.latest_commit.short_sha} committed {formatRelativeDate(data.latest_commit.date)}
          </Link>
          <Link
            to={commitsHref}
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
