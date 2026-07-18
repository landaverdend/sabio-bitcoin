import type { TreeEntry } from "@/pages/code/hooks/use-repo-tree"

export type FileNode = {
  id: string
  name: string
  type: "blob" | "tree"
  children?: FileNode[]
}

function sortChildren(nodes: FileNode[]): FileNode[] {
  nodes.sort((a, b) => {
    if (a.type !== b.type) return a.type === "tree" ? -1 : 1
    return a.name.localeCompare(b.name)
  })
  for (const node of nodes) {
    if (node.children) sortChildren(node.children)
  }
  return nodes
}

/** Flat {path, type} entries (as returned by GET /repo/tree) -> a nested
 * tree react-arborist can render, directories-before-files/alphabetical at
 * each level like GitHub's own file view. */
export function buildTree(entries: readonly TreeEntry[]): FileNode[] {
  const root: FileNode[] = []
  const dirs = new Map<string, FileNode>()

  // git ls-tree -r -t already lists a directory before its contents, but
  // sort by path depth defensively so parent lookups below never miss.
  const sorted = [...entries].sort(
    (a, b) => a.path.split("/").length - b.path.split("/").length,
  )

  for (const entry of sorted) {
    const parts = entry.path.split("/")
    const name = parts[parts.length - 1]
    const parentPath = parts.slice(0, -1).join("/")

    const node: FileNode = {
      id: entry.path,
      name,
      type: entry.type,
      ...(entry.type === "tree" ? { children: [] } : {}),
    }

    if (entry.type === "tree") {
      dirs.set(entry.path, node)
    }

    const parent = parentPath ? dirs.get(parentPath) : undefined
    if (parent?.children) {
      parent.children.push(node)
    } else {
      root.push(node)
    }
  }

  return sortChildren(root)
}
