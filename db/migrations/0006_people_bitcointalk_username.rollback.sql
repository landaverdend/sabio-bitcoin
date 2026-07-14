DROP INDEX people_bitcointalk_username_trgm_idx;
ALTER TABLE people DROP COLUMN bitcointalk_username;
ALTER TABLE people ALTER COLUMN email SET NOT NULL;
