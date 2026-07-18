import { useQuery } from "@tanstack/react-query"

export type CommitFile = {
  path: string
  old_path: string | null
  status: "added" | "modified" | "deleted" | "renamed"
  additions: number
  deletions: number
}

export type CommitDetail = {
  repo: string
  sha: string
  short_sha: string
  author: string
  date: string
  message: string
  parents: string[]
  parent_short: string | null
  files: CommitFile[]
}

async function fetchRepoCommit(repoName: string, sha: string): Promise<CommitDetail> {
  const params = new URLSearchParams({ repo_name: repoName, sha })
  const res = await fetch(`/repo/commit?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch commit: ${res.status}`)
  }
  return res.json()
}

export function useRepoCommit(sha: string, repoName = "core") {
  return useQuery({
    queryKey: ["repo-commit", repoName, sha],
    queryFn: () => fetchRepoCommit(repoName, sha),
    staleTime: Infinity,
  })
}
