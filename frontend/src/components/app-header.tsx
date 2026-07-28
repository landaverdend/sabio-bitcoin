import { useLocation } from "react-router-dom"

import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { useLocale } from "@/lib/i18n"

export function AppHeader() {
  const { pathname } = useLocation()
  const { t } = useLocale()
  const title = pathname.includes("/commit/")
    ? t("pageCommit")
    : pathname.includes("/commits")
      ? t("pageCommits")
      : pathname.startsWith("/code")
        ? t("navCode")
        : pathname.startsWith("/people/")
          ? t("pageContributor")
          : pathname.startsWith("/people")
            ? t("navPeople")
            : t("navChat")

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b bg-background px-3 md:px-4">
      <SidebarTrigger />
      <Separator orientation="vertical" className="h-4" />
      <p className="truncate text-sm font-medium">{title}</p>
    </header>
  )
}
