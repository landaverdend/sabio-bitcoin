import { useLocation } from "react-router-dom"

import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { useLocale, type Translator } from "@/lib/i18n"

function pageTitle(pathname: string, t: Translator): string {
  if (pathname.startsWith("/about")) return t("navAbout")
  if (pathname.includes("/commit/")) return t("pageCommit")
  if (pathname.includes("/commits")) return t("pageCommits")
  if (pathname.startsWith("/code")) return t("navCode")
  if (pathname.startsWith("/people/")) return t("pageContributor")
  if (pathname.startsWith("/people")) return t("navPeople")
  return t("navChat")
}

export function AppHeader() {
  const { pathname } = useLocation()
  const { t } = useLocale()
  const title = pageTitle(pathname, t)

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b bg-background px-3 md:px-4">
      <SidebarTrigger />
      <Separator orientation="vertical" className="h-4" />
      <p className="truncate text-sm font-medium">{title}</p>
    </header>
  )
}
