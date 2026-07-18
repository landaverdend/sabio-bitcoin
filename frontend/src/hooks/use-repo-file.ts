import { useQueries, useQuery } from "@tanstack/react-query"

export type FileResponse = {
  repo: string
  ref: string
  path: string
  content: string | null
  binary: boolean
}

async function fetchRepoFile(repoName: string, ref: string, path: string): Promise<FileResponse> {
  const params = new URLSearchParams({ repo_name: repoName, ref, path })
  const res = await fetch(`/repo/file?${params}`)
  if (!res.ok) {
    throw new Error(`failed to fetch file: ${res.status}`)
  }
  return res.json()
}

function repoFileQuery(path: string, repoName: string, ref: string) {
  return {
    queryKey: ["repo-file", repoName, ref, path],
    queryFn: () => fetchRepoFile(repoName, ref, path),
    // Immutable per (repo, ref, path) -- same rationale as useRepoTree.
    staleTime: Infinity,
  }
}

export function useRepoFile(path: string | null, repoName = "core", ref = "HEAD") {
  return useQuery({
    ...repoFileQuery(path ?? "", repoName, ref),
    enabled: path !== null,
  })
}

/** One query per open path, fetched in parallel and cached independently --
 * lets every open tab's content be ready even though only the active tab's
 * is actually rendered into the editor. */
export function useRepoFiles(paths: string[], repoName = "core", ref = "HEAD") {
  return useQueries({
    queries: paths.map((path) => repoFileQuery(path, repoName, ref)),
  })
}
