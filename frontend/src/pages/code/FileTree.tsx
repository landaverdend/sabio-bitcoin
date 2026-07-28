import { ChevronRight, Folder, FolderOpen, Plus } from "lucide-react"
import { useMemo } from "react"
import { Tree, type NodeRendererProps } from "react-arborist"
import useMeasure from "react-use-measure"

import { cn } from "@/lib/utils"
import { useLocale } from "@/lib/i18n"
import { buildTree, type FileNode } from "@/pages/code/build-tree"
import { getFileIcon } from "@/pages/code/file-icons"
import { useRepoTree } from "@/pages/code/hooks/use-repo-tree"

type FileTreeProps = {
  onSelectFile: (path: string) => void
  activePath: string | null
  repoName: string
  browseRef: string
  /** Optional: renders a hover "+" on each file row (not directories) that
   * adds it to the code chat panel's context tray. Omitted entirely when
   * the panel isn't open, rather than always reserving the space for it. */
  onAddToContext?: (path: string) => void
}

export function FileTree({ onSelectFile, activePath, repoName, browseRef, onAddToContext }: FileTreeProps) {
  const { t } = useLocale()
  const [measureRef, bounds] = useMeasure()
  const { data, isLoading, isError } = useRepoTree(repoName, browseRef)

  const tree = useMemo(() => (data ? buildTree(data.entries) : []), [data])

  // Defined inside FileTree (not module scope) so it closes over
  // onSelectFile, but memoized so its identity stays stable across
  // re-renders -- react-arborist treats a changed render-prop identity as a
  // different component type and remounts every row, which would be a real
  // cost with ~3k rows in the tree.
  const Node = useMemo(() => {
    function TreeNode({ node, style }: NodeRendererProps<FileNode>) {
      const isDir = node.data.type === "tree"
      let Icon = getFileIcon(node.data.name)
      if (isDir) {
        Icon = node.isOpen ? FolderOpen : Folder
      }

      return (
        <div
          style={style}
          onClick={() => (isDir ? node.toggle() : onSelectFile(node.data.id))}
          className={cn(
            "group flex cursor-pointer items-center gap-1.5 rounded-md px-2 text-sm select-none hover:bg-accent",
            node.isSelected && "bg-accent text-accent-foreground",
          )}
        >
          {isDir ? (
            <ChevronRight
              className={cn(
                "size-3.5 shrink-0 text-muted-foreground transition-transform",
                node.isOpen && "rotate-90",
              )}
            />
          ) : (
            <span className="w-3.5 shrink-0" />
          )}
          <Icon className="size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate">{node.data.name}</span>
          {!isDir && onAddToContext && (
            <button
              type="button"
              title={t("addToChat")}
              onClick={(e) => {
                e.stopPropagation()
                onAddToContext(node.data.id)
              }}
              className="hidden shrink-0 rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground group-hover:block"
            >
              <Plus className="size-3.5" />
            </button>
          )}
        </div>
      )
    }
    return TreeNode
  }, [onSelectFile, onAddToContext, t])

  return (
    <div ref={measureRef} className="h-full min-h-0 w-full overflow-hidden">
      {isLoading && <p className="p-3 text-sm text-muted-foreground">{t("loadingFiles")}</p>}
      {isError && <p className="p-3 text-sm text-destructive">{t("failedToLoadFiles")}</p>}
      {!isLoading && !isError && bounds.height > 0 && (
        <Tree
          data={tree}
          width={bounds.width}
          height={bounds.height}
          rowHeight={28}
          indent={16}
          openByDefault={false}
          selection={activePath ?? undefined}
          disableDrag
          disableDrop
          disableEdit
          className="text-sm"
        >
          {Node}
        </Tree>
      )}
    </div>
  )
}
