-- depends: 0005_people_github_username

-- email stops being the required identity key: a channel can expose no email
-- at all (BitcoinTalk hides member emails, verified empirically against
-- several real profiles including board moderators) and a person still needs
-- a stable key to be created and deduped by. bitcointalk_username plays that
-- role for forum-only identities, the same way email does for mailing-list
-- ones -- UNIQUE so "one person per username" holds, same shape as email's
-- "one person per email" (multiple NULLs are allowed side by side in
-- Postgres, so rows lacking either key don't collide with each other).
ALTER TABLE people ALTER COLUMN email DROP NOT NULL;

ALTER TABLE people ADD COLUMN bitcointalk_username TEXT UNIQUE;
CREATE INDEX people_bitcointalk_username_trgm_idx ON people USING GIN (bitcointalk_username gin_trgm_ops);
