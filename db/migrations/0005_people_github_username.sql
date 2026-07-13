-- depends: 0004_people_trgm

-- Nullable, deliberately NOT unique: the same real person can legitimately
-- end up as two different `people` rows (one per email, per the 1-person-
-- 1-email model) while sharing one github_username -- that's a useful signal
-- linking the two rows, not something to constrain against.
ALTER TABLE people ADD COLUMN github_username TEXT;
CREATE INDEX people_github_username_idx ON people (github_username);
