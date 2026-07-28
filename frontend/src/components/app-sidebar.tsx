import { Code2, Loader2, MessageCircle, MessageSquare, Plus, SquarePen, Trash2, Users } from "lucide-react"
import { useState } from "react"
import { NavLink, useLocation, useNavigate } from "react-router-dom"

import { NostrAuthButton } from "@/components/nostr-auth-button"
import { SabioMark } from "@/components/sabio-mark"
import { LanguageToggle } from "@/components/language-toggle"
import { ThemeToggle } from "@/components/theme-toggle"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { useAuth } from "@/lib/auth"
import { useLocale, type TranslationKey } from "@/lib/i18n"
import { DEFAULT_REPO } from "@/lib/repos"
import { useAppChat } from "@/pages/chat/chat-context"

const items = [
  { to: "/chat", labelKey: "navChat", icon: MessageCircle },
  { to: `/code/${DEFAULT_REPO}`, labelKey: "navCode", icon: Code2, matchPrefix: "/code" },
  { to: "/people", labelKey: "navPeople", icon: Users },
] as const satisfies ReadonlyArray<{
  to: string
  labelKey: TranslationKey
  icon: typeof MessageCircle
  matchPrefix?: string
}>

export function AppSidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { pubkey } = useAuth()
  const { t } = useLocale()
  const {
    sessionId,
    sessions,
    isStreaming,
    isLoadingHistory,
    sessionError,
    newSession,
    loadSession,
    deleteSession,
    renameSession,
  } = useAppChat()

  // Which session's row is showing an inline title editor, if any -- only
  // one at a time, so the row itself can own the draft text instead of
  // keying a whole map of drafts by session id.
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [draftTitle, setDraftTitle] = useState("")

  const startNewConversation = () => {
    newSession()
    navigate("/chat")
  }

  const openConversation = (nextSessionId: string) => {
    navigate("/chat")
    void loadSession(nextSessionId)
  }

  const startRename = (sessionId: string, currentTitle: string) => {
    setRenamingId(sessionId)
    setDraftTitle(currentTitle)
  }

  const commitRename = () => {
    const id = renamingId
    const title = draftTitle
    setRenamingId(null)
    if (!id || !title.trim()) return
    void renameSession(id, title)
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-12 justify-center border-b p-2">
        <div className="flex items-center gap-2 px-0.5">
          <SabioMark className="size-6 shrink-0" />
          <p className="truncate text-sm font-semibold group-data-[collapsible=icon]:hidden">
            Sabio
          </p>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup className="pt-2">
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    render={<NavLink to={item.to} />}
                    isActive={location.pathname.startsWith(
                      "matchPrefix" in item ? item.matchPrefix : item.to,
                    )}
                    tooltip={t(item.labelKey)}
                  >
                    <item.icon />
                    <span>{t(item.labelKey)}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        {pubkey && (
          <SidebarGroup className="group-data-[collapsible=icon]:hidden">
            <SidebarGroupLabel>{t("conversations")}</SidebarGroupLabel>
            <SidebarGroupAction
              onClick={startNewConversation}
              disabled={isStreaming || isLoadingHistory}
              aria-label={t("newConversation")}
              title={t("newConversation")}
            >
              <Plus />
            </SidebarGroupAction>
            <SidebarGroupContent>
              {isLoadingHistory && sessions.length === 0 ? (
                <div className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" />
                  {t("loadingConversations")}
                </div>
              ) : sessions.length === 0 ? (
                <p className="px-2 py-2 text-xs text-muted-foreground">
                  {t("noConversations")}
                </p>
              ) : (
                <SidebarMenu>
                  {sessions.map((session) =>
                    renamingId === session.session_id ? (
                      <SidebarMenuItem key={session.session_id}>
                        <div className="flex items-center gap-2 rounded-md px-2 py-1.5">
                          <MessageSquare className="size-4 shrink-0 text-sidebar-foreground/70" />
                          <input
                            autoFocus
                            value={draftTitle}
                            onChange={(e) => setDraftTitle(e.target.value)}
                            onBlur={commitRename}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") e.currentTarget.blur()
                              else if (e.key === "Escape") setRenamingId(null)
                            }}
                            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                          />
                        </div>
                      </SidebarMenuItem>
                    ) : (
                      <SidebarMenuItem key={session.session_id}>
                        <SidebarMenuButton
                          onClick={() => openConversation(session.session_id)}
                          disabled={isStreaming || isLoadingHistory}
                          isActive={
                            location.pathname.startsWith("/chat") &&
                            session.session_id === sessionId
                          }
                          tooltip={session.title}
                        >
                          <MessageSquare />
                          <span>{session.title}</span>
                        </SidebarMenuButton>
                        <SidebarMenuAction
                          showOnHover
                          className="right-6"
                          onClick={() => startRename(session.session_id, session.title)}
                          disabled={isStreaming || isLoadingHistory}
                          aria-label={`${t("renameConversation")}: ${session.title}`}
                          title={t("renameConversation")}
                        >
                          <SquarePen />
                        </SidebarMenuAction>
                        <SidebarMenuAction
                          showOnHover
                          onClick={() => void deleteSession(session.session_id)}
                          disabled={isStreaming || isLoadingHistory}
                          aria-label={`${t("deleteConversation")}: ${session.title}`}
                          title={t("deleteConversation")}
                        >
                          <Trash2 />
                        </SidebarMenuAction>
                      </SidebarMenuItem>
                    ),
                  )}
                </SidebarMenu>
              )}
              {sessionError && (
                <p className="px-2 pt-2 text-xs text-destructive">{sessionError}</p>
              )}
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
      <SidebarFooter>
        <NostrAuthButton />
        <LanguageToggle />
        <ThemeToggle />
      </SidebarFooter>
    </Sidebar>
  )
}
