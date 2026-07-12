import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from git import GitCommandError, InvalidGitRepositoryError, Repo

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_repos")

REPOS = {
    "core": {
        "path": os.getenv("REPO_BITCOIN_CORE"),
        "github_slug": os.getenv("GITHUB_REPO_CORE", "bitcoin/bitcoin"),
    },
}


def sync_repo(name: str, path: str, github_slug: str) -> None:
    repo_path = Path(path)

    if not repo_path.exists():
        url = f"https://github.com/{github_slug}.git"
        logger.info(f"[{name}] no local clone found, cloning {url} -> {repo_path}")
        Repo.clone_from(url, repo_path)
        logger.info(f"[{name}] clone complete")
        return

    repo = Repo(repo_path)
    if repo.is_dirty(untracked_files=False):
        logger.warning(f"[{name}] working tree has local changes, skipping to avoid clobbering them")
        return

    before = repo.head.commit.hexsha[:12]
    repo.remotes.origin.fetch()
    repo.git.merge("--ff-only", "@{u}")
    after = repo.head.commit.hexsha[:12]

    if before == after:
        logger.info(f"[{name}] already up to date at {after}")
    else:
        logger.info(f"[{name}] updated {before} -> {after}")


def main() -> None:
    exit_code = 0
    for name, cfg in REPOS.items():
        if not cfg["path"]:
            logger.warning(f"[{name}] no local path configured (check .env), skipping")
            continue
        try:
            sync_repo(name, cfg["path"], cfg["github_slug"])
        except (GitCommandError, InvalidGitRepositoryError) as e:
            logger.error(f"[{name}] sync failed: {e}")
            exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
