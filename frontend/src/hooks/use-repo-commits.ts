import { useQueries, useQuery } from "@tanstack/react-query"
import type { CommitInfo } from "@/hooks/use-repo-summary"

type CommitsResponse = {
  repo: string
  ref: string
  page: number
  page_size: number
  total: number
  commits: CommitInfo[]
}

async function fetchRepoCommits(repoName: string, ref: string, page: number): Promise<CommitsResponse> {
  const params = new URLSearchParams({ repo_name: repoName, ref, page: String(page) })
  const res = await fetch(`/repo/commits?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch commits: ${res.status}`)
  }
  return res.json()
}

function repoCommitsQuery(page: number, repoName: string, ref: string) {
  return {
    queryKey: ["repo-commits", repoName, ref, page],
    queryFn: () => fetchRepoCommits(repoName, ref, page),
    // A given page of history at a fixed ref never changes -- same
    // immutable-per-key rationale as the other repo hooks.
    staleTime: Infinity,
  }
}

export function useRepoCommits(page: number, repoName = "core", ref = "HEAD") {
  return useQuery(repoCommitsQuery(page, repoName, ref))
}

/** Pages 1..pageCount, fetched in parallel and already-fetched pages served
 * from cache -- backs a "load more" control without refetching earlier
 * pages each time. */
export function useRepoCommitPages(pageCount: number, repoName = "core", ref = "HEAD") {
  return useQueries({
    queries: Array.from({ length: pageCount }, (_, i) => repoCommitsQuery(i + 1, repoName, ref)),
  })
}
