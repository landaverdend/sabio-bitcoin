import { createContext, useCallback, useContext, useEffect, useState } from "react"
import type { ReactNode } from "react"

// Minimal NIP-07 surface -- the actual extension (Alby, nos2x, etc.) injects
// this; we only ever call the two methods a login needs.
type UnsignedNostrEvent = {
  kind: number
  created_at: number
  tags: string[][]
  content: string
  pubkey: string
}
type SignedNostrEvent = UnsignedNostrEvent & { id: string; sig: string }

declare global {
  interface Window {
    nostr?: {
      getPublicKey: () => Promise<string>
      signEvent: (event: UnsignedNostrEvent) => Promise<SignedNostrEvent>
    }
  }
}

const AUTH_EVENT_KIND = 22242 // NIP-42 "client authentication"

type AuthContextValue = {
  pubkey: string | null
  // Distinguishes "haven't checked yet" from "checked, not logged in" --
  // without it, the sidebar would flash a "Connect Nostr" button for
  // everyone for a moment on every load, even already-logged-in users.
  checking: boolean
  login: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [pubkey, setPubkey] = useState<string | null>(null)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    fetch("/auth/me", { credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { pubkey: string } | null) => setPubkey(data?.pubkey ?? null))
      .catch(() => setPubkey(null))
      .finally(() => setChecking(false))
  }, [])

  const login = useCallback(async () => {
    if (!window.nostr) {
      throw new Error("No Nostr extension found -- install one (e.g. Alby or nos2x) to log in.")
    }
    const nostr = window.nostr

    const challengeRes = await fetch("/auth/challenge", { method: "POST", credentials: "include" })
    if (!challengeRes.ok) throw new Error("Could not start login -- try again.")
    const { nonce }: { nonce: string } = await challengeRes.json()

    const nostrPubkey = await nostr.getPublicKey()
    // Signed client-side by the extension -- the private key never leaves
    // it, and never reaches this app or the server.
    const signed = await nostr.signEvent({
      kind: AUTH_EVENT_KIND,
      created_at: Math.floor(Date.now() / 1000),
      tags: [["challenge", nonce]],
      content: "",
      pubkey: nostrPubkey,
    })

    const verifyRes = await fetch("/auth/verify", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event: signed }),
    })
    if (!verifyRes.ok) {
      const body = await verifyRes.json().catch(() => null)
      throw new Error(body?.detail || "Login failed -- signature could not be verified.")
    }
    const data: { pubkey: string } = await verifyRes.json()
    setPubkey(data.pubkey)
  }, [])

  const logout = useCallback(async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "include" })
    setPubkey(null)
  }, [])

  return <AuthContext.Provider value={{ pubkey, checking, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
