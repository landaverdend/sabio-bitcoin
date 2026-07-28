import Editor from "@monaco-editor/react"
import { ExternalLink, FileCode2, X } from "lucide-react"

import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { useLocale } from "@/lib/i18n"
import { repoLabel } from "@/lib/repos"
import type { SourceReference } from "@/pages/chat/hooks/use-chat"
import { useRepoFile } from "@/pages/code/hooks/use-repo-file"
import { getMonacoLanguage } from "@/pages/code/monaco-language"

type SourceCodePanelProps = {
  source: SourceReference
  onClose: () => void
}

function basename(path: string): string {
  return path.split("/").pop() ?? path
}

export function SourceCodePanel({ source, onClose }: SourceCodePanelProps) {
  const { theme } = useTheme()
  const { t } = useLocale()
  const isDark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)
  const file = useRepoFile(source.path, source.repo, source.ref)
  const lineLabel =
    source.startLine === source.endLine
      ? t("line", { line: source.startLine })
      : t("lines", { start: source.startLine, end: source.endLine })
  const editorKey = `${source.repo}:${source.ref}:${source.path}:${source.startLine}:${source.endLine}`

  return (
    <aside className="flex h-full min-h-0 flex-col bg-background">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
        <FileCode2 className="size-4 shrink-0 text-sabio" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium" title={source.path}>
            {source.path}
          </p>
          <p className="truncate text-[11px] text-muted-foreground">
            {repoLabel(source.repo)} · {source.ref} · {lineLabel}
          </p>
        </div>
        <Button
          render={
            <a
              href={source.githubUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={t("openCitedLines")}
              title={t("openOnGitHub")}
            />
          }
          variant="ghost"
          size="icon-sm"
        >
          <ExternalLink className="size-3.5" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onClose}
          aria-label={t("closeSource")}
        >
          <X className="size-3.5" />
        </Button>
      </div>

      <div className="min-h-0 flex-1">
        {file.isLoading && (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {t("loadingSource")}
          </div>
        )}
        {file.isError && (
          <div className="flex h-full items-center justify-center p-4 text-center text-sm text-destructive">
            {t("sourceLoadError")}
          </div>
        )}
        {file.data?.binary && (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {t("binarySource")}
          </div>
        )}
        {file.data && !file.data.binary && (
          <Editor
            key={editorKey}
            path={editorKey}
            value={file.data.content ?? ""}
            language={getMonacoLanguage(basename(source.path))}
            theme={isDark ? "vs-dark" : "vs"}
            height="100%"
            options={{
              readOnly: true,
              minimap: { enabled: false },
              folding: false,
              renderLineHighlight: "none",
              scrollBeyondLastLine: false,
              wordWrap: "off",
            }}
            onMount={(editor, monaco) => {
              const model = editor.getModel()
              if (!model) return
              const startLine = Math.min(Math.max(source.startLine, 1), model.getLineCount())
              const endLine = Math.min(
                Math.max(source.endLine, startLine),
                model.getLineCount(),
              )
              editor.createDecorationsCollection([
                {
                  range: new monaco.Range(startLine, 1, endLine, 1),
                  options: {
                    isWholeLine: true,
                    className: "source-line-highlight",
                  },
                },
              ])
              editor.revealLinesInCenter(startLine, endLine)
            }}
          />
        )}
      </div>
    </aside>
  )
}
