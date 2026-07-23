"""Link people to their GitHub account, and add git-only contributors people
doesn't know about yet (e.g. someone who never posted to the mailing list).

Identity comes from walking the repo's full commit history via GitHub's REST
API (no local clone anywhere in this project anymore) -- slower and more
API-call-hungry than reading a local clone would be (a full walk of
bitcoin/bitcoin's history is a few hundred paginated requests on top of the
per-email lookups below), but there's no local git object database left to
read. GitHub is then consulted per distinct email to check whether it's
linked to a verified account (one lightweight API call per distinct email --
verified to accept a plain email string, same as `git log --author`).

Only emails GitHub actually confirms are linked get written: an unlinked
email (bots, merge-script, decade-old drive-by contributors) is skipped
rather than added as noise -- see db/migrations/0005_people_github_username.sql.

Safe to re-run: matching an existing person updates github_username in place
(idempotent), and a new person is only ever inserted once (ON CONFLICT on
the existing email UNIQUE constraint).
"""

import logging
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from github import Auth, Github

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.repos.github_tools import REPOS as GITHUB_REPO_SLUGS  # noqa: E402
from db.client import get_connection  # noqa: E402

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("link_github_contributors")

REPO_NAME = "core"
_COMMIT_EVERY = 100

_SELECT_PERSON_SQL = "SELECT id FROM people WHERE email = %(email)s"
_UPDATE_GITHUB_USERNAME_SQL = "UPDATE people SET github_username = %(login)s WHERE email = %(email)s"
_INSERT_PERSON_SQL = """
INSERT INTO people (email, display_name, github_username)
VALUES (%(email)s, %(display_name)s, %(login)s)
ON CONFLICT (email) DO UPDATE SET github_username = EXCLUDED.github_username
"""


def _github_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    return Github(auth=Auth.Token(token)) if token else Github()


def local_git_identities(gh_repo) -> dict[str, tuple[str, int]]:
    """Every distinct commit-author email across a repo's full history,
    mapped to (most common author name for that email, total commit
    count). Walks the REST commits endpoint page by page -- see module
    docstring for why this replaced reading a local clone."""
    names_by_email: dict[str, Counter] = {}
    counts: Counter = Counter()
    for commit in gh_repo.get_commits():
        git_author = commit.commit.author
        if git_author is None or not git_author.email:
            continue
        names_by_email.setdefault(git_author.email, Counter())[git_author.name] += 1
        counts[git_author.email] += 1

    return {
        email: (names.most_common(1)[0][0], counts[email])
        for email, names in names_by_email.items()
    }


def github_login_for_email(gh_repo, email: str) -> str | None:
    """The GitHub login linked to this commit-author email, if GitHub has
    one on file -- checking just the most recent matching commit is enough,
    since account linking is per-email, not per-commit."""
    for commit in gh_repo.get_commits(author=email):
        return commit.author.login if commit.author is not None else None
    return None


def link(repo_name: str = REPO_NAME) -> dict:
    gh_repo = _github_client().get_repo(GITHUB_REPO_SLUGS[repo_name])
    identities = local_git_identities(gh_repo)
    logger.info(f"{len(identities)} distinct commit-author emails in repo history")

    updated = created = skipped = 0
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for i, (email, (name, _count)) in enumerate(identities.items(), start=1):
                login = github_login_for_email(gh_repo, email)
                if login is None:
                    skipped += 1
                    continue

                cur.execute(_SELECT_PERSON_SQL, {"email": email})
                if cur.fetchone():
                    cur.execute(_UPDATE_GITHUB_USERNAME_SQL, {"login": login, "email": email})
                    updated += 1
                else:
                    cur.execute(_INSERT_PERSON_SQL, {"email": email, "display_name": name, "login": login})
                    created += 1

                if i % _COMMIT_EVERY == 0:
                    conn.commit()
                    logger.info(
                        f"processed {i}/{len(identities)} "
                        f"(updated={updated}, created={created}, skipped={skipped})"
                    )

        conn.commit()
    finally:
        conn.close()

    logger.info(f"done: updated {updated}, created {created}, skipped {skipped}")
    return {"updated": updated, "created": created, "skipped": skipped}


if __name__ == "__main__":
    link()
