import { Check, ChevronDown } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import { REPOS } from "@/lib/repos"

type RepoSwitcherProps = {
  current: string
}

// Switching repos always lands on that repo's own default branch/HEAD --
// browsing state (open tabs, current ref) is tied to one repo's file space
// and doesn't carry over to a different codebase.
export function RepoSwitcher({ current }: RepoSwitcherProps) {
  const [open, setOpen] = useState(false)
  const currentLabel = REPOS.find((r) => r.id === current)?.label ?? current

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger className="flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 font-medium hover:bg-accent">
        {currentLabel}
        <ChevronDown className="size-3.5" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56 p-1">
        {REPOS.map((repo) => (
          <Link
            key={repo.id}
            to={`/code/${repo.id}`}
            onClick={() => setOpen(false)}
            className={cn(
              "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
              repo.id === current && "bg-accent",
            )}
          >
            <Check className={cn("size-3.5 shrink-0", repo.id !== current && "invisible")} />
            <span className="truncate">{repo.label}</span>
          </Link>
        ))}
      </PopoverContent>
    </Popover>
  )
}
