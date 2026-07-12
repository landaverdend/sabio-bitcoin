DROP INDEX messages_title_trgm_idx;
DROP INDEX messages_email_trgm_idx;
DROP INDEX messages_author_trgm_idx;
DROP INDEX messages_search_vector_idx;
ALTER TABLE messages DROP COLUMN search_vector;
DROP EXTENSION IF EXISTS pg_trgm;
