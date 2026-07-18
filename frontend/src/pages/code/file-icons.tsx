import { File, FileCode2, FileCog, FileJson2, FileTerminal, FileText } from "lucide-react"
import type { ComponentType } from "react"

type IconComponent = ComponentType<{ className?: string }>

const EXTENSION_ICONS: Record<string, IconComponent> = {
  c: FileCode2,
  cc: FileCode2,
  cpp: FileCode2,
  cxx: FileCode2,
  h: FileCode2,
  hpp: FileCode2,
  py: FileCode2,
  ts: FileCode2,
  tsx: FileCode2,
  js: FileCode2,
  jsx: FileCode2,
  json: FileJson2,
  md: FileText,
  rst: FileText,
  txt: FileText,
  sh: FileTerminal,
  bash: FileTerminal,
  yml: FileCog,
  yaml: FileCog,
  cmake: FileCog,
  toml: FileCog,
}

const FILENAME_ICONS: Record<string, IconComponent> = {
  "cmakelists.txt": FileCog,
  dockerfile: FileCog,
  makefile: FileCog,
}

export function getFileIcon(name: string): IconComponent {
  const lower = name.toLowerCase()
  if (FILENAME_ICONS[lower]) return FILENAME_ICONS[lower]

  const ext = lower.includes(".") ? lower.split(".").pop() : undefined
  return (ext && EXTENSION_ICONS[ext]) || File
}
