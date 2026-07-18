import { useCallback, useState } from "react"
import { FileTree } from "@/pages/code/FileTree"
import { FileViewer } from "@/pages/code/FileViewer"
import { RepoHeader } from "@/pages/code/RepoHeader"

export default function CodePage() {
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
      <RepoHeader />
      <div className="flex min-h-0 flex-1">
        <aside className="flex h-full w-64 shrink-0 flex-col border-r">
          <div className="flex h-9 shrink-0 items-center border-b px-3 text-xs font-medium text-muted-foreground">
            Files
          </div>
          <div className="min-h-0 flex-1 overflow-hidden p-1">
            <FileTree onSelectFile={handleSelectFile} activePath={activePath} />
          </div>
        </aside>
        <FileViewer
          openPaths={openPaths}
          activePath={activePath}
          onSelectTab={setActivePath}
          onCloseTab={handleCloseTab}
        />
      </div>
    </div>
  )
}
