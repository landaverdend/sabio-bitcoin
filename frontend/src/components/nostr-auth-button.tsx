import { KeyRound, LogOut } from "lucide-react"
import { useState } from "react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar"
import { useAuth } from "@/lib/auth"

function truncate(pubkey: string): string {
  return `${pubkey.slice(0, 8)}…${pubkey.slice(-4)}`
}

export function NostrAuthButton() {
  const { pubkey, checking, login, logout } = useAuth()
  const [error, setError] = useState<string | null>(null)

  // Nothing rendered while the initial /auth/me check is in flight -- a
  // "Connect Nostr" button that flashes for a moment on every load (even
  // for someone already logged in) would be worse than a brief blank slot.
  if (checking) return null

  if (!pubkey) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            tooltip="Log in with Nostr"
            onClick={() => {
              setError(null)
              login().catch((err: Error) => setError(err.message))
            }}
          >
            <KeyRound />
            <span>Connect Nostr</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
        {error && (
          <p className="px-2 pt-1 text-xs text-destructive group-data-[collapsible=icon]:hidden">{error}</p>
        )}
      </SidebarMenu>
    )
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger render={<SidebarMenuButton tooltip={pubkey} />}>
            <KeyRound />
            <span className="font-mono">{truncate(pubkey)}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start">
            <DropdownMenuItem onClick={() => void logout()}>
              <LogOut />
              <span>Log out</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
