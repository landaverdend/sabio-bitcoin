-- depends: 0001_create_messages_table

CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE messages ADD COLUMN search_vector TSVECTOR GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(body, '')), 'B')
) STORED;

CREATE INDEX messages_search_vector_idx ON messages USING GIN (search_vector);
CREATE INDEX messages_author_trgm_idx ON messages USING GIN (author gin_trgm_ops);
CREATE INDEX messages_email_trgm_idx ON messages USING GIN (email gin_trgm_ops);
CREATE INDEX messages_title_trgm_idx ON messages USING GIN (title gin_trgm_ops);
