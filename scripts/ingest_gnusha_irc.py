"""Backfill clean human IRC messages from gnusha.org.

Only two feeds are in scope:

* #bitcoin-core-dev
* #bitcoin-core-pr-reviews

The parser deliberately drops joins, quits, parts, nick changes, logger
markers, empty messages, meeting boundary commands, and known bots. Those raw
events remain available from gnusha; Sabio stores only human messages/actions.

Safe to rerun: before resolving people or inserting rows, each daily file is
compared with the source positions already present in ``irc_events``. The
database uniqueness constraint and ``ON CONFLICT DO NOTHING`` are a second
idempotency guard.

Review Club dates/titles come from bitcoincore.reviews' one-page meeting index.
That provides a reliable primary PR correlation without storing a separate
conversation table. Core weekly meetings are recognized from
``#startmeeting``/``#endmeeting`` markers; explicit PR/issue/commit/BIP links
on individual messages take precedence.

Run ``jobs.sync_irc`` on a schedule for bounded incremental updates. This
script is also the one-time backfill entry point:

    python scripts/ingest_gnusha_irc.py
    python scripts/ingest_gnusha_irc.py --since 2025-01-01
    python scripts/ingest_gnusha_irc.py --since 2025-01-01 --dry-run
"""

import argparse
import hashlib
import http.client
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg2
from bs4 import BeautifulSoup
from psycopg2.extras import Json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_gnusha_irc")

SOURCE = "gnusha"
BASE_URL = "https://gnusha.org"
REVIEW_MEETINGS_URL = "https://bitcoincore.reviews/meetings/"
REVIEW_BASE_URL = "https://bitcoincore.reviews"
CHANNELS = ("bitcoin-core-dev", "bitcoin-core-pr-reviews")

# Gnusha's log clock follows America/Los_Angeles. The same Review Club
# #startmeeting appears at 09:00 in winter / 10:00 in summer there and 17:00
# UTC on the rendered Review Club transcript.
LOG_TIMEZONE = ZoneInfo("America/Los_Angeles")

USER_AGENT = "sabio-bitcoin-research/0.1 (+local research archive)"
FETCH_TIMEOUT = 30
FETCH_RETRIES = 4
FETCH_RETRY_BACKOFF = 2.0
REQUEST_DELAY = 0.25
_ADVISORY_LOCK_KEY = 727100610

_LOG_LINK_RE = re.compile(r'href="(?P<date>\d{4}-\d{2}-\d{2})\.log"')
_MESSAGE_RE = re.compile(
    r"^(?P<clock>\d{2}:\d{2})\s+<(?P<nick>[^>]+)>\s?(?P<body>.*)$"
)
_ACTION_RE = re.compile(
    r"^(?P<clock>\d{2}:\d{2})\s+\*\s+(?P<nick>\S+)\s*(?P<body>.*)$"
)
_NICK_CHANGE_RE = re.compile(
    r"^\d{2}:\d{2}\s+-!-\s+(?P<old>\S+).*?\sis now known as\s(?P<new>\S+)"
)
_MEETING_START_RE = re.compile(r"^#startmeeting\b", re.IGNORECASE)
_MEETING_END_RE = re.compile(r"^#endmeeting\b", re.IGNORECASE)
_GITHUB_REF_RE = re.compile(
    r"https?://github\.com/(?P<repo>[\w.-]+/[\w.-]+)/(?P<kind>pull|issues|commit)/"
    r"(?P<value>[A-Fa-f0-9]{7,64}|\d+)"
)
_PR_TEXT_RE = re.compile(r"\b(?:PR|pull request)\s*#\s*(?P<number>\d+)\b", re.IGNORECASE)
_BIP_RE = re.compile(r"\bBIP[- ]?(?P<number>\d{1,4})\b", re.IGNORECASE)

_BOT_NICKS = frozenset(
    {
        "andy-logbot",
        "bitcoin-git",
        "chanserv",
        "core-meetingbot",
        "corebot",
        "gribble",
        "lightningbot",
        "meetingbot",
        "nickserv",
        "paperbot",
    }
)
_BOT_NICK_RE = re.compile(r"^(?:github\d+|.*(?:meetingbot|logbot))`?$", re.IGNORECASE)


@dataclass(frozen=True)
class KnownIdentity:
    primary_irc_nick: str
    display_name: str
    github_username: str
    aliases: tuple[str, ...]


_KNOWN_IDENTITIES = (
    KnownIdentity("sipa", "Pieter Wuille", "sipa", ("sipa",)),
    KnownIdentity("gmaxwell", "Gregory Maxwell", "gmaxwell", ("gmaxwell",)),
    KnownIdentity("wumpus", "Wladimir J. van der Laan", "laanwj", ("wumpus", "laanwj")),
    KnownIdentity("achow101", "Andrew Chow", "achow101", ("achow101",)),
    KnownIdentity("bluematt", "Matt Corallo", "TheBlueMatt", ("bluematt",)),
    KnownIdentity("jeremyrubin", "Jeremy Rubin", "JeremyRubin", ("jeremyrubin",)),
    KnownIdentity("glozow", "Gloria Zhao", "glozow", ("glozow", "gzhao408")),
    KnownIdentity("fanquake", "Michael Ford", "fanquake", ("fanquake",)),
    KnownIdentity("marcofalke", "Marco Falke", "MarcoFalke", ("marcofalke",)),
    KnownIdentity("jonatack", "Jon Atack", "jonatack", ("jonatack",)),
    KnownIdentity("instagibbs", "Greg Sanders", "instagibbs", ("instagibbs",)),
    KnownIdentity("aj", "Anthony Towns", "ajtowns", ("aj", "_aj_", "ajtowns")),
    KnownIdentity("luke-jr", "Luke Dashjr", "luke-jr", ("luke-jr",)),
    KnownIdentity("jnewbery", "John Newbery", "jnewbery", ("jnewbery",)),
    KnownIdentity("thestack", "Sebastian Falbesoner", "theStack", ("thestack",)),
    KnownIdentity("ryanofsky", "Russell Yanofsky", "ryanofsky", ("ryanofsky",)),
    KnownIdentity("darosior", "Antoine Poinsot", "darosior", ("darosior",)),
    KnownIdentity("harding", "David A. Harding", "harding", ("harding",)),
    KnownIdentity("kanzure", "Bryan Bishop", "kanzure", ("kanzure",)),
    KnownIdentity("provoostenator", "Sjors Provoost", "Sjors", ("provoostenator", "sjors")),
    KnownIdentity("cfields", "Cory Fields", "cfields", ("cfields",)),
    KnownIdentity("jtimon", "Jorge Timón", "jtimon", ("jtimon",)),
    KnownIdentity("petertodd", "Peter Todd", "petertodd", ("petertodd",)),
    KnownIdentity("amiti", "Amiti Uttarwar", "amitiuttarwar", ("amiti",)),
    KnownIdentity("murch", "Mark Erhardt", "murchandamus", ("murch",)),
)

_IDENTITY_BY_ALIAS: dict[str, KnownIdentity] = {}
for _identity in _KNOWN_IDENTITIES:
    for _alias in _identity.aliases:
        _IDENTITY_BY_ALIAS[_alias.casefold()] = _identity


@dataclass(frozen=True)
class Context:
    kind: str
    key: str
    title: str | None
    url: str


@dataclass(frozen=True)
class LogFile:
    channel: str
    log_date: date
    url: str


@dataclass(frozen=True)
class IRCEvent:
    channel: str
    log_date: date
    line_number: int
    posted_at: datetime
    event_type: str
    nick: str
    normalized_nick: str
    identity_hint: str
    body: str
    raw_line: str
    source_url: str
    source_file_sha: str
    context: Context | None


_SELECT_EXISTING_LINES_SQL = """
SELECT line_number
FROM irc_events
WHERE source = %(source)s
  AND channel = %(channel)s
  AND log_date = %(log_date)s
"""

_INSERT_EVENT_SQL = """
INSERT INTO irc_events (
    source, network, channel, log_date, line_number, posted_at, event_type,
    nick, normalized_nick, body, raw_line, person_id, context_kind,
    context_key, context_title, context_url, source_url, source_file_sha, raw
)
VALUES (
    %(source)s, %(network)s, %(channel)s, %(log_date)s, %(line_number)s,
    %(posted_at)s, %(event_type)s, %(nick)s, %(normalized_nick)s, %(body)s,
    %(raw_line)s, %(person_id)s, %(context_kind)s, %(context_key)s,
    %(context_title)s, %(context_url)s, %(source_url)s, %(source_file_sha)s,
    %(raw)s
)
ON CONFLICT (source, channel, log_date, line_number) DO NOTHING
RETURNING id
"""

_SELECT_PERSON_BY_IRC_SQL = """
SELECT id
FROM people
WHERE irc_nick = %(irc_nick)s
LIMIT 1
"""

_SELECT_PERSON_BY_GITHUB_SQL = """
SELECT id
FROM people
WHERE lower(github_username) = lower(%(github_username)s)
ORDER BY canonical_person_id NULLS FIRST, id
LIMIT 1
"""

_SELECT_PERSON_BY_UNIQUE_GITHUB_SQL = """
SELECT min(root_id)
FROM (
    SELECT coalesce(canonical_person_id, id) AS root_id
    FROM people
    WHERE lower(github_username) = lower(%(github_username)s)
) matches
HAVING count(DISTINCT root_id) = 1
"""

_SELECT_PERSON_BY_UNIQUE_ALIAS_SQL = """
SELECT min(person_id)
FROM person_aliases
WHERE lower(alias) = lower(%(alias)s)
HAVING count(DISTINCT person_id) = 1
"""

_INSERT_UNKNOWN_PERSON_SQL = """
WITH inserted AS (
    INSERT INTO people (display_name, irc_nick)
    VALUES (%(display_name)s, %(irc_nick)s)
    ON CONFLICT (irc_nick) DO NOTHING
    RETURNING id
)
SELECT id, TRUE AS created FROM inserted
UNION ALL
SELECT id, FALSE AS created
FROM people
WHERE irc_nick = %(irc_nick)s
  AND NOT EXISTS (SELECT 1 FROM inserted)
LIMIT 1
"""

_INSERT_KNOWN_PERSON_SQL = """
INSERT INTO people (display_name, github_username, irc_nick)
VALUES (%(display_name)s, %(github_username)s, %(irc_nick)s)
RETURNING id
"""

_UPDATE_KNOWN_PERSON_SQL = """
UPDATE people
SET display_name = coalesce(display_name, %(display_name)s),
    github_username = coalesce(github_username, %(github_username)s),
    irc_nick = coalesce(irc_nick, %(irc_nick)s)
WHERE id = %(person_id)s
"""

_INSERT_ALIAS_SQL = """
INSERT INTO person_aliases (person_id, alias)
VALUES (%(person_id)s, %(alias)s)
ON CONFLICT DO NOTHING
"""


def _fetch_bytes(url: str, *, throttle: bool = False) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
                payload = response.read()
            if throttle:
                time.sleep(REQUEST_DELAY)
            return payload
        except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
            if attempt == FETCH_RETRIES:
                raise
            delay = FETCH_RETRY_BACKOFF * attempt
            logger.warning(
                "fetch failed (%r), retrying in %.0fs (%d/%d): %s",
                error,
                delay,
                attempt,
                FETCH_RETRIES,
                url,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable fetch retry state")


def parse_log_index(
    channel: str,
    html: str,
    *,
    since: date | None = None,
    until: date | None = None,
) -> list[LogFile]:
    if channel not in CHANNELS:
        raise ValueError(f"unsupported IRC channel: {channel}")

    files: list[LogFile] = []
    seen_dates: set[date] = set()
    for match in _LOG_LINK_RE.finditer(html):
        log_date = date.fromisoformat(match.group("date"))
        if log_date in seen_dates:
            continue
        if since is not None and log_date < since:
            continue
        if until is not None and log_date > until:
            continue
        seen_dates.add(log_date)
        files.append(
            LogFile(
                channel=channel,
                log_date=log_date,
                url=f"{BASE_URL}/{channel}/{log_date.isoformat()}.log",
            )
        )
    files.sort(key=lambda item: item.log_date)
    return files


def list_log_files(
    channel: str,
    *,
    since: date | None = None,
    until: date | None = None,
    max_files: int | None = None,
) -> list[LogFile]:
    index_url = f"{BASE_URL}/{channel}/"
    html = _fetch_bytes(index_url).decode("utf-8", errors="replace")
    files = parse_log_index(channel, html, since=since, until=until)
    if max_files is not None:
        files = files[-max_files:]
    return files


def parse_review_contexts(html: str) -> dict[date, Context]:
    """Parse the Review Club's rendered meeting index in one request."""

    soup = BeautifulSoup(html, "html.parser")
    contexts: dict[date, Context] = {}
    for row in soup.select("tr.Home-posts-post"):
        date_cell = row.select_one("td.Home-posts-post-date")
        title_link = row.select_one("a.Home-posts-post-title[href]")
        if date_cell is None or title_link is None:
            continue
        try:
            meeting_date = datetime.strptime(
                date_cell.get_text(" ", strip=True),
                "%d %b %Y",
            ).date()
        except ValueError:
            continue

        title = title_link.get_text(" ", strip=True)
        href = str(title_link["href"])
        page_url = urllib.parse.urljoin(REVIEW_BASE_URL, href)
        pr_match = re.match(r"^#(?P<number>\d+)\s*(?P<title>.*)$", title)
        if pr_match is not None:
            pr_number = int(pr_match.group("number"))
            context = Context(
                kind="github_pr",
                key=f"bitcoin/bitcoin#{pr_number}",
                title=title,
                url=f"https://github.com/bitcoin/bitcoin/pull/{pr_number}",
            )
        else:
            slug = href.strip("/")
            context = Context(
                kind="other",
                key=f"review_club:{slug}",
                title=title,
                url=page_url,
            )

        if meeting_date in contexts:
            logger.warning(
                "multiple Review Club entries found for %s; keeping the first",
                meeting_date,
            )
            continue
        contexts[meeting_date] = context
    return contexts


def fetch_review_contexts() -> dict[date, Context]:
    html = _fetch_bytes(REVIEW_MEETINGS_URL).decode("utf-8", errors="replace")
    return parse_review_contexts(html)


def normalize_nick(nick: str) -> str:
    return nick.strip().lstrip("~&@%+").casefold()


def known_identity_for_nick(nick: str) -> KnownIdentity | None:
    normalized = normalize_nick(nick)
    identity = _IDENTITY_BY_ALIAS.get(normalized)
    if identity is not None:
        return identity

    # Known contributors often acquire trailing underscores/backticks when
    # their preferred nick is temporarily occupied. Only apply this heuristic
    # when the stripped base is in the curated map; never merge unknown users.
    stripped = normalized.rstrip("_`")
    if stripped != normalized:
        return _IDENTITY_BY_ALIAS.get(stripped)
    return None


def is_bot_nick(nick: str) -> bool:
    normalized = normalize_nick(nick)
    return normalized in _BOT_NICKS or _BOT_NICK_RE.fullmatch(normalized) is not None


def extract_explicit_context(body: str) -> Context | None:
    reference = _GITHUB_REF_RE.search(body)
    if reference is not None:
        repository = reference.group("repo")
        reference_kind = reference.group("kind")
        value = reference.group("value")
        if reference_kind == "pull":
            kind = "github_pr"
            key = f"{repository}#{value}"
        elif reference_kind == "issues":
            kind = "github_issue"
            key = f"{repository}#{value}"
        else:
            kind = "commit"
            key = f"{repository}@{value}"
        return Context(
            kind=kind,
            key=key,
            title=None,
            url=reference.group(0),
        )

    pr_match = _PR_TEXT_RE.search(body)
    if pr_match is not None:
        number = int(pr_match.group("number"))
        return Context(
            kind="github_pr",
            key=f"bitcoin/bitcoin#{number}",
            title=None,
            url=f"https://github.com/bitcoin/bitcoin/pull/{number}",
        )

    bip_match = _BIP_RE.search(body)
    if bip_match is not None:
        number = int(bip_match.group("number"))
        return Context(
            kind="bip",
            key=f"bip:{number}",
            title=f"BIP {number}",
            url=f"https://github.com/bitcoin/bips/blob/master/bip-{number:04d}.mediawiki",
        )
    return None


def _timestamp(log_date: date, clock: str) -> datetime:
    hour_text, minute_text = clock.split(":", 1)
    local_timestamp = datetime.combine(
        log_date,
        datetime_time(hour=int(hour_text), minute=int(minute_text)),
        tzinfo=LOG_TIMEZONE,
    )
    return local_timestamp.astimezone(timezone.utc)


def _weekly_context(channel: str, log_date: date, source_url: str) -> Context:
    return Context(
        kind="weekly_meeting",
        key=f"{channel}:{log_date.isoformat()}",
        title=f"Bitcoin Core weekly meeting — {log_date.isoformat()}",
        url=source_url,
    )


def parse_log(
    channel: str,
    log_date: date,
    text: str,
    *,
    review_contexts: dict[date, Context] | None = None,
) -> tuple[list[IRCEvent], Counter]:
    """Parse one raw daily log, returning only clean human conversation."""

    if channel not in CHANNELS:
        raise ValueError(f"unsupported IRC channel: {channel}")

    source_url = f"{BASE_URL}/{channel}/{log_date.isoformat()}.log"
    source_file_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    review_context = None
    if review_contexts is not None and channel == "bitcoin-core-pr-reviews":
        review_context = review_contexts.get(log_date)

    events: list[IRCEvent] = []
    stats: Counter = Counter()
    in_weekly_meeting = False
    nick_links: dict[str, str] = {}

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stats["raw_lines"] += 1

        nick_change = _NICK_CHANGE_RE.match(raw_line)
        if nick_change is not None:
            old_nick = normalize_nick(nick_change.group("old"))
            new_nick = normalize_nick(nick_change.group("new"))
            nick_links[new_nick] = nick_links.get(old_nick, old_nick)
            stats["dropped_non_message"] += 1
            continue

        event_type = "message"
        parsed = _MESSAGE_RE.match(raw_line)
        if parsed is None:
            parsed = _ACTION_RE.match(raw_line)
            event_type = "action"
        if parsed is None:
            stats["dropped_non_message"] += 1
            continue

        nick = parsed.group("nick").strip().lstrip("~&@%+")
        normalized_nick = normalize_nick(nick)
        body = parsed.group("body").replace("\x00", "").strip()
        if not normalized_nick or not body:
            stats["dropped_empty"] += 1
            continue
        if is_bot_nick(normalized_nick):
            stats["dropped_bot"] += 1
            continue

        if _MEETING_START_RE.match(body):
            if channel == "bitcoin-core-dev":
                in_weekly_meeting = True
            stats["dropped_meeting_control"] += 1
            continue
        if _MEETING_END_RE.match(body):
            if channel == "bitcoin-core-dev":
                in_weekly_meeting = False
            stats["dropped_meeting_control"] += 1
            continue

        context = review_context
        if context is None:
            context = extract_explicit_context(body)
        if context is None and channel == "bitcoin-core-dev" and in_weekly_meeting:
            context = _weekly_context(channel, log_date, source_url)

        if context is None:
            stats["context_none"] += 1
        else:
            stats[f"context_{context.kind}"] += 1

        identity_hint = nick_links.get(normalized_nick, normalized_nick)
        events.append(
            IRCEvent(
                channel=channel,
                log_date=log_date,
                line_number=line_number,
                posted_at=_timestamp(log_date, parsed.group("clock")),
                event_type=event_type,
                nick=nick,
                normalized_nick=normalized_nick,
                identity_hint=identity_hint,
                body=body,
                raw_line=raw_line,
                source_url=source_url,
                source_file_sha=source_file_sha,
                context=context,
            )
        )
        stats["kept"] += 1

    return events, stats


def _existing_line_numbers(cur, channel: str, log_date: date) -> set[int]:
    cur.execute(
        _SELECT_EXISTING_LINES_SQL,
        {"source": SOURCE, "channel": channel, "log_date": log_date},
    )
    return {row[0] for row in cur.fetchall()}


def _insert_alias(cur, person_id: int, alias: str) -> None:
    cleaned = alias.strip()
    if not cleaned:
        return
    cur.execute(_INSERT_ALIAS_SQL, {"person_id": person_id, "alias": cleaned})


def _resolve_person(
    cur,
    event: IRCEvent,
    cache: dict[str, int],
    stats: Counter,
) -> int:
    identity = known_identity_for_nick(event.normalized_nick)
    cache_key = event.identity_hint
    if identity is not None:
        cache_key = identity.primary_irc_nick
    if cache_key in cache:
        person_id = cache[cache_key]
        _insert_alias(cur, person_id, event.nick)
        return person_id

    primary_irc_nick = cache_key
    cur.execute(_SELECT_PERSON_BY_IRC_SQL, {"irc_nick": primary_irc_nick})
    row = cur.fetchone()
    person_id = row[0] if row is not None else None

    if identity is not None:
        if person_id is None:
            cur.execute(
                _SELECT_PERSON_BY_GITHUB_SQL,
                {"github_username": identity.github_username},
            )
            row = cur.fetchone()
            person_id = row[0] if row is not None else None

        params = {
            "display_name": identity.display_name,
            "github_username": identity.github_username,
            "irc_nick": identity.primary_irc_nick,
        }
        if person_id is None:
            cur.execute(_INSERT_KNOWN_PERSON_SQL, params)
            person_id = cur.fetchone()[0]
            stats["people_created_known"] += 1
        else:
            cur.execute(_UPDATE_KNOWN_PERSON_SQL, {**params, "person_id": person_id})
            stats["people_linked_known"] += 1

        _insert_alias(cur, person_id, identity.display_name)
        for alias in identity.aliases:
            _insert_alias(cur, person_id, alias)
    elif person_id is None:
        # An exact IRC-nick/GitHub-username match is a stable account-key
        # match, not a fuzzy display-name guess. This covers contributors
        # whose IRC and GitHub handles are the same without requiring every
        # such person to be maintained in _KNOWN_IDENTITIES. Multiple people
        # rows can share a GitHub username, so only use the match when every
        # row belongs to the same canonical root.
        cur.execute(
            _SELECT_PERSON_BY_UNIQUE_GITHUB_SQL,
            {"github_username": event.normalized_nick},
        )
        row = cur.fetchone()
        person_id = row[0] if row is not None else None
        if person_id is not None:
            stats["people_linked_exact_github"] += 1

    if identity is None and person_id is None:
        # Nick-change events are consumed as identity hints but not stored as
        # IRC content. Reuse an observed spelling only when it identifies
        # exactly one existing person; ambiguous display-name aliases are not
        # enough evidence to merge people.
        cur.execute(_SELECT_PERSON_BY_UNIQUE_ALIAS_SQL, {"alias": event.nick})
        row = cur.fetchone()
        person_id = row[0] if row is not None else None

    if identity is None and person_id is None:
        cur.execute(
            _INSERT_UNKNOWN_PERSON_SQL,
            {
                "display_name": event.nick,
                "irc_nick": primary_irc_nick,
            },
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"failed to resolve IRC person {primary_irc_nick}")
        person_id, created = row
        if created:
            stats["people_created_unknown"] += 1

    _insert_alias(cur, person_id, event.nick)
    cache[cache_key] = person_id
    cache[event.normalized_nick] = person_id
    return person_id


def _event_params(event: IRCEvent, person_id: int) -> dict[str, Any]:
    context = event.context
    return {
        "source": SOURCE,
        "network": None,
        "channel": event.channel,
        "log_date": event.log_date,
        "line_number": event.line_number,
        "posted_at": event.posted_at,
        "event_type": event.event_type,
        "nick": event.nick,
        "normalized_nick": event.normalized_nick,
        "body": event.body,
        "raw_line": event.raw_line,
        "person_id": person_id,
        "context_kind": context.kind if context is not None else None,
        "context_key": context.key if context is not None else None,
        "context_title": context.title if context is not None else None,
        "context_url": context.url if context is not None else None,
        "source_url": event.source_url,
        "source_file_sha": event.source_file_sha,
        "raw": Json(
            {
                "raw_line": event.raw_line,
                "identity_hint": event.identity_hint,
                "log_timezone": str(LOG_TIMEZONE),
            }
        ),
    }


def _connect_and_lock():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%(key)s)", {"key": _ADVISORY_LOCK_KEY})
    if not cur.fetchone()[0]:
        cur.close()
        conn.close()
        raise RuntimeError("another gnusha IRC ingestion job is already running")
    return conn, cur


def ingest(
    *,
    channels: tuple[str, ...] = CHANNELS,
    since_by_channel: dict[str, date | None] | None = None,
    until: date | None = None,
    max_files: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    for channel in channels:
        if channel not in CHANNELS:
            raise ValueError(f"unsupported IRC channel: {channel}")

    since_by_channel = since_by_channel or {}
    review_contexts: dict[date, Context] = {}
    if "bitcoin-core-pr-reviews" in channels:
        review_contexts = fetch_review_contexts()
    files: list[LogFile] = []
    for channel in channels:
        channel_files = list_log_files(
            channel,
            since=since_by_channel.get(channel),
            until=until,
            max_files=max_files,
        )
        files.extend(channel_files)

    totals: Counter = Counter()
    totals["files_selected"] = len(files)
    person_cache: dict[str, int] = {}
    conn = cur = None
    if not dry_run:
        conn, cur = _connect_and_lock()

    try:
        for file in files:
            logger.info("fetching %s", file.url)
            text = _fetch_bytes(file.url, throttle=True).decode("utf-8", errors="replace")
            events, parse_stats = parse_log(
                file.channel,
                file.log_date,
                text,
                review_contexts=review_contexts,
            )
            totals.update(parse_stats)
            totals["files_fetched"] += 1

            if dry_run:
                continue

            existing_lines = _existing_line_numbers(cur, file.channel, file.log_date)
            new_events = [event for event in events if event.line_number not in existing_lines]
            totals["already_present"] += len(events) - len(new_events)

            try:
                for event in new_events:
                    person_id = _resolve_person(cur, event, person_cache, totals)
                    cur.execute(_INSERT_EVENT_SQL, _event_params(event, person_id))
                    if cur.fetchone() is not None:
                        totals["inserted"] += 1
                    else:
                        totals["conflicted"] += 1
                conn.commit()
            except Exception:
                conn.rollback()
                raise

            logger.info(
                "%s: kept=%d new=%d inserted_total=%d dropped_non_message=%d dropped_bot=%d",
                file.url,
                len(events),
                len(new_events),
                totals["inserted"],
                parse_stats["dropped_non_message"],
                parse_stats["dropped_bot"],
            )
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()

    result = dict(totals)
    logger.info("IRC ingestion complete: %s", json.dumps(result, sort_keys=True))
    return result


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must use YYYY-MM-DD") from error


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill filtered human IRC messages from two gnusha.org feeds."
    )
    parser.add_argument(
        "--channel",
        action="append",
        choices=CHANNELS,
        help="channel to ingest; repeat to select both (default: both)",
    )
    parser.add_argument("--since", type=_iso_date, help="inclusive source date")
    parser.add_argument("--until", type=_iso_date, help="inclusive source date")
    parser.add_argument(
        "--max-files",
        type=_positive_int,
        help="newest N matching daily files per selected channel",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and parse without opening a database connection",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    channels = tuple(args.channel) if args.channel else CHANNELS
    since_by_channel = {channel: args.since for channel in channels}
    ingest(
        channels=channels,
        since_by_channel=since_by_channel,
        until=args.until,
        max_files=args.max_files,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
