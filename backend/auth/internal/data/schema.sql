CREATE TABLE IF NOT EXISTS users (
    id           BIGSERIAL    PRIMARY KEY,
    username     VARCHAR(50)  NOT NULL UNIQUE,
    email        VARCHAR(150) NOT NULL UNIQUE,
    password     VARCHAR(255) NOT NULL,
    salt         VARCHAR(64)  NOT NULL,
    avatar_url   VARCHAR(255) NOT NULL DEFAULT '',
    status       VARCHAR(20)  NOT NULL DEFAULT 'unverified', -- unverified / active / banned
    role         VARCHAR(20)  NOT NULL DEFAULT 'user',       -- user / admin
    totp_secret  VARCHAR(64)  NOT NULL DEFAULT '',
    totp_enabled BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
