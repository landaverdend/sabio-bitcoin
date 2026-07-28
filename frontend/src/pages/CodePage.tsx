import { useQueryClient } from "@tanstack/react-query"
import { MessageSquareText } from "lucide-react"
import { useCallback, useState } from "react"
import { useParams } from "react-router-dom"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { useLocale } from "@/lib/i18n"
import { DEFAULT_REPO } from "@/lib/repos"
import type { ContextItem } from "@/pages/chat/hooks/use-chat"
import { CodeChatPanel } from "@/pages/code/CodeChatPanel"
import { FileTree } from "@/pages/code/FileTree"
import { FileViewer } from "@/pages/code/FileViewer"
import { repoFileQuery } from "@/pages/code/hooks/use-repo-file"
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
  const { t } = useLocale()
  const queryClient = useQueryClient()
  const [openPaths, setOpenPaths] = useState<string[]>([])
  const [activePath, setActivePath] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [contextItems, setContextItems] = useState<ContextItem[]>([])

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

  // Opens the panel on first use rather than requiring it already be open --
  // "highlight code, add it" should work as one motion, not two.
  const addContext = useCallback((item: ContextItem) => {
    setContextItems((prev) => [...prev, item])
    setChatOpen(true)
  }, [])

  const handleAddFile = useCallback(
    async (path: string) => {
      // A fresh fetch is a real ~1s round trip to GitHub's API, and the
      // picker/tree gave no feedback while that was in flight -- it just
      // looked stuck. Adding a loading placeholder immediately (patched in
      // place once content arrives) makes the click feel instant regardless
      // of how long the fetch actually takes. queryClient.fetchQuery (not a
      // raw fetch) also means a file that's already open in a tab -- same
      // cache key as useRepoFile/useRepoFiles -- resolves right away instead
      // of re-fetching content this page already has.
      const id = crypto.randomUUID()
      setContextItems((prev) => [...prev, { id, path, content: "", loading: true }])
      setChatOpen(true)
      try {
        const file = await queryClient.fetchQuery(repoFileQuery(path, repoName, browseRef))
        if (file.binary || file.content === null) {
          setContextItems((prev) => prev.filter((c) => c.id !== id))
          return
        }
        const content = file.content
        setContextItems((prev) => prev.map((c) => (c.id === id ? { ...c, content, loading: false } : c)))
      } catch {
        setContextItems((prev) => prev.filter((c) => c.id !== id))
      }
    },
    [repoName, browseRef, queryClient],
  )

  const handleAddSelection = useCallback(
    (path: string, startLine: number, endLine: number, content: string) => {
      addContext({ id: crypto.randomUUID(), path, startLine, endLine, content })
    },
    [addContext],
  )

  return (
    <div className="flex h-full min-h-0 flex-col">
      <RepoHeader repoName={repoName} browseRef={browseRef} />
      <div className="flex min-h-0 flex-1">
        {/* Pixel-based sizes here (react-resizable-panels v4 treats bare
            numbers as px, not %) -- matches the fixed w-64/w-96 values this
            replaced, just now adjustable rather than locked. */}
        <ResizablePanelGroup orientation="horizontal" className="min-h-0 flex-1">
          <ResizablePanel id="file-tree" defaultSize={256} minSize={180} maxSize={480}>
            <aside className="flex h-full flex-col border-r">
              <div className="flex h-9 shrink-0 items-center border-b px-3 text-xs font-medium text-muted-foreground">
                Files
              </div>
              <div className="min-h-0 flex-1 overflow-hidden p-1">
                <FileTree
                  onSelectFile={handleSelectFile}
                  activePath={activePath}
                  repoName={repoName}
                  browseRef={browseRef}
                  onAddToContext={handleAddFile}
                />
              </div>
            </aside>
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel id="file-viewer" minSize={320}>
            <FileViewer
              openPaths={openPaths}
              activePath={activePath}
              onSelectTab={setActivePath}
              onCloseTab={handleCloseTab}
              repoName={repoName}
              browseRef={browseRef}
              onAddSelection={handleAddSelection}
            />
          </ResizablePanel>
          {chatOpen && (
            <>
              <ResizableHandle withHandle />
              <ResizablePanel id="code-chat" defaultSize={384} minSize={280} maxSize={640}>
                <CodeChatPanel
                  contextItems={contextItems}
                  onRemoveContext={(id) => setContextItems((prev) => prev.filter((c) => c.id !== id))}
                  onClearContext={() => setContextItems([])}
                  onClose={() => setChatOpen(false)}
                  repoName={repoName}
                  browseRef={browseRef}
                  openPaths={openPaths}
                  onAddFile={handleAddFile}
                />
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>
        {!chatOpen && (
          <button
            type="button"
            title={t("askAboutCode")}
            onClick={() => setChatOpen(true)}
            className="flex w-9 shrink-0 items-start justify-center border-l pt-2.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <MessageSquareText className="size-4" />
          </button>
        )}
      </div>
    </div>
  )
}
