DROP TABLE irc_events;
DROP INDEX people_irc_nick_trgm_idx;
ALTER TABLE people DROP COLUMN irc_nick;
