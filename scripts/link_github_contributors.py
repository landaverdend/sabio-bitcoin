"""Link people to their GitHub account, and add git-only contributors people
doesn't know about yet (e.g. someone who never posted to the mailing list).

Walks each repo's full commit history exactly once via GitHub's REST API (no
local clone anywhere in this project anymore). Every commit response already
carries both the raw git author (name/email) *and* the linked GitHub account
(if any) in the same object -- there's no need for a second per-email lookup
pass, that was redundant work fetching something already visible in the
first walk. Commits come back newest-first, so only recording an email's
login the first time it's seen naturally captures its *most recent* linked
account, same as a dedicated per-email lookup would.

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

from agents.repos.github_tools import FORK_OF, REPOS as GITHUB_REPO_SLUGS  # noqa: E402
from db.client import get_connection  # noqa: E402

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("link_github_contributors")

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


_PROGRESS_EVERY = 2000  # commits, not pages -- a large repo's walk produced
# zero output for 20+ minutes with nothing to show for it once, indistinguishable
# from actually being stuck; this is the same fix already applied to
# scrape_bitcointalk.py's per-topic walk for the same reason.


def fork_point_since(client: Github, repo_name: str):
    """When repo_name is a documented fork (agents/repos/github_tools.FORK_OF),
    the commit-author date it last diverged from its base repo -- so the walk
    below can skip re-reading history the base repo's own pass already
    covered. None for repos that aren't a fork of another configured repo."""
    base_name = FORK_OF.get(repo_name)
    if base_name is None:
        return None
    base_repo = client.get_repo(GITHUB_REPO_SLUGS[base_name])
    fork_repo = client.get_repo(GITHUB_REPO_SLUGS[repo_name])
    fork_owner = GITHUB_REPO_SLUGS[repo_name].split("/")[0]
    comparison = base_repo.compare(base_repo.default_branch, f"{fork_owner}:{fork_repo.default_branch}")
    return comparison.merge_base_commit.commit.author.date


def repo_identities(gh_repo, repo_label: str = "", since=None) -> dict[str, tuple[str, str | None, int]]:
    """Every distinct commit-author email across a repo's history (or, for a
    fork, just history since it last diverged -- see fork_point_since),
    mapped to (most common author name for that email, linked GitHub login
    if any, total commit count). One pass over the REST commits endpoint --
    see module docstring for why a second per-email lookup pass isn't
    needed."""
    names_by_email: dict[str, Counter] = {}
    logins_by_email: dict[str, str | None] = {}
    counts: Counter = Counter()
    seen = 0
    commits = gh_repo.get_commits(since=since) if since else gh_repo.get_commits()
    for commit in commits:
        seen += 1
        if seen % _PROGRESS_EVERY == 0:
            logger.info(f"{repo_label}: walked {seen} commits so far, "
                        f"{len(names_by_email)} distinct emails found")
        git_author = commit.commit.author
        if git_author is None or not git_author.email:
            continue
        email = git_author.email
        names_by_email.setdefault(email, Counter())[git_author.name] += 1
        counts[email] += 1
        if email not in logins_by_email:
            logins_by_email[email] = commit.author.login if commit.author is not None else None

    return {
        email: (names.most_common(1)[0][0], logins_by_email[email], counts[email])
        for email, names in names_by_email.items()
    }


def link(repo_names: list[str] | None = None) -> dict:
    """Runs across every repo in agents/repos/github_tools.py's REPOS by
    default (currently core, knots, bips, secp256k1) -- pass repo_names to
    scope it to fewer. Identities naturally merge across repos: the same
    email showing up in more than one repo's history just re-updates the
    same person row (ON CONFLICT / the UPDATE branch below), not a
    duplicate, so processing order between repos doesn't matter."""
    repo_names = repo_names or list(GITHUB_REPO_SLUGS.keys())
    client = _github_client()

    updated = created = skipped = 0
    for repo_name in repo_names:
        gh_repo = client.get_repo(GITHUB_REPO_SLUGS[repo_name])
        since = fork_point_since(client, repo_name)
        if since is not None:
            logger.info(f"{repo_name}: fork of {FORK_OF[repo_name]}, scoping walk to commits since {since}")
        identities = repo_identities(gh_repo, repo_label=repo_name, since=since)
        logger.info(f"{repo_name}: {len(identities)} distinct commit-author emails in repo history")

        # Fresh connection per repo -- the discovery walk above (no DB activity,
        # GitHub-only) can run 40+ minutes for a large repo, and a connection
        # opened before it sits idle that whole time. A held-open connection
        # got reaped mid-run (psycopg2.OperationalError: server closed the
        # connection unexpectedly) once that idle stretch was long enough.
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                for i, (email, (name, login, _count)) in enumerate(identities.items(), start=1):
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
                            f"{repo_name}: processed {i}/{len(identities)} "
                            f"(updated={updated}, created={created}, skipped={skipped})"
                        )

                conn.commit()
                logger.info(f"{repo_name}: done")
        finally:
            conn.close()

    logger.info(f"done: updated {updated}, created {created}, skipped {skipped}")
    return {"updated": updated, "created": created, "skipped": skipped}


if __name__ == "__main__":
    link()
