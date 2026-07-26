import { Plus, Search } from "lucide-react"
import { useMemo, useState } from "react"

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { getFileIcon } from "@/pages/code/file-icons"
import { useRepoTree } from "@/pages/code/hooks/use-repo-tree"

const MAX_RESULTS = 40

function basename(path: string): string {
  return path.split("/").pop() ?? path
}

type FilePickerButtonProps = {
  repoName: string
  browseRef: string
  /** Currently open editor tabs -- listed first when there's no search
   * text, same "recent/relevant first" ordering VS Code's own file-picker
   * uses, since a file you already have open is the likely thing to want. */
  openPaths: string[]
  onSelectFile: (path: string) => void
}

export function FilePickerButton({ repoName, browseRef, openPaths, onSelectFile }: FilePickerButtonProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const { data } = useRepoTree(repoName, browseRef)

  const files = useMemo(() => (data ? data.entries.filter((e) => e.type === "blob").map((e) => e.path) : []), [data])

  const results = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) {
      // No search yet -- lead with what's already open, then pad out with
      // whatever else exists, rather than an alphabetical dump of the
      // thousands of files a repo this size actually has.
      const rest = files.filter((f) => !openPaths.includes(f)).slice(0, MAX_RESULTS - openPaths.length)
      return [...openPaths, ...rest]
    }
    return files.filter((f) => f.toLowerCase().includes(query)).slice(0, MAX_RESULTS)
  }, [files, openPaths, search])

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setSearch("")
      }}
    >
      <PopoverTrigger
        title="Add a file"
        className="flex size-9 shrink-0 items-center justify-center rounded-xl border text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <Plus className="size-4" />
      </PopoverTrigger>
      <PopoverContent align="start" side="top" className="w-80 p-0">
        <div className="flex items-center gap-2 border-b px-2.5 py-2">
          <Search className="size-3.5 shrink-0 text-muted-foreground" />
          <input
            autoFocus
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Find a file..."
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="max-h-72 overflow-y-auto py-1">
          {results.map((path) => {
            const Icon = getFileIcon(basename(path))
            return (
              <button
                key={path}
                type="button"
                onClick={() => {
                  onSelectFile(path)
                  setOpen(false)
                  setSearch("")
                }}
                className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-sm hover:bg-accent"
              >
                <Icon className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">{basename(path)}</span>
                <span className="ml-auto min-w-0 shrink truncate text-xs text-muted-foreground">{path}</span>
              </button>
            )
          })}
          {results.length === 0 && (
            <p className="px-2.5 py-3 text-center text-sm text-muted-foreground">No files found.</p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
