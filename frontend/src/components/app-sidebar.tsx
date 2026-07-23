import { Bot, Code2, MessagesSquare, Users } from "lucide-react"
import { NavLink, useLocation } from "react-router-dom"

import { ThemeToggle } from "@/components/theme-toggle"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { DEFAULT_REPO } from "@/lib/repos"

const items = [
  { to: "/chat", label: "Chat", icon: Bot },
  { to: `/code/${DEFAULT_REPO}`, label: "Code", icon: Code2, matchPrefix: "/code" },
  { to: "/comms", label: "Comms", icon: MessagesSquare },
  { to: "/people", label: "People", icon: Users },
]

export function AppSidebar() {
  const location = useLocation()

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
      </SidebarContent>
      <SidebarFooter>
        <ThemeToggle />
      </SidebarFooter>
    </Sidebar>
  )
}
