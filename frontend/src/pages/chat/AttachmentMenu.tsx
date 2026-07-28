import {
  ArrowLeft,
  FileImage,
  GitBranch,
  Loader2,
  Plus,
  Search,
  UserRound,
} from "lucide-react"
import { useState } from "react"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useDebouncedValue } from "@/hooks/use-debounced-value"
import { useLocale } from "@/lib/i18n"
import { REPOS } from "@/lib/repos"
import type {
  ChatAttachment,
  PersonAttachment,
  RepositoryAttachment,
} from "@/pages/chat/hooks/use-chat"
import { PersonAvatar } from "@/pages/people/PersonAvatar"
import type { PersonSummary } from "@/pages/people/hooks/use-people"
import { usePeople } from "@/pages/people/hooks/use-people"

type MenuPage = "main" | "repositories" | "people"

function personName(person: PersonSummary, unknownLabel: string): string {
  return (
    person.display_name ||
    person.github_username ||
    person.bitcointalk_username ||
    person.email ||
    unknownLabel
  )
}

function personDetail(person: PersonSummary): string | null {
  if (person.github_username) return `GitHub: @${person.github_username}`
  if (person.bitcointalk_username) {
    return `BitcoinTalk: ${person.bitcointalk_username}`
  }
  return person.email
}

function MenuHeader({
  title,
  onBack,
}: {
  title: string
  onBack: () => void
}) {
  const { t } = useLocale()
  return (
    <div className="flex h-10 items-center gap-2 border-b px-2">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        onClick={onBack}
        aria-label={t("back")}
      >
        <ArrowLeft className="size-4" />
      </Button>
      <span className="text-sm font-medium">{title}</span>
    </div>
  )
}

export function AttachmentMenu({
  disabled,
  attachments,
  onAdd,
  onChooseImages,
}: {
  disabled?: boolean
  attachments: ChatAttachment[]
  onAdd: (attachment: RepositoryAttachment | PersonAttachment) => void
  onChooseImages: () => void
}) {
  const { t } = useLocale()
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState<MenuPage>("main")
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebouncedValue(search.trim())
  const peopleQuery = usePeople(1, debouncedSearch || undefined, open && page === "people")

  const close = () => {
    setOpen(false)
    setPage("main")
    setSearch("")
  }

  const selectedRepoIds = new Set(
    attachments
      .filter((attachment) => attachment.kind === "repository")
      .map((attachment) => attachment.repoId),
  )
  const selectedPersonIds = new Set(
    attachments
      .filter((attachment) => attachment.kind === "person")
      .map((attachment) => attachment.personId),
  )

  let peopleContent: ReactNode
  if (peopleQuery.isLoading) {
    peopleContent = (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
      </div>
    )
  } else if (peopleQuery.isError) {
    peopleContent = (
      <p className="px-3 py-6 text-center text-sm text-destructive">
        {t("couldNotLoadPeople")}
      </p>
    )
  } else if (!peopleQuery.data || peopleQuery.data.people.length === 0) {
    peopleContent = (
      <p className="px-3 py-6 text-center text-sm text-muted-foreground">
        {t("noPeopleFound")}
      </p>
    )
  } else {
    peopleContent = peopleQuery.data.people.map((person) => {
      const label = personName(person, t("unknownPerson"))
      const selected = selectedPersonIds.has(person.id)
      const detail = personDetail(person)
      return (
        <button
          key={person.id}
          type="button"
          disabled={selected}
          onClick={() => {
            onAdd({
              id: crypto.randomUUID(),
              kind: "person",
              personId: person.id,
              label,
              githubUsername: person.github_username || undefined,
              bitcointalkUsername: person.bitcointalk_username || undefined,
            })
            close()
          }}
          className="flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left hover:bg-accent focus-visible:bg-accent focus-visible:outline-none disabled:opacity-50"
        >
          <PersonAvatar name={label} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{label}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {selected ? t("alreadyAttached") : detail || t("person")}
            </span>
          </span>
        </button>
      )
    })
  }

  return (
    <Popover
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen)
        if (!nextOpen) {
          setPage("main")
          setSearch("")
        }
      }}
    >
      <PopoverTrigger
        render={
          <Button
            type="button"
            variant="outline"
            size="icon"
            disabled={disabled}
            className="shrink-0 rounded-full"
            aria-label={t("addImagesOrContext")}
          />
        }
      >
        <Plus className="size-4" />
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="start"
        sideOffset={8}
        className="w-80 p-0"
        aria-label={t("addToMessage")}
      >
        {page === "main" && (
          <div className="p-1.5">
            <p className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
              {t("add")}
            </p>
            <button
              type="button"
              onClick={() => {
                close()
                onChooseImages()
              }}
              className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
            >
              <FileImage className="size-4 text-muted-foreground" />
              {t("images")}
              <span className="ml-auto text-xs text-muted-foreground">PNG, JPEG, WebP, GIF</span>
            </button>
            <button
              type="button"
              onClick={() => setPage("repositories")}
              className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
            >
              <GitBranch className="size-4 text-muted-foreground" />
              {t("repository")}
            </button>
            <button
              type="button"
              onClick={() => setPage("people")}
              className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
            >
              <UserRound className="size-4 text-muted-foreground" />
              {t("person")}
            </button>
          </div>
        )}

        {page === "repositories" && (
          <>
            <MenuHeader title={t("addRepository")} onBack={() => setPage("main")} />
            <div className="p-1.5">
              {REPOS.map((repo) => {
                const selected = selectedRepoIds.has(repo.id)
                return (
                  <button
                    key={repo.id}
                    type="button"
                    disabled={selected}
                    onClick={() => {
                      onAdd({
                        id: crypto.randomUUID(),
                        kind: "repository",
                        repoId: repo.id,
                        label: repo.label,
                      })
                      close()
                    }}
                    className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left hover:bg-accent focus-visible:bg-accent focus-visible:outline-none disabled:opacity-50"
                  >
                    <span className="flex size-8 items-center justify-center rounded-lg border bg-muted/30">
                      <GitBranch className="size-4 text-sabio" />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">{repo.label}</span>
                      <span className="block text-xs text-muted-foreground">
                        {selected ? t("alreadyAttached") : repo.id}
                      </span>
                    </span>
                  </button>
                )
              })}
            </div>
          </>
        )}

        {page === "people" && (
          <>
            <MenuHeader title={t("addPerson")} onBack={() => setPage("main")} />
            <div className="border-b p-2">
              <label className="flex items-center gap-2 rounded-md border px-2.5 py-1.5">
                <Search className="size-3.5 text-muted-foreground" />
                <span className="sr-only">{t("searchPeople")}</span>
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t("searchPeople")}
                  autoFocus
                  className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                />
              </label>
            </div>
            <div className="max-h-72 overflow-y-auto p-1.5">
              {peopleContent}
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}
