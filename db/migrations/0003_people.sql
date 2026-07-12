-- depends: 0002_search

CREATE TABLE people (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One person per email, skipping shared/relay addresses (more than 5 distinct
-- author-name spellings under one email -- grounded in the real data: 130 of
-- 131 multi-author emails top out at 4 spellings of the same person; only the
-- Google Groups relay address (bitcoindev@googlegroups.com) is an outlier at 63).
INSERT INTO people (email, display_name)
SELECT email, mode() WITHIN GROUP (ORDER BY author)
FROM messages
WHERE email IS NOT NULL
GROUP BY email
HAVING count(DISTINCT author) <= 5;

ALTER TABLE messages ADD COLUMN person_id BIGINT REFERENCES people(id);
UPDATE messages m SET person_id = p.id FROM people p WHERE m.email = p.email;
CREATE INDEX messages_person_id_idx ON messages (person_id);
