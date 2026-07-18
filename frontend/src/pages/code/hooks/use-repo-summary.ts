import { useQuery } from "@tanstack/react-query"

export type CommitInfo = {
  sha: string
  short_sha: string
  author: string
  date: string
  message: string
}

type SummaryResponse = {
  repo: string
  ref: string
  branch: string
  commit_count: number
  latest_commit: CommitInfo
}

async function fetchRepoSummary(repoName: string, ref: string): Promise<SummaryResponse> {
  const params = new URLSearchParams({ repo_name: repoName, ref })
  const res = await fetch(`/repo/summary?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch repo summary: ${res.status}`)
  }
  return res.json()
}

export function useRepoSummary(repoName = "core", ref = "HEAD") {
  return useQuery({
    queryKey: ["repo-summary", repoName, ref],
    queryFn: () => fetchRepoSummary(repoName, ref),
    // Same "HEAD could move mid-session" caveat as useRepoTree -- acceptable
    // for a local dev tool.
    staleTime: Infinity,
  })
}
