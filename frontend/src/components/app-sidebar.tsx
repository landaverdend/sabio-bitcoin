import { Bot, Code2, Loader2, MessageSquare, Plus, Trash2, Users } from "lucide-react"
import { NavLink, useLocation, useNavigate } from "react-router-dom"

import { NostrAuthButton } from "@/components/nostr-auth-button"
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
import { DEFAULT_REPO } from "@/lib/repos"
import { useAppChat } from "@/pages/chat/chat-context"

const items = [
  { to: "/chat", label: "Chat", icon: Bot },
  { to: `/code/${DEFAULT_REPO}`, label: "Code", icon: Code2, matchPrefix: "/code" },
  { to: "/people", label: "People", icon: Users },
]

export function AppSidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { pubkey } = useAuth()
  const {
    sessionId,
    sessions,
    isStreaming,
    isLoadingHistory,
    sessionError,
    newSession,
    loadSession,
    deleteSession,
  } = useAppChat()

  const startNewConversation = () => {
    newSession()
    navigate("/chat")
  }

  const openConversation = (nextSessionId: string) => {
    navigate("/chat")
    void loadSession(nextSessionId)
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <span className="truncate px-2 py-1 text-sm font-semibold group-data-[collapsible=icon]:hidden">
          Sabio
        </span>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigate</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    render={<NavLink to={item.to} />}
                    isActive={location.pathname.startsWith(item.matchPrefix ?? item.to)}
                    tooltip={item.label}
                  >
                    <item.icon />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        {pubkey && (
          <SidebarGroup className="group-data-[collapsible=icon]:hidden">
            <SidebarGroupLabel>Conversations</SidebarGroupLabel>
            <SidebarGroupAction
              onClick={startNewConversation}
              disabled={isStreaming || isLoadingHistory}
              aria-label="New conversation"
              title="New conversation"
            >
              <Plus />
            </SidebarGroupAction>
            <SidebarGroupContent>
              {isLoadingHistory && sessions.length === 0 ? (
                <div className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" />
                  Loading conversations
                </div>
              ) : sessions.length === 0 ? (
                <p className="px-2 py-2 text-xs text-muted-foreground">
                  Your conversations will appear here.
                </p>
              ) : (
                <SidebarMenu>
                  {sessions.map((session) => (
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
                        onClick={() => void deleteSession(session.session_id)}
                        disabled={isStreaming || isLoadingHistory}
                        aria-label={`Delete ${session.title}`}
                        title="Delete conversation"
                      >
                        <Trash2 />
                      </SidebarMenuAction>
                    </SidebarMenuItem>
                  ))}
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
        <ThemeToggle />
      </SidebarFooter>
    </Sidebar>
  )
}
