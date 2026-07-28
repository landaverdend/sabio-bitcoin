-- depends: 0009_adk_sessions

-- IRC archives are event streams rather than ordinary authored messages.
-- Ingestion filters connection events, log markers, known bots, empty lines,
-- and exact duplicates before insert; this table contains only clean human
-- messages and actions. The upstream archive remains the raw source of truth.
--
-- IRC has no email/account identifier, so people.irc_nick is the stable
-- channel-specific key used to make scheduled re-ingestion idempotent. Other
-- observed spellings and curated real-name mappings still live in
-- person_aliases.
ALTER TABLE people ADD COLUMN irc_nick TEXT UNIQUE;
CREATE INDEX people_irc_nick_trgm_idx
    ON people USING GIN (irc_nick gin_trgm_ops);

CREATE TABLE irc_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Source archive and IRC location. network is nullable because it is not
    -- always recoverable with confidence from historical log files.
    source TEXT NOT NULL,
    network TEXT,
    channel TEXT NOT NULL,
    log_date DATE NOT NULL,
    line_number INTEGER NOT NULL CHECK (line_number > 0),

    -- Gnusha timestamps have minute precision. line_number provides
    -- deterministic ordering for events that share a minute.
    posted_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('message', 'action')),

    -- nick is the source spelling after removing IRC privilege prefixes.
    -- normalized_nick is populated by ingestion for matching across spelling
    -- and case variants; neither field alone proves a real-world identity.
    nick TEXT NOT NULL CHECK (btrim(nick) != ''),
    normalized_nick TEXT NOT NULL CHECK (btrim(normalized_nick) != ''),
    body TEXT NOT NULL CHECK (btrim(body) != ''),
    raw_line TEXT NOT NULL,

    -- A meeting or bounded discussion can carry one primary correlation
    -- directly on every event. source_url cites the IRC line; context_url
    -- points to the PR, issue, BIP, commit, or meeting it is about.
    context_kind TEXT CHECK (
        context_kind IN (
            'github_pr',
            'github_issue',
            'bip',
            'commit',
            'weekly_meeting',
            'other'
        )
    ),
    context_key TEXT,
    context_title TEXT,
    context_url TEXT,

    person_id BIGINT REFERENCES people(id) ON DELETE SET NULL,

    source_url TEXT NOT NULL,
    source_file_sha TEXT,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- A scheduled run can safely refetch overlapping/current daily logs and
    -- upsert against this stable source position.
    UNIQUE (source, channel, log_date, line_number),

    -- Context is either absent or complete enough to query and link. A title
    -- is useful for display but optional when the source does not provide one.
    CHECK (
        (
            context_kind IS NULL
            AND context_key IS NULL
            AND context_title IS NULL
            AND context_url IS NULL
        )
        OR (
            context_kind IS NOT NULL
            AND context_key IS NOT NULL
            AND context_url IS NOT NULL
        )
    ),

    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', body)
    ) STORED
);

-- Conversation reconstruction reads a hit's neighboring events in timestamp
-- and source order. line_number resolves multiple events within one minute.
CREATE INDEX irc_events_timeline_idx
    ON irc_events (source, channel, posted_at, line_number);

-- Directly answers questions such as "show IRC discussion of Core PR #25038"
-- without requiring a separate conversation/reference table.
CREATE INDEX irc_events_context_reference_idx
    ON irc_events (context_kind, context_key)
    WHERE context_kind IS NOT NULL;

CREATE INDEX irc_events_person_id_idx
    ON irc_events (person_id);

CREATE INDEX irc_events_normalized_nick_idx
    ON irc_events (normalized_nick);

CREATE INDEX irc_events_search_vector_idx
    ON irc_events USING GIN (search_vector);
