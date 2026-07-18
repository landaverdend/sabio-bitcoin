import { ChevronLeft, Code, Copy, FileDiff } from "lucide-react"
import { useMemo } from "react"
import { Link, useParams } from "react-router-dom"

import { Markdown } from "@/components/Markdown"
import { formatRelativeDate } from "@/lib/format-date"
import { cn } from "@/lib/utils"
import { DiffFile } from "@/pages/code/DiffFile"
import { getFileIcon } from "@/pages/code/file-icons"
import { useRepoCommit } from "@/pages/code/hooks/use-repo-commit"

const STATUS_COLOR: Record<string, string> = {
  added: "text-green-600 dark:text-green-400",
  modified: "text-yellow-600 dark:text-yellow-400",
  deleted: "text-red-600 dark:text-red-400",
  renamed: "text-blue-600 dark:text-blue-400",
}

const STATUS_LETTER: Record<string, string> = {
  added: "A",
  modified: "M",
  deleted: "D",
  renamed: "R",
}

function DiffStatBar({ additions, deletions }: { additions: number; deletions: number }) {
  const total = additions + deletions
  if (total === 0) return null
  const blocks = 5
  const addBlocks = Math.max(additions > 0 ? 1 : 0, Math.round((additions / total) * blocks))
  const delBlocks = Math.min(blocks - addBlocks, deletions > 0 ? Math.max(1, blocks - addBlocks) : 0)
  return (
    <span className="inline-flex gap-0.5">
      {Array.from({ length: addBlocks }).map((_, i) => (
        <span key={`a${i}`} className="size-2.5 rounded-[2px] bg-green-600 dark:bg-green-400" />
      ))}
      {Array.from({ length: delBlocks }).map((_, i) => (
        <span key={`d${i}`} className="size-2.5 rounded-[2px] bg-red-600 dark:bg-red-400" />
      ))}
    </span>
  )
}

export default function CommitDetailPage() {
  const { sha = "" } = useParams<{ sha: string }>()
  const { data: commit, isLoading, isError } = useRepoCommit(sha)

  const totals = useMemo(() => {
    if (!commit) return { additions: 0, deletions: 0 }
    return commit.files.reduce(
      (acc, f) => ({ additions: acc.additions + f.additions, deletions: acc.deletions + f.deletions }),
      { additions: 0, deletions: 0 },
    )
  }, [commit])

  if (isLoading) {
    return <p className="p-6 text-sm text-muted-foreground">Loading…</p>
  }
  if (isError || !commit) {
    return <p className="p-6 text-sm text-destructive">Failed to load commit.</p>
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="flex h-full w-64 shrink-0 flex-col overflow-y-auto border-r">
        <div className="flex h-9 shrink-0 items-center border-b px-3 text-xs font-medium text-muted-foreground">
          {commit.files.length} changed file{commit.files.length === 1 ? "" : "s"}
        </div>
        {commit.files.map((file, i) => {
          const Icon = getFileIcon(file.path)
          return (
            <a
              key={file.path}
              href={`#file-${i}`}
              className="flex items-center gap-1.5 px-2 py-1.5 text-sm hover:bg-accent"
            >
              <span className={cn("w-3.5 shrink-0 text-center text-xs font-bold", STATUS_COLOR[file.status])}>
                {STATUS_LETTER[file.status]}
              </span>
              <Icon className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate">{file.path.split("/").pop()}</span>
            </a>
          )
        })}
      </aside>

      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col gap-3 border-b px-6 py-4">
          <Link
            to="/code/commits"
            className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ChevronLeft className="size-4" />
            Commits
          </Link>
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-xl font-semibold">
              Commit <span className="font-mono">{commit.short_sha}</span>
            </h1>
            <Link
              to={`/code/tree/${commit.sha}`}
              className="flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
              title="Browse the repository at this point in the history"
            >
              <Code className="size-3.5" />
              Browse files
            </Link>
          </div>
          <p className="text-sm text-muted-foreground">
            {commit.author} committed {formatRelativeDate(commit.date)}
          </p>
          <div className="rounded-md border bg-muted/30 p-3">
            <Markdown>{commit.message}</Markdown>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            {commit.parents.length > 0 && (
              <span>
                {commit.parents.length} parent{commit.parents.length > 1 ? "s" : ""}{" "}
                <span className="font-mono">{commit.parent_short}</span>
              </span>
            )}
            <span className="flex items-center gap-1">
              commit <span className="font-mono">{commit.short_sha}</span>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(commit.sha)}
                className="rounded p-0.5 hover:bg-muted"
                title="Copy full SHA"
              >
                <Copy className="size-3" />
              </button>
            </span>
            <span className="ml-auto flex items-center gap-2">
              <FileDiff className="size-4" />
              {commit.files.length} file{commit.files.length === 1 ? "" : "s"} changed
              <span className="text-green-600 dark:text-green-400">+{totals.additions}</span>
              <span className="text-red-600 dark:text-red-400">-{totals.deletions}</span>
              <DiffStatBar additions={totals.additions} deletions={totals.deletions} />
            </span>
          </div>
        </div>

        <div className="px-6 py-4">
          {commit.files.map((file, i) => (
            <div key={file.path} id={`file-${i}`}>
              <DiffFile file={file} sha={commit.sha} parentSha={commit.parents[0] ?? null} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
