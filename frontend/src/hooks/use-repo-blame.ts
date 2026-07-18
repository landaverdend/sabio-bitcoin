import { useQuery } from "@tanstack/react-query"

export type BlameLine = {
  line: number
  sha: string
  author: string
  date: string | null
  summary: string
}

type BlameResponse = {
  repo: string
  ref: string
  path: string
  lines: BlameLine[]
}

async function fetchRepoBlame(repoName: string, ref: string, path: string): Promise<BlameResponse> {
  const params = new URLSearchParams({ repo_name: repoName, ref, path })
  const res = await fetch(`/repo/blame?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch blame: ${res.status}`)
  }
  return res.json()
}

/** enabled is passed in by the caller (currently: only when there's an
 * active path) -- unlike file content, blame is real work for git to
 * compute (~1.8s on this repo's biggest file), so it's not worth fetching
 * for every open tab up front, just the one being displayed. */
export function useRepoBlame(path: string | null, enabled: boolean, repoName = "core", ref = "HEAD") {
  return useQuery({
    queryKey: ["repo-blame", repoName, ref, path],
    queryFn: () => fetchRepoBlame(repoName, ref, path as string),
    enabled: enabled && path !== null,
    staleTime: Infinity,
  })
}
