import { useQuery } from "@tanstack/react-query"

export type Branch = {
  name: string
  ref: string
  sha: string
  short_sha: string
  date: string
  is_default: boolean
}

type BranchesResponse = {
  repo: string
  branches: Branch[]
}

async function fetchRepoBranches(repoName: string): Promise<BranchesResponse> {
  const params = new URLSearchParams({ repo_name: repoName })
  const res = await fetch(`/repo/branches?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch branches: ${res.status}`)
  }
  return res.json()
}

export function useRepoBranches(repoName = "core") {
  return useQuery({
    queryKey: ["repo-branches", repoName],
    queryFn: () => fetchRepoBranches(repoName),
    staleTime: Infinity,
  })
}
