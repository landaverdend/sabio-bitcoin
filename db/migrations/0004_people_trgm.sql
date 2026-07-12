-- depends: 0003_people

CREATE INDEX people_display_name_trgm_idx ON people USING GIN (display_name gin_trgm_ops);
CREATE INDEX people_email_trgm_idx ON people USING GIN (email gin_trgm_ops);
