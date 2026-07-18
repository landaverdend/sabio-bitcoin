import { useQueries, useQuery } from "@tanstack/react-query"
import type { CommitInfo } from "@/hooks/use-repo-summary"

type CommitsResponse = {
  repo: string
  ref: string
  page: number
  page_size: number
  total: number
  author: string | null
  since: string | null
  until: string | null
  commits: CommitInfo[]
}

export type CommitFilters = {
  author?: string
  since?: string
  until?: string
}

async function fetchRepoCommits(
  repoName: string,
  ref: string,
  page: number,
  filters: CommitFilters,
): Promise<CommitsResponse> {
  const params = new URLSearchParams({ repo_name: repoName, ref, page: String(page) })
  if (filters.author) params.set("author", filters.author)
  if (filters.since) params.set("since", filters.since)
  if (filters.until) params.set("until", filters.until)
  const res = await fetch(`/repo/commits?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch commits: ${res.status}`)
  }
  return res.json()
}

function repoCommitsQuery(page: number, repoName: string, ref: string, filters: CommitFilters) {
  return {
    queryKey: [
      "repo-commits",
      repoName,
      ref,
      filters.author ?? null,
      filters.since ?? null,
      filters.until ?? null,
      page,
    ],
    queryFn: () => fetchRepoCommits(repoName, ref, page, filters),
    // A given page of history at a fixed ref (and filter set) never
    // changes -- same immutable-per-key rationale as the other repo hooks.
    staleTime: Infinity,
  }
}

export function useRepoCommits(page: number, repoName = "core", ref = "HEAD", filters: CommitFilters = {}) {
  return useQuery(repoCommitsQuery(page, repoName, ref, filters))
}

/** Pages 1..pageCount, fetched in parallel and already-fetched pages served
 * from cache -- backs a "load more" control without refetching earlier
 * pages each time. */
export function useRepoCommitPages(
  pageCount: number,
  repoName = "core",
  ref = "HEAD",
  filters: CommitFilters = {},
) {
  return useQueries({
    queries: Array.from({ length: pageCount }, (_, i) => repoCommitsQuery(i + 1, repoName, ref, filters)),
  })
}
