// Mirrors agents/repos/github_tools.py's REPOS dict on the backend -- both
// sides need to agree on which repo_name values are valid. Adding a new
// implementation here is the only frontend change needed to make it
// selectable; every page/hook already threads repoName through generically.
export type RepoId = "core" | "knots" | "bips" | "secp256k1"

export const REPOS: { id: RepoId; label: string }[] = [
  { id: "core", label: "Bitcoin Core" },
  { id: "knots", label: "Bitcoin Knots" },
  { id: "bips", label: "BIPs" },
  { id: "secp256k1", label: "secp256k1" },
]

export const DEFAULT_REPO: RepoId = "core"

export function repoLabel(repoId: string): string {
  return REPOS.find((r) => r.id === repoId)?.label ?? repoId
}
