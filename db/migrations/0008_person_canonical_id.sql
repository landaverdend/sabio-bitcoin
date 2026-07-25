-- depends: 0007_person_aliases

-- Two people rows can legitimately be the same real human under different
-- channel-specific keys (a GitHub-linked email row and a BitcoinTalk-only
-- row with no email, for instance) with zero shared column between them --
-- nothing to automatically join on. merge_people.py collapses that into one
-- row, but that's destructive (picks one canonical email, the rest stop
-- being independently resolvable) and refuses on its own when rows
-- disagree on email, which is the common case (achow101 alone has 5
-- distinct emails across rows that are unmistakably the same person).
--
-- canonical_person_id is the non-destructive alternative: point every
-- row that's the same real person at one anchor row, without deleting or
-- picking a winner. Every row keeps its own email/username exactly as-is
-- and stays independently queryable; canonical_person_id just says "list
-- and count this alongside that other row when showing a human a single
-- profile." A person page or people-list query groups by
-- coalesce(canonical_person_id, id) to collapse the group into one card.
--
-- Points at another people row, never at itself, and only ever one level
-- deep (the anchor row's own canonical_person_id must be NULL) -- chains
-- would need every consumer to walk them instead of a flat coalesce().
ALTER TABLE people ADD COLUMN canonical_person_id BIGINT REFERENCES people(id)
    CHECK (canonical_person_id IS NULL OR canonical_person_id != id);

CREATE INDEX people_canonical_person_id_idx ON people (canonical_person_id);
