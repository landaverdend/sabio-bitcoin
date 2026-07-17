import { useEffect } from "react"
import { useRepoTree } from "@/hooks/use-repo-tree"

export default function CodePage() {
  const { data } = useRepoTree()

  useEffect(() => {
    if (data) {
      console.log(data)
    }
  }, [data])

  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
      <h1 className="text-xl font-semibold">Code</h1>
      <p className="text-muted-foreground">
        Browsing the local Bitcoin Core checkout is coming soon.
      </p>
    </div>
  )
}
