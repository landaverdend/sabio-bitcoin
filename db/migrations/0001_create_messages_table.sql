-- depends:

CREATE TABLE messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel TEXT NOT NULL,
    external_id TEXT NOT NULL,
    thread_id TEXT,
    author TEXT,
    email TEXT,
    title TEXT,
    body TEXT NOT NULL,
    url TEXT NOT NULL,
    posted_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (channel, external_id),
    UNIQUE (channel, url)
);

CREATE INDEX messages_channel_idx ON messages (channel);
CREATE INDEX messages_thread_id_idx ON messages (thread_id);
CREATE INDEX messages_posted_at_idx ON messages (posted_at DESC);
