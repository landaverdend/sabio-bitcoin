-- depends: 0006_people_bitcointalk_username

-- A person's display_name is a single column, but the same real person can
-- post under a different name per channel (a mailing-list signature vs a
-- BitcoinTalk forum handle vs a GitHub profile name) -- resolve()'s fuzzy
-- match only ever saw whichever one name happened to land in display_name,
-- so a query using any other name variant silently missed a person we
-- already know. person_aliases collects every distinct name string ever
-- seen for a known person, across every channel, so any of them resolves.
--
-- Not a fix for two *separate* rows that are secretly the same real person
-- (e.g. a mailing-list row and a forum-only row with no shared key) --
-- that's scripts/merge_people.py's job. This only enriches a row that's
-- already correctly identified.
CREATE TABLE person_aliases (
    person_id BIGINT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    PRIMARY KEY (person_id, alias)
);

CREATE INDEX person_aliases_alias_trgm_idx ON person_aliases USING GIN (alias gin_trgm_ops);

-- Backfill from what's already in the data: every author name attached to a
-- known person's messages (mailing list *and* BitcoinTalk both flow through
-- the same messages.author column), plus each person's current display_name
-- itself in case it was never derived from a messages row (e.g. a
-- GitHub-only contributor discovered by scripts/link_github_contributors.py).
INSERT INTO person_aliases (person_id, alias)
SELECT DISTINCT person_id, author
FROM messages
WHERE person_id IS NOT NULL AND author IS NOT NULL AND author != ''
ON CONFLICT DO NOTHING;

INSERT INTO person_aliases (person_id, alias)
SELECT id, display_name
FROM people
WHERE display_name IS NOT NULL AND display_name != ''
ON CONFLICT DO NOTHING;
