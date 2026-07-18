import { DiffEditor } from "@monaco-editor/react"

import { useTheme } from "@/components/theme-provider"
import type { CommitFile } from "@/hooks/use-repo-commit"
import { useRepoFile } from "@/hooks/use-repo-file"
import { getFileIcon } from "@/pages/code/file-icons"
import { getMonacoLanguage } from "@/pages/code/monaco-language"

type DiffFileProps = {
  file: CommitFile
  sha: string
  parentSha: string | null
}

function basename(path: string): string {
  return path.split("/").pop() ?? path
}

export function DiffFile({ file, sha, parentSha }: DiffFileProps) {
  const { theme } = useTheme()
  const isDark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)

  // Renamed-without-content-change files still need the *old* path to look
  // up the "before" blob -- it doesn't exist at the new path pre-rename.
  const originalPath = file.status === "renamed" ? file.old_path : file.path
  const fetchOriginal = file.status !== "added" && parentSha !== null
  const fetchModified = file.status !== "deleted"

  const original = useRepoFile(originalPath, "core", parentSha ?? "HEAD", fetchOriginal)
  const modified = useRepoFile(file.path, "core", sha, fetchModified)

  const Icon = getFileIcon(basename(file.path))
  const isLoading = (fetchOriginal && original.isLoading) || (fetchModified && modified.isLoading)
  const isBinary = original.data?.binary || modified.data?.binary

  return (
    <div className="mb-4 overflow-hidden rounded-md border">
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2 text-sm">
        <Icon className="size-4 shrink-0 text-muted-foreground" />
        <span className="truncate font-mono">
          {file.status === "renamed" ? `${file.old_path} → ${file.path}` : file.path}
        </span>
        <span className="ml-auto shrink-0 text-xs">
          <span className="text-green-600 dark:text-green-400">+{file.additions}</span>{" "}
          <span className="text-red-600 dark:text-red-400">-{file.deletions}</span>
        </span>
      </div>
      {isLoading && <p className="p-3 text-sm text-muted-foreground">Loading…</p>}
      {!isLoading && isBinary && (
        <p className="p-3 text-sm text-muted-foreground">Binary file not shown.</p>
      )}
      {!isLoading && !isBinary && (
        <DiffEditor
          original={fetchOriginal ? (original.data?.content ?? "") : ""}
          modified={fetchModified ? (modified.data?.content ?? "") : ""}
          language={getMonacoLanguage(basename(file.path))}
          theme={isDark ? "vs-dark" : "vs"}
          options={{
            readOnly: true,
            renderSideBySide: true,
            useInlineViewWhenSpaceIsLimited: false,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
          }}
          height="400px"
        />
      )}
    </div>
  )
}
