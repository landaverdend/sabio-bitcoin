import type { Page, Route } from "@playwright/test"

export type SessionSummary = {
  session_id: string
  title: string
  last_update_time: number
}

export type MockPerson = {
  id: number
  display_name: string | null
  email: string | null
  github_username: string | null
  bitcointalk_username: string | null
  message_count: number
  linked_count: number
}

type HistoryEvent =
  | {
      type: "user_message"
      message: string
      context: []
      attachments: []
    }
  | { type: "text"; author: string; text: string }
  | { type: "done" }

export type MockApiState = {
  sessions: SessionSummary[]
  histories: Record<string, HistoryEvent[]>
  people: MockPerson[]
  deletedSessionIds: string[]
}

const JSON_HEADERS = {
  "access-control-allow-origin": "*",
  "content-type": "application/json",
}

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  })
}

export function sse(...events: object[]): string {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("")
}

export async function installMockApi(
  page: Page,
  initial: Partial<Pick<MockApiState, "sessions" | "histories" | "people">> = {},
): Promise<MockApiState> {
  const state: MockApiState = {
    sessions: initial.sessions ? [...initial.sessions] : [],
    histories: { ...(initial.histories ?? {}) },
    people: initial.people ? [...initial.people] : [],
    deletedSessionIds: [],
  }

  await page.route("**/ping", (route) => json(route, { message: "pong" }))
  await page.route("**/auth/me", (route) =>
    json(route, {
      pubkey: "e2e-pubkey-000000000000000000000000000000000000000000000000000000",
    }),
  )

  await page.route(/\/chat\/sessions(?:\/[^/?]+)?(?:\?.*)?$/, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const match = url.pathname.match(/^\/chat\/sessions(?:\/([^/]+))?$/)
    if (!match) {
      await route.continue()
      return
    }

    const sessionId = match[1]
    if (!sessionId && request.method() === "GET") {
      await json(route, state.sessions)
      return
    }
    if (sessionId && request.method() === "GET") {
      await json(route, {
        session_id: sessionId,
        events: state.histories[sessionId] ?? [],
      })
      return
    }
    if (sessionId && request.method() === "DELETE") {
      state.sessions = state.sessions.filter(
        (session) => session.session_id !== sessionId,
      )
      state.deletedSessionIds.push(sessionId)
      await json(route, { ok: true })
      return
    }
    if (sessionId && request.method() === "PATCH") {
      const { title } = request.postDataJSON() as { title: string }
      state.sessions = state.sessions.map((session) =>
        session.session_id === sessionId ? { ...session, title } : session,
      )
      await json(route, { session_id: sessionId, title })
      return
    }

    await json(route, { detail: "Unhandled mocked session request" }, 405)
  })

  await page.route(/\/people(?:\?.*)?$/, async (route) => {
    if (route.request().resourceType() === "document") {
      await route.continue()
      return
    }
    await json(route, {
      page: 1,
      page_size: 50,
      total: state.people.length,
      people: state.people,
    })
  })

  return state
}
