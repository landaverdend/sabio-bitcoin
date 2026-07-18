import { Check, ChevronDown, GitBranch } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { formatRelativeDate } from "@/lib/format-date"
import { cn } from "@/lib/utils"
import { useRepoBranches } from "@/pages/code/hooks/use-repo-branches"

type BranchSwitcherProps = {
  current: string
  // Where the default branch's link points (e.g. "/code"), and the prefix
  // non-default branches are appended to (e.g. "/code/tree" ->
  // "/code/tree/origin/29.x") -- callers browsing files vs. commit history
  // land on different routes for the same branch.
  defaultHref: string
  branchBasePath: string
}

export function BranchSwitcher({ current, defaultHref, branchBasePath }: BranchSwitcherProps) {
  const [open, setOpen] = useState(false)
  const { data } = useRepoBranches()
  const branches = data?.branches ?? []

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger className="flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-muted-foreground hover:bg-accent hover:text-foreground">
        <GitBranch className="size-4" />
        {current}
        <ChevronDown className="size-3.5" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-1">
        <div className="max-h-80 overflow-y-auto">
          {branches.map((branch) => (
            <Link
              key={branch.name}
              to={branch.is_default ? defaultHref : `${branchBasePath}/${branch.ref}`}
              onClick={() => setOpen(false)}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
                branch.name === current && "bg-accent",
              )}
            >
              <Check className={cn("size-3.5 shrink-0", branch.name !== current && "invisible")} />
              <span className="min-w-0 flex-1 truncate font-mono">{branch.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {formatRelativeDate(branch.date)}
              </span>
            </Link>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
