import Editor, { type Monaco } from "@monaco-editor/react"
import { Plus, X } from "lucide-react"
import type { editor as MonacoEditor } from "monaco-editor"
import { useEffect, useRef, useState } from "react"

import { useTheme } from "@/components/theme-provider"
import { formatRelativeDate } from "@/lib/format-date"
import { cn } from "@/lib/utils"
import { getFileIcon } from "@/pages/code/file-icons"
import { useRepoBlame } from "@/pages/code/hooks/use-repo-blame"
import { useRepoFiles } from "@/pages/code/hooks/use-repo-file"
import { getMonacoLanguage } from "@/pages/code/monaco-language"

type FileViewerProps = {
  openPaths: string[]
  activePath: string | null
  onSelectTab: (path: string) => void
  onCloseTab: (path: string) => void
  repoName: string
  browseRef: string
  /** Omitted entirely when the code chat panel isn't open. */
  onAddSelection?: (path: string, startLine: number, endLine: number, content: string) => void
}

type PendingSelection = { startLine: number; endLine: number; top: number; left: number }

function basename(path: string): string {
  return path.split("/").pop() ?? path
}

export function FileViewer({
  openPaths,
  activePath,
  onSelectTab,
  onCloseTab,
  repoName,
  browseRef,
  onAddSelection,
}: FileViewerProps) {
  const { theme } = useTheme()
  const isDark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)

  const editorRef = useRef<MonacoEditor.IStandaloneCodeEditor | null>(null)
  const monacoRef = useRef<Monaco | null>(null)
  const decorationsRef = useRef<MonacoEditor.IEditorDecorationsCollection | null>(null)
  // The line the cursor is currently on -- blame shows only for this line,
  // matching GitLens/VS Code's actual default (always on, follows the
  // cursor), not a manual per-file toggle.
  const [currentLine, setCurrentLine] = useState(1)
  // A non-empty selection's line range and where to float the "add to chat"
  // button -- null whenever the selection is empty (just a cursor) or the
  // panel that would consume it isn't open (onAddSelection undefined).
  const [pendingSelection, setPendingSelection] = useState<PendingSelection | null>(null)

  const results = useRepoFiles(openPaths, repoName, browseRef)
  const activeIndex = activePath ? openPaths.indexOf(activePath) : -1
  const activeResult = activeIndex >= 0 ? results[activeIndex] : undefined

  const blameResult = useRepoBlame(activePath, activePath !== null, repoName, browseRef)

  // Re-sync on tab switch: @monaco-editor/react swaps the bound model when
  // `path` changes, and the new model's cursor position may not line up
  // with whatever onDidChangeCursorPosition last reported for the old one.
  // The decorations collection also needs recreating, not reusing -- it
  // stays targeted at whichever model existed when it was created, so
  // calling .set() on the old one after a model swap silently no-ops
  // against a model that's no longer visible.
  useEffect(() => {
    setCurrentLine(editorRef.current?.getPosition()?.lineNumber ?? 1)
    setPendingSelection(null)
    decorationsRef.current?.clear()
    decorationsRef.current = null
  }, [activePath])

  useEffect(() => {
    const editor = editorRef.current
    const monaco = monacoRef.current
    const model = editor?.getModel()
    if (!editor || !monaco || !model) return

    const entry = blameResult.data?.lines.find((line) => line.line === currentLine)
    if (!entry) {
      decorationsRef.current?.clear()
      return
    }

    const col = model.getLineMaxColumn(entry.line)
    const decoration: MonacoEditor.IModelDeltaDecoration = {
      range: new monaco.Range(entry.line, col, entry.line, col),
      options: {
        // Decorations with a collapsed (zero-width) range -- exactly what a
        // single injection point is -- are hidden by default; showIfCollapsed
        // is what makes Monaco render them anyway.
        showIfCollapsed: true,
        after: {
          content: `  ${entry.author}, ${formatRelativeDate(entry.date)} • ${entry.summary}`,
          inlineClassName: "blame-annotation",
        },
      },
    }

    if (!decorationsRef.current) {
      decorationsRef.current = editor.createDecorationsCollection()
    }
    decorationsRef.current.set([decoration])
  }, [currentLine, blameResult.data, activePath])

  if (openPaths.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
        <h1 className="text-xl font-semibold">Code</h1>
        <p className="text-muted-foreground">Select a file to view its contents.</p>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">

      <div role="tablist" className="flex h-9 shrink-0 items-stretch overflow-x-auto border-b">
        {openPaths.map((path) => {
          const name = basename(path)
          const Icon = getFileIcon(name)
          const isActive = path === activePath
          return (
            <div
              key={path}
              role="tab"
              aria-selected={isActive}
              onClick={() => onSelectTab(path)}
              className={cn(
                "flex shrink-0 cursor-pointer items-center gap-1.5 border-r px-3 text-sm text-muted-foreground hover:bg-accent",
                isActive && "bg-background text-foreground",
              )}
            >
              <Icon className="size-3.5 shrink-0" />
              <span className="max-w-40 truncate">{name}</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onCloseTab(path)
                }}
                className="ml-1 rounded p-0.5 hover:bg-muted"
              >
                <X className="size-3.5" />
              </button>
            </div>
          )
        })}
      </div>
      <div className="relative min-h-0 flex-1">
        {activeResult?.isLoading && (
          <p className="p-3 text-sm text-muted-foreground">Loading…</p>
        )}
        {activeResult?.isError && (
          <p className="p-3 text-sm text-destructive">Failed to load file.</p>
        )}
        {activeResult?.data?.binary && (
          <p className="p-3 text-sm text-muted-foreground">Binary file -- cannot display.</p>
        )}
        {activeResult?.data && !activeResult.data.binary && activePath && (
          <Editor
            path={activePath}
            value={activeResult.data.content ?? ""}
            language={getMonacoLanguage(basename(activePath))}
            theme={isDark ? "vs-dark" : "vs"}
            options={{ readOnly: true, minimap: { enabled: false } }}
            height="100%"
            onMount={(editor, monaco) => {
              editorRef.current = editor
              monacoRef.current = monaco
              setCurrentLine(editor.getPosition()?.lineNumber ?? 1)
              editor.onDidChangeCursorPosition((e) => setCurrentLine(e.position.lineNumber))
              editor.onDidChangeCursorSelection((e) => {
                if (!onAddSelection || e.selection.isEmpty()) {
                  setPendingSelection(null)
                  return
                }
                const { startLineNumber, endLineNumber, endColumn } = e.selection
                // A selection ending at column 1 of a line hasn't actually
                // included that line's content (just its leading edge) --
                // floating the button past it, and later slicing one line
                // too many into the attached excerpt, would both be wrong.
                const endLine = endColumn === 1 && endLineNumber > startLineNumber ? endLineNumber - 1 : endLineNumber
                const pos = editor.getScrolledVisiblePosition({ lineNumber: endLine, column: 1 })
                if (!pos) return
                setPendingSelection({ startLine: startLineNumber, endLine, top: pos.top, left: pos.left })
              })
            }}
          />
        )}
        {pendingSelection && onAddSelection && activePath && (
          <button
            type="button"
            style={{ top: pendingSelection.top, left: pendingSelection.left }}
            className="absolute z-10 flex items-center gap-1 rounded-md border border-sabio/30 bg-sabio/10 px-1.5 py-0.5 text-xs text-sabio shadow-sm hover:bg-sabio/20"
            onClick={() => {
              const model = editorRef.current?.getModel()
              if (!model) return
              const { startLine, endLine } = pendingSelection
              const content = model.getValueInRange({
                startLineNumber: startLine,
                startColumn: 1,
                endLineNumber: endLine,
                endColumn: model.getLineMaxColumn(endLine),
              })
              onAddSelection(activePath, startLine, endLine, content)
              setPendingSelection(null)
            }}
          >
            <Plus className="size-3" />
            Add to chat
          </button>
        )}
      </div>
    </div>
  )
}
