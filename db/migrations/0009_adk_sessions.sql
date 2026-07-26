-- depends: 0008_person_canonical_id

-- Persistent conversation storage owned by google-adk 1.13's
-- DatabaseSessionService. ADK still calls SQLAlchemy create_all() as a
-- compatibility fallback, but recording its tables here makes their schema
-- explicit, reviewable, backed up, and reproducible before the API starts.
--
-- These names and columns are part of ADK's persistence contract. Upgrade
-- this migration/schema deliberately before moving beyond the pinned ADK
-- version in requirements.txt.
CREATE TABLE IF NOT EXISTS app_states (
    app_name VARCHAR(128) PRIMARY KEY,
    state JSONB NOT NULL,
    update_time TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    app_name VARCHAR(128) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    id VARCHAR(128) NOT NULL,
    state JSONB NOT NULL,
    create_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    update_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (app_name, user_id, id)
);

CREATE TABLE IF NOT EXISTS user_states (
    app_name VARCHAR(128) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    state JSONB NOT NULL,
    update_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (app_name, user_id)
);

CREATE TABLE IF NOT EXISTS events (
    id VARCHAR(128) NOT NULL,
    app_name VARCHAR(128) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    session_id VARCHAR(128) NOT NULL,
    invocation_id VARCHAR(256) NOT NULL,
    author VARCHAR(256) NOT NULL,
    branch VARCHAR(256),
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    content JSONB,
    actions BYTEA NOT NULL,
    long_running_tool_ids_json TEXT,
    grounding_metadata JSONB,
    partial BOOLEAN,
    turn_complete BOOLEAN,
    error_code VARCHAR(256),
    error_message VARCHAR(1024),
    interrupted BOOLEAN,
    PRIMARY KEY (id, app_name, user_id, session_id),
    FOREIGN KEY (app_name, user_id, session_id)
        REFERENCES sessions (app_name, user_id, id) ON DELETE CASCADE
);

-- ADK 1.13 does not declare lookup indexes beyond primary keys. These match
-- its hot paths: list a user's sessions and replay one session's events.
CREATE INDEX IF NOT EXISTS sessions_user_updated_idx
    ON sessions (app_name, user_id, update_time DESC);
CREATE INDEX IF NOT EXISTS events_session_timestamp_idx
    ON events (app_name, user_id, session_id, timestamp);
