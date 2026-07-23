import { useCallback, useState } from "react"
import { useParams } from "react-router-dom"
import { DEFAULT_REPO } from "@/lib/repos"
import { FileTree } from "@/pages/code/FileTree"
import { FileViewer } from "@/pages/code/FileViewer"
import { RepoHeader } from "@/pages/code/RepoHeader"

// Split so the `key` on the inner component forces a full remount (fresh
// openPaths/activePath) whenever the browsed ref *or* repo changes -- tabs
// left open from browsing one commit (or one codebase entirely) shouldn't
// silently carry over into another.
export default function CodePage() {
  // "*" (not a named param) -- refs for non-default branches contain a "/"
  // (e.g. "origin/29.x"), which the route matches via a wildcard segment.
  const params = useParams()
  const repoName = params.repoName ?? DEFAULT_REPO
  const browseRef = params["*"] || "HEAD"
  return <CodePageAtRef key={`${repoName}/${browseRef}`} repoName={repoName} browseRef={browseRef} />
}

function CodePageAtRef({ repoName, browseRef }: { repoName: string; browseRef: string }) {
  const [openPaths, setOpenPaths] = useState<string[]>([])
  const [activePath, setActivePath] = useState<string | null>(null)

  // Stable identity (empty deps, functional updates only) -- passed down
  // into FileTree's virtualized row renderer, which memoizes on this to
  // avoid remounting all ~3k rows whenever CodePage re-renders.
  const handleSelectFile = useCallback((path: string) => {
    setOpenPaths((prev) => (prev.includes(path) ? prev : [...prev, path]))
    setActivePath(path)
  }, [])

  const handleCloseTab = useCallback(
    (path: string) => {
      const closedIndex = openPaths.indexOf(path)
      const next = openPaths.filter((p) => p !== path)
      setOpenPaths(next)
      if (activePath === path) {
        setActivePath(next[closedIndex] ?? next[closedIndex - 1] ?? null)
      }
    },
    [openPaths, activePath],
  )

  return (
    <div className="flex h-full min-h-0 flex-col">
      <RepoHeader repoName={repoName} browseRef={browseRef} />
      <div className="flex min-h-0 flex-1">
        <aside className="flex h-full w-64 shrink-0 flex-col border-r">
          <div className="flex h-9 shrink-0 items-center border-b px-3 text-xs font-medium text-muted-foreground">
            Files
          </div>
          <div className="min-h-0 flex-1 overflow-hidden p-1">
            <FileTree
              onSelectFile={handleSelectFile}
              activePath={activePath}
              repoName={repoName}
              browseRef={browseRef}
            />
          </div>
        </aside>
        <FileViewer
          openPaths={openPaths}
          activePath={activePath}
          onSelectTab={setActivePath}
          onCloseTab={handleCloseTab}
          repoName={repoName}
          browseRef={browseRef}
        />
      </div>
    </div>
  )
}
