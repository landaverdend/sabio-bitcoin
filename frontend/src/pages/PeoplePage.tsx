import { Search } from "lucide-react"
import { useMemo, useState } from "react"
import { Link } from "react-router-dom"

import { ListSkeleton } from "@/components/ListRowSkeleton"
import { Button } from "@/components/ui/button"
import { PersonAvatar } from "@/pages/people/PersonAvatar"
import type { PersonSummary } from "@/pages/people/hooks/use-people"
import { usePeoplePages } from "@/pages/people/hooks/use-people"

function personName(person: PersonSummary): string {
  return person.display_name || person.github_username || person.bitcointalk_username || person.email || "Unknown"
}

function personSubtitle(person: PersonSummary): string | null {
  const parts: string[] = []
  if (person.email) parts.push(person.email)
  if (person.github_username) parts.push(`GitHub: ${person.github_username}`)
  if (person.bitcointalk_username) parts.push(`BitcoinTalk: ${person.bitcointalk_username}`)
  return parts.length > 0 ? parts.join(" · ") : null
}

export default function PeoplePage() {
  const [search, setSearch] = useState("")
  const [pageCount, setPageCount] = useState(1)
  const q = search.trim() || undefined

  const pages = usePeoplePages(pageCount, q)
  const people = useMemo(() => pages.flatMap((p) => p.data?.people ?? []), [pages])
  const total = pages[0]?.data?.total ?? 0
  const isLoading = pages.some((p) => p.isLoading)
  const hasMore = people.length < total

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="flex shrink-0 flex-col gap-3 border-b px-6 py-4">
        <h1 className="text-xl font-semibold">People</h1>
        <div className="flex max-w-sm items-center gap-2 rounded-md border px-2.5 py-1.5">
          <Search className="size-3.5 shrink-0 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPageCount(1)
            }}
            placeholder="Search by name, email, or username..."
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
      </div>

      <div className="flex-1 px-6 py-4">
        <div className="overflow-hidden rounded-md border">
          {isLoading && people.length === 0 ? (
            <ListSkeleton rows={8} avatar trailing />
          ) : (
            <>
              {people.map((person, i) => (
                <Link
                  key={person.id}
                  to={`/people/${person.id}`}
                  className={`flex items-center gap-3 px-4 py-3 hover:bg-accent ${i > 0 ? "border-t" : ""}`}
                >
                  <PersonAvatar name={personName(person)} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{personName(person)}</p>
                    {personSubtitle(person) && (
                      <p className="truncate text-xs text-muted-foreground">{personSubtitle(person)}</p>
                    )}
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {person.message_count.toLocaleString()} message{person.message_count === 1 ? "" : "s"}
                  </span>
                </Link>
              ))}
              {people.length === 0 && (
                <p className="px-4 py-6 text-center text-sm text-muted-foreground">No people found.</p>
              )}
            </>
          )}
        </div>

        {hasMore && (
          <Button
            variant="outline"
            className="mt-4"
            disabled={isLoading}
            onClick={() => setPageCount((n) => n + 1)}
          >
            {isLoading ? "Loading…" : "Load more"}
          </Button>
        )}
      </div>
    </div>
  )
}
