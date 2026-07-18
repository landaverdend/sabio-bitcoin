import { ChevronDown, Search, Users } from "lucide-react"
import { useMemo, useState } from "react"

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import type { Author } from "@/hooks/use-repo-authors"
import { useRepoAuthors } from "@/hooks/use-repo-authors"
import { cn } from "@/lib/utils"

// Deterministic color from a name, so the same author always gets the same
// placeholder-avatar color across renders/sessions without storing anything.
const AVATAR_COLORS = [
  "bg-red-500",
  "bg-orange-500",
  "bg-amber-500",
  "bg-lime-500",
  "bg-emerald-500",
  "bg-teal-500",
  "bg-cyan-500",
  "bg-blue-500",
  "bg-indigo-500",
  "bg-violet-500",
  "bg-fuchsia-500",
  "bg-pink-500",
]

function hashString(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i++) {
    hash = (hash << 5) - hash + value.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

function AuthorAvatar({ name }: { name: string }) {
  const color = AVATAR_COLORS[hashString(name) % AVATAR_COLORS.length]
  return (
    <span
      className={cn(
        "flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white",
        color,
      )}
    >
      {name.trim().charAt(0).toUpperCase() || "?"}
    </span>
  )
}

type AuthorFilterProps = {
  selected: string | null
  onSelect: (author: string | null) => void
}

export function AuthorFilter({ selected, onSelect }: AuthorFilterProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const { data } = useRepoAuthors()

  const authors: Author[] = data?.authors ?? []
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return authors
    return authors.filter((a) => a.name.toLowerCase().includes(query))
  }, [authors, search])

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setSearch("")
      }}
    >
      <PopoverTrigger
        className="flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <Users className="size-3.5" />
        {selected ?? "All users"}
        <ChevronDown className="size-3.5" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72">
        <div className="flex items-center gap-2 border-b px-2.5 py-2">
          <Search className="size-3.5 shrink-0 text-muted-foreground" />
          <input
            autoFocus
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Find a user..."
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="max-h-72 overflow-y-auto py-1">
          {filtered.map((author) => (
            <button
              key={author.name}
              type="button"
              onClick={() => {
                onSelect(author.name)
                setOpen(false)
              }}
              className={cn(
                "flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-sm hover:bg-accent",
                selected === author.name && "bg-accent",
              )}
            >
              <AuthorAvatar name={author.name} />
              <span className="truncate">{author.name}</span>
              <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                {author.commit_count.toLocaleString()}
              </span>
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="px-2.5 py-3 text-center text-sm text-muted-foreground">No users found.</p>
          )}
        </div>
        <button
          type="button"
          onClick={() => {
            onSelect(null)
            setOpen(false)
          }}
          className="block w-full border-t px-2.5 py-2 text-center text-sm text-primary hover:bg-accent"
        >
          View commits for all users
        </button>
      </PopoverContent>
    </Popover>
  )
}
