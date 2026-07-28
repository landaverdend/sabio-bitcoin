import { expect, test, type Page, type Route } from "@playwright/test"

import { installMockApi, sse } from "./mock-api"

const PIXEL_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
)

function monitorClientErrors(page: Page): string[] {
  const errors: string[] = []
  page.on("pageerror", (error) => errors.push(error.message))
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text())
  })
  return errors
}

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

async function fulfillJson(route: Route, body: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  })
}

test("language switch translates the interface and persists after reload", async ({
  page,
}) => {
  const clientErrors = monitorClientErrors(page)
  await installMockApi(page)

  await page.goto("/chat")
  await expect(page.getByRole("heading", { name: "Ask Sabio" })).toBeVisible()

  await page.getByRole("switch", { name: "Use Spanish" }).click()

  await expect(page.locator("html")).toHaveAttribute("lang", "es")
  await expect(
    page.getByRole("heading", { name: "Pregúntale a Sabio" }),
  ).toBeVisible()
  await expect(page.getByRole("link", { name: "Código" })).toBeVisible()
  await expect(page.getByText("Sabio puede cometer errores.")).toBeVisible()

  await page.reload()
  await expect(page.locator("html")).toHaveAttribute("lang", "es")
  await expect(
    page.getByRole("heading", { name: "Pregúntale a Sabio" }),
  ).toBeVisible()

  await page.getByRole("link", { name: "Personas" }).click()
  await expect(page.getByRole("heading", { name: "Personas" })).toBeVisible()
  await expect(
    page.getByPlaceholder("Buscar por nombre, correo o usuario…"),
  ).toBeVisible()
  expect(clientErrors).toEqual([])
})

test("Spanish chat sends the locale and renders an SSE response", async ({
  page,
}) => {
  const clientErrors = monitorClientErrors(page)
  await installMockApi(page)
  let streamPayload: Record<string, unknown> | null = null

  await page.route("**/chat/stream", async (route) => {
    streamPayload = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse(
        { type: "text", author: "root", text: "Respuesta verificada." },
        { type: "done" },
      ),
    })
  })

  await page.goto("/chat")
  await page.getByRole("switch", { name: "Use Spanish" }).click()
  await page.getByPlaceholder("Escribe a Sabio…").fill("¿Qué cambió?")
  await page.getByRole("button", { name: "Enviar mensaje" }).click()

  await expect(page.getByText("Respuesta verificada.")).toBeVisible()
  await expect.poll(() => streamPayload).not.toBeNull()
  expect(streamPayload).toMatchObject({
    locale: "es",
    message: "¿Qué cambió?",
    context: [],
    attachments: [],
  })
  expect(streamPayload?.session_id).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  )
  expect(streamPayload?.run_id).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  )
  expect(clientErrors).toEqual([])
})

test("exact PR discussion reads render as linked source cards", async ({
  page,
}) => {
  const clientErrors = monitorClientErrors(page)
  await installMockApi(page)
  const sourceUrl =
    "https://github.com/bitcoin/bitcoin/pull/28984#discussion_r1776"

  await page.route("**/chat/stream", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse(
        {
          type: "tool_call",
          author: "sabio_repos",
          tool: "get_pr_discussion_item",
          args: {
            repo_name: "core",
            number: 28984,
            kind: "review_comment",
            item_id: 1776,
          },
        },
        {
          type: "tool_result",
          author: "sabio_repos",
          tool: "get_pr_discussion_item",
        },
        {
          type: "github_discussion_source",
          repo: "bitcoin/bitcoin",
          pr_number: 28984,
          pr_title: "Add package relay",
          kind: "review_comment",
          item_id: "1776",
          author: "glozow",
          created_at: "2026-07-01T12:00:00+00:00",
          excerpt: "Could this package relay condition be simplified?",
          path: "src/net_processing.cpp",
          line: 700,
          source_url: sourceUrl,
        },
        {
          type: "text",
          author: "sabio_repos",
          text: "The reviewer asked whether the condition could be simplified.",
        },
        { type: "done" },
      ),
    })
  })

  await page.goto("/chat")
  await page.getByPlaceholder("Message Sabio…").fill("What did the reviewer say?")
  await page.getByRole("button", { name: "Send message" }).click()

  await expect(page.getByText("Reading a PR comment")).toBeVisible()
  const source = page.getByRole("link", { name: /glozow/ })
  await expect(source).toContainText("bitcoin/bitcoin#28984")
  await expect(source).toContainText("src/net_processing.cpp:L700")
  await expect(source).toHaveAttribute("href", sourceUrl)
  await expect(
    page.getByText(
      "The reviewer asked whether the condition could be simplified.",
    ),
  ).toBeVisible()
  expect(clientErrors).toEqual([])
})

test("image attachments are previewed and serialized into the chat request", async ({
  page,
}) => {
  const clientErrors = monitorClientErrors(page)
  await installMockApi(page)
  let streamPayload: Record<string, unknown> | null = null

  await page.route("**/chat/stream", async (route) => {
    streamPayload = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse({ type: "text", author: "root", text: "Image received." }, { type: "done" }),
    })
  })

  await page.goto("/chat")
  const fileChooserPromise = page.waitForEvent("filechooser")
  await page
    .getByRole("button", { name: "Add images or context" })
    .click()
  await page.getByRole("button", { name: /Images/ }).click()
  const fileChooser = await fileChooserPromise
  await fileChooser.setFiles({
    name: "pixel.png",
    mimeType: "image/png",
    buffer: PIXEL_PNG,
  })

  await expect(page.getByRole("img", { name: "pixel.png" })).toBeVisible()
  await page.getByPlaceholder("Message Sabio…").fill("Inspect this image")
  await page.getByRole("button", { name: "Send message" }).click()
  await expect(page.getByText("Image received.")).toBeVisible()

  await expect.poll(() => streamPayload).not.toBeNull()
  const attachments = streamPayload?.attachments as Array<Record<string, unknown>>
  expect(attachments).toHaveLength(1)
  expect(attachments[0]).toMatchObject({
    kind: "image",
    name: "pixel.png",
    mime_type: "image/png",
    size: PIXEL_PNG.length,
  })
  expect(attachments[0].data_url).toMatch(/^data:image\/png;base64,/)
  expect(clientErrors).toEqual([])
})

test("repository and person context can be selected and sent", async ({
  page,
}) => {
  const clientErrors = monitorClientErrors(page)
  await installMockApi(page, {
    people: [
      {
        id: 42,
        display_name: "Alice Example",
        email: "alice@example.com",
        github_username: "alice",
        bitcointalk_username: null,
        message_count: 12,
        linked_count: 1,
      },
    ],
  })
  let streamPayload: Record<string, unknown> | null = null

  await page.route("**/chat/stream", async (route) => {
    streamPayload = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse(
        { type: "text", author: "root", text: "Context received." },
        { type: "done" },
      ),
    })
  })

  await page.goto("/chat")
  const addButton = page.getByRole("button", {
    name: "Add images or context",
  })

  await addButton.click()
  await page.getByRole("button", { name: "Repository", exact: true }).click()
  await page.getByRole("button", { name: /Bitcoin Core/ }).click()

  await addButton.click()
  await page.getByRole("button", { name: "Person", exact: true }).click()
  await page.getByRole("button", { name: /Alice Example/ }).click()

  await page.getByPlaceholder("Message Sabio…").fill("Use this context")
  await page.getByRole("button", { name: "Send message" }).click()
  await expect(page.getByText("Context received.")).toBeVisible()

  await expect.poll(() => streamPayload).not.toBeNull()
  expect(streamPayload?.attachments).toEqual([
    {
      kind: "repository",
      repo_id: "core",
      label: "Bitcoin Core",
    },
    {
      kind: "person",
      person_id: 42,
      label: "Alice Example",
      github_username: "alice",
    },
  ])
  expect(clientErrors).toEqual([])
})

test("Stop aborts the active stream and addresses the matching backend run", async ({
  page,
}) => {
  const clientErrors = monitorClientErrors(page)
  await installMockApi(page)
  const streamStarted = deferred()
  const releaseStream = deferred()
  let streamPayload: Record<string, unknown> | null = null
  let stopPayload: Record<string, unknown> | null = null

  await page.route("**/chat/stream", async (route) => {
    streamPayload = route.request().postDataJSON() as Record<string, unknown>
    streamStarted.resolve()
    await releaseStream.promise
    await route.abort("aborted").catch(() => undefined)
  })
  await page.route("**/chat/stop", async (route) => {
    stopPayload = route.request().postDataJSON() as Record<string, unknown>
    releaseStream.resolve()
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ stopped: true }),
    })
  })

  await page.goto("/chat")
  await page.getByPlaceholder("Message Sabio…").fill("Keep working")
  await page.getByRole("button", { name: "Send message" }).click()
  await streamStarted.promise

  await page.getByRole("button", { name: "Stop generating" }).click()
  await expect.poll(() => stopPayload).not.toBeNull()
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible()

  expect(stopPayload).toEqual({
    session_id: streamPayload?.session_id,
    run_id: streamPayload?.run_id,
  })
  expect(clientErrors).toEqual([])
})

test("stored sessions reload and can be deleted from the sidebar", async ({
  page,
}) => {
  const clientErrors = monitorClientErrors(page)
  const firstId = "11111111-1111-4111-8111-111111111111"
  const secondId = "22222222-2222-4222-8222-222222222222"
  const state = await installMockApi(page, {
    sessions: [
      { session_id: firstId, title: "First topic", last_update_time: 2 },
      { session_id: secondId, title: "Second topic", last_update_time: 1 },
    ],
    histories: {
      [firstId]: [
        { type: "user_message", message: "First question", context: [], attachments: [] },
        { type: "text", author: "root", text: "First stored answer" },
        { type: "done" },
      ],
      [secondId]: [
        { type: "user_message", message: "Second question", context: [], attachments: [] },
        { type: "text", author: "root", text: "Second stored answer" },
        { type: "done" },
      ],
    },
  })

  await page.goto("/chat")
  await expect(page.getByText("First stored answer")).toBeVisible()

  const firstConversation = page.getByRole("button", {
    name: "First topic",
    exact: true,
  })
  await firstConversation.hover()
  await page
    .getByRole("button", { name: "Rename conversation: First topic" })
    .click()
  const renameInput = page.locator('input:not([type])')
  await expect(renameInput).toHaveValue("First topic")
  await renameInput.fill("Renamed topic")
  await renameInput.press("Enter")
  await expect(
    page.getByRole("button", { name: "Renamed topic", exact: true }),
  ).toBeVisible()

  const secondConversation = page.getByRole("button", {
    name: "Second topic",
    exact: true,
  })
  await secondConversation.click()
  await expect(page.getByText("Second stored answer")).toBeVisible()

  await secondConversation.hover()
  await page
    .getByRole("button", { name: "Delete conversation: Second topic" })
    .click()

  await expect(page.getByText("First stored answer")).toBeVisible()
  await expect(page.getByRole("button", { name: "Second topic" })).toHaveCount(0)
  expect(state.deletedSessionIds).toEqual([secondId])
  expect(clientErrors).toEqual([])
})

test("people detail switches between commit and communication data", async ({
  page,
}) => {
  const clientErrors = monitorClientErrors(page)
  await installMockApi(page, {
    people: [
      {
        id: 42,
        display_name: "Alice Example",
        email: "alice@example.com",
        github_username: "alice",
        bitcointalk_username: null,
        message_count: 1,
        linked_count: 0,
      },
    ],
  })

  await page.route(/\/people\/42$/, async (route) => {
    if (route.request().resourceType() === "document") {
      await route.continue()
      return
    }
    await fulfillJson(route, {
      id: 42,
      display_name: "Alice Example",
      email: "alice@example.com",
      github_username: "alice",
      bitcointalk_username: null,
      channels: [{ channel: "mailing_list", count: 1 }],
      identities: [
        {
          id: 42,
          display_name: "Alice Example",
          email: "alice@example.com",
          github_username: "alice",
          bitcointalk_username: null,
        },
      ],
    })
  })
  await page.route(/\/repo\/commits\?.*$/, (route) =>
    fulfillJson(route, {
      repo: "core",
      ref: "HEAD",
      page: 1,
      page_size: 50,
      total: 1,
      author: "alice",
      since: null,
      until: null,
      q: null,
      commits: [
        {
          sha: "abcdef1234567890",
          short_sha: "abcdef1",
          author: "Alice Example",
          date: "2026-07-01T12:00:00+00:00",
          message: "Clarify package relay",
        },
      ],
    }),
  )
  await page.route(/\/people\/42\/messages\?.*$/, (route) =>
    fulfillJson(route, {
      page: 1,
      page_size: 50,
      total: 1,
      messages: [
        {
          id: 7,
          channel: "mailing_list",
          title: "Re: Package relay",
          author: "alice@example.com",
          posted_at: "2026-07-02T12:00:00+00:00",
          url: "https://example.com/message/7",
          snippet: "A concrete review observation.",
        },
      ],
    }),
  )

  await page.goto("/people/42")
  await expect(page.getByRole("heading", { name: "Alice Example" })).toBeVisible()
  await expect(page.getByText("Clarify package relay")).toBeVisible()

  await page.getByRole("tab", { name: /Mailing List/ }).click()
  await expect(page.getByText("Re: Package relay")).toBeVisible()
  await expect(page.getByText("A concrete review observation.")).toBeVisible()
  expect(clientErrors).toEqual([])
})

test("code tree and commit date controls still respond to interaction", async ({
  page,
}) => {
  const clientErrors = monitorClientErrors(page)
  await installMockApi(page)
  const commitQueries: URL[] = []
  const commit = {
    sha: "abcdef1234567890",
    short_sha: "abcdef1",
    author: "Alice Example",
    date: "2026-07-01T12:00:00+00:00",
    message: "Clarify package relay",
  }

  await page.route(/\/repo\/summary\?.*$/, (route) =>
    fulfillJson(route, {
      repo: "core",
      ref: "HEAD",
      branch: "master",
      commit_count: 1,
      latest_commit: commit,
    }),
  )
  await page.route(/\/repo\/branches\?.*$/, (route) =>
    fulfillJson(route, {
      repo: "core",
      branches: [
        {
          name: "master",
          ref: "HEAD",
          sha: commit.sha,
          short_sha: commit.short_sha,
          date: commit.date,
          is_default: true,
        },
      ],
    }),
  )
  await page.route(/\/repo\/tree\?.*$/, (route) =>
    fulfillJson(route, {
      repo: "core",
      ref: "HEAD",
      entries: [
        { path: "src", type: "tree" },
        { path: "src/main.cpp", type: "blob" },
      ],
    }),
  )
  await page.route(/\/repo\/file\?.*$/, (route) =>
    fulfillJson(route, {
      repo: "core",
      ref: "HEAD",
      path: "src/main.cpp",
      content: "int main() { return 0; }\n",
      binary: false,
    }),
  )
  await page.route(/\/repo\/blame\?.*$/, (route) =>
    fulfillJson(route, {
      repo: "core",
      ref: "HEAD",
      path: "src/main.cpp",
      lines: [],
    }),
  )
  await page.route(/\/repo\/authors\?.*$/, (route) =>
    fulfillJson(route, {
      repo: "core",
      ref: "HEAD",
      authors: [{ name: "Alice Example", commit_count: 1 }],
    }),
  )
  await page.route(/\/repo\/commits\?.*$/, (route) => {
    commitQueries.push(new URL(route.request().url()))
    return fulfillJson(route, {
      repo: "core",
      ref: "HEAD",
      page: 1,
      page_size: 50,
      total: 1,
      author: null,
      since: null,
      until: null,
      q: null,
      commits: [commit],
    })
  })

  await page.goto("/code/core")
  await expect(page.getByText("Select a file to view its contents.")).toBeVisible()
  await page.getByText("src", { exact: true }).click()
  await page.getByText("main.cpp", { exact: true }).click()
  await expect(page.getByRole("tab", { name: /main\.cpp/ })).toBeVisible()

  await page.goto("/code/core/commits")
  await expect(page.getByText("Clarify package relay")).toBeVisible()
  await page.getByRole("button", { name: "All time" }).click()
  await page.getByRole("button", { name: "Today", exact: true }).click()

  await expect.poll(() => commitQueries.length).toBeGreaterThan(1)
  const filteredQuery = commitQueries.at(-1)
  expect(filteredQuery?.searchParams.get("since")).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  expect(filteredQuery?.searchParams.get("until")).toBe(
    filteredQuery?.searchParams.get("since"),
  )
  expect(clientErrors).toEqual([])
})
