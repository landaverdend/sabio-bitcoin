import { FileTree } from "@/pages/code/FileTree"

export default function CodePage() {
  return (
    <div className="flex h-full min-h-0">
      <aside className="flex h-full w-64 shrink-0 flex-col border-r">
        <div className="flex h-9 shrink-0 items-center border-b px-3 text-xs font-medium text-muted-foreground">
          Files
        </div>
        <div className="min-h-0 flex-1 overflow-hidden p-1">
          <FileTree />
        </div>
      </aside>
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
        <h1 className="text-xl font-semibold">Code</h1>
        <p className="text-muted-foreground">Select a file to view its contents.</p>
      </div>
    </div>
  )
}
