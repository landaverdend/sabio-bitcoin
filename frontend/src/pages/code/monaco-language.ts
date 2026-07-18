// Maps file extensions to Monaco's registered language ids (verified against
// monaco-editor's actual basic-languages + language/json,yaml directories --
// e.g. there's no "cmake" or "makefile" id despite Bitcoin Core using both
// extensively, so those fall back to plaintext rather than guessing wrong).
const EXTENSION_LANGUAGES: Record<string, string> = {
  c: "cpp",
  cc: "cpp",
  cpp: "cpp",
  cxx: "cpp",
  h: "cpp",
  hpp: "cpp",
  py: "python",
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  jsx: "javascript",
  json: "json",
  md: "markdown",
  sh: "shell",
  bash: "shell",
  yml: "yaml",
  yaml: "yaml",
  xml: "xml",
  html: "html",
  css: "css",
}

const FILENAME_LANGUAGES: Record<string, string> = {
  dockerfile: "dockerfile",
}

export function getMonacoLanguage(name: string): string {
  const lower = name.toLowerCase()
  if (FILENAME_LANGUAGES[lower]) return FILENAME_LANGUAGES[lower]

  const ext = lower.includes(".") ? lower.split(".").pop() : undefined
  return (ext && EXTENSION_LANGUAGES[ext]) || "plaintext"
}
