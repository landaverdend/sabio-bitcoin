import { ChevronRight, Folder, FolderOpen } from "lucide-react"
import { useMemo } from "react"
import { Tree, type NodeRendererProps } from "react-arborist"
import useMeasure from "react-use-measure"

import { useRepoTree } from "@/hooks/use-repo-tree"
import { cn } from "@/lib/utils"
import { buildTree, type FileNode } from "@/pages/code/build-tree"
import { getFileIcon } from "@/pages/code/file-icons"

type FileTreeProps = {
  onSelectFile: (path: string) => void
  activePath: string | null
  browseRef: string
}

export function FileTree({ onSelectFile, activePath, browseRef }: FileTreeProps) {
  const [measureRef, bounds] = useMeasure()
  const { data, isLoading, isError } = useRepoTree("core", browseRef)

  const tree = useMemo(() => (data ? buildTree(data.entries) : []), [data])

  // Defined inside FileTree (not module scope) so it closes over
  // onSelectFile, but memoized so its identity stays stable across
  // re-renders -- react-arborist treats a changed render-prop identity as a
  // different component type and remounts every row, which would be a real
  // cost with ~3k rows in the tree.
  const Node = useMemo(() => {
    function TreeNode({ node, style }: NodeRendererProps<FileNode>) {
      const isDir = node.data.type === "tree"
      const Icon = isDir ? (node.isOpen ? FolderOpen : Folder) : getFileIcon(node.data.name)

      return (
        <div
          style={style}
          onClick={() => (isDir ? node.toggle() : onSelectFile(node.data.id))}
          className={cn(
            "flex cursor-pointer items-center gap-1.5 rounded-md px-2 text-sm select-none hover:bg-accent",
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
          <span className="truncate">{node.data.name}</span>
        </div>
      )
    }
    return TreeNode
  }, [onSelectFile])

  return (
    <div ref={measureRef} className="h-full min-h-0 w-full overflow-hidden">
      {isLoading && <p className="p-3 text-sm text-muted-foreground">Loading files…</p>}
      {isError && <p className="p-3 text-sm text-destructive">Failed to load files.</p>}
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
