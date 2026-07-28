import { Search } from "lucide-react"
import { useMemo, useState } from "react"
import type { ReactNode } from "react"
import { Link } from "react-router-dom"

import { ListSkeleton } from "@/components/ListRowSkeleton"
import { Button } from "@/components/ui/button"
import { useDebouncedValue } from "@/hooks/use-debounced-value"
import { useLocale } from "@/lib/i18n"
import { PersonAvatar } from "@/pages/people/PersonAvatar"
import type { PersonSummary } from "@/pages/people/hooks/use-people"
import { usePeoplePages } from "@/pages/people/hooks/use-people"

function personName(person: PersonSummary, unknownLabel: string): string {
  return (
    person.display_name ||
    person.github_username ||
    person.bitcointalk_username ||
    person.email ||
    unknownLabel
  )
}

function personSubtitle(
  person: PersonSummary,
  linkedIdentity: string,
  linkedIdentities: string,
): string | null {
  const parts: string[] = []
  if (person.email) parts.push(person.email)
  if (person.github_username) parts.push(`GitHub: ${person.github_username}`)
  if (person.bitcointalk_username) parts.push(`BitcoinTalk: ${person.bitcointalk_username}`)
  // Other rows exist for the same real person (a different email, a
  // BitcoinTalk-only identity, etc.) but aren't shown as separate list
  // entries -- see backend/people.py's canonical_person_id grouping.
  if (person.linked_count > 0) {
    parts.push(person.linked_count === 1 ? linkedIdentity : linkedIdentities)
  }
  return parts.length > 0 ? parts.join(" · ") : null
}

export default function PeoplePage() {
  const { locale, t } = useLocale()
  const [search, setSearch] = useState("")
  const [pageCount, setPageCount] = useState(1)
  const debouncedSearch = useDebouncedValue(search)
  const q = debouncedSearch.trim() || undefined

  const pages = usePeoplePages(pageCount, q)
  const people = useMemo(() => pages.flatMap((p) => p.data?.people ?? []), [pages])
  const total = pages[0]?.data?.total ?? 0
  const isLoading = pages.some((p) => p.isLoading)
  const hasMore = people.length < total

  let peopleContent: ReactNode
  if (isLoading && people.length === 0) {
    peopleContent = <ListSkeleton rows={8} avatar trailing />
  } else {
    peopleContent = (
      <>
        {people.map((person, index) => {
          const subtitle = personSubtitle(
            person,
            t("linkedIdentity"),
            t("linkedIdentities", { count: person.linked_count }),
          )
          return (
            <Link
              key={person.id}
              to={`/people/${person.id}`}
              className={`flex items-center gap-3 px-4 py-3 hover:bg-accent ${index > 0 ? "border-t" : ""}`}
            >
              <PersonAvatar name={personName(person, t("unknown"))} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">
                  {personName(person, t("unknown"))}
                </p>
                {subtitle && (
                  <p className="truncate text-xs text-muted-foreground">
                    {subtitle}
                  </p>
                )}
              </div>
              <span className="shrink-0 text-xs text-muted-foreground">
                {person.message_count === 1
                  ? t("oneMessage")
                  : t("messageCount", {
                      count: person.message_count.toLocaleString(locale),
                    })}
              </span>
            </Link>
          )
        })}
        {people.length === 0 && (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">
            {t("noPeopleFound")}
          </p>
        )}
      </>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="flex shrink-0 flex-col gap-3 border-b px-6 py-4">
        <h1 className="text-xl font-semibold">{t("people")}</h1>
        <div className="flex max-w-sm items-center gap-2 rounded-md border px-2.5 py-1.5">
          <Search className="size-3.5 shrink-0 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPageCount(1)
            }}
            placeholder={t("searchPeopleLong")}
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
      </div>

      <div className="flex-1 px-6 py-4">
        <div className="overflow-hidden rounded-md border">
          {peopleContent}
        </div>

        {hasMore && (
          <Button
            variant="outline"
            className="mt-4"
            disabled={isLoading}
            onClick={() => setPageCount((n) => n + 1)}
          >
            {isLoading ? t("loading") : t("loadMore")}
          </Button>
        )}
      </div>
    </div>
  )
}
