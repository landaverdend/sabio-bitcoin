import { useLocation } from "react-router-dom"

import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"

function pageTitle(pathname: string): string {
  if (pathname.includes("/commit/")) return "Commit"
  if (pathname.includes("/commits")) return "Commits"
  if (pathname.startsWith("/code")) return "Code"
  if (pathname.startsWith("/people/")) return "Contributor"
  if (pathname.startsWith("/people")) return "People"
  return "Chat"
}

export function AppHeader() {
  const { pathname } = useLocation()

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b bg-background px-3 md:px-4">
      <SidebarTrigger />
      <Separator orientation="vertical" className="h-4" />
      <p className="truncate text-sm font-medium">{pageTitle(pathname)}</p>
    </header>
  )
}
