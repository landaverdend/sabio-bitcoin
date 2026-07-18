import { useQuery } from "@tanstack/react-query"

export type Author = {
  name: string
  commit_count: number
}

type AuthorsResponse = {
  repo: string
  ref: string
  authors: Author[]
}

async function fetchRepoAuthors(repoName: string, ref: string): Promise<AuthorsResponse> {
  const params = new URLSearchParams({ repo_name: repoName, ref })
  const res = await fetch(`/repo/authors?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch authors: ${res.status}`)
  }
  return res.json()
}

export function useRepoAuthors(repoName = "core", ref = "HEAD") {
  return useQuery({
    queryKey: ["repo-authors", repoName, ref],
    queryFn: () => fetchRepoAuthors(repoName, ref),
    staleTime: Infinity,
  })
}
