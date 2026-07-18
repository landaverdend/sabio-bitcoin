import { useQuery } from "@tanstack/react-query"

export type TreeEntry = {
  path: string
  type: "blob" | "tree"
}

type TreeResponse = {
  repo: string
  ref: string
  entries: TreeEntry[]
}

async function fetchRepoTree(repoName: string, ref: string): Promise<TreeResponse> {
  const params = new URLSearchParams({ repo_name: repoName, ref })
  const res = await fetch(`/repo/tree?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch repo tree: ${res.status}`)
  }
  return res.json()
}

export function useRepoTree(repoName = "core", ref = "HEAD") {
  return useQuery({
    queryKey: ["repo-tree", repoName, ref],
    queryFn: () => fetchRepoTree(repoName, ref),
    // A tree at a fixed ref never changes -- a different ref is already a
    // different cache key -- so there's nothing to revalidate by refetching
    // on every remount (TanStack's default). Doesn't account for "HEAD"
    // itself moving mid-session (a new commit landing while the app is
    // open); acceptable for a local dev tool, revisit if that matters.
    staleTime: Infinity,
  })
}
