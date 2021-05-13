CREATE TABLE IF NOT EXISTS message
(
    id              TEXT PRIMARY KEY,
    original_id     INT     NOT NULL,
    author_id       INT     NOT NULL,
    author          TEXT    NOT NULL,
    chat_id         INT     NOT NULL,
    parent          TEXT,
    is_bot_reaction BOOLEAN NOT NULL,
    is_ranking      BOOLEAN NOT NULL,
    expanded        BOOLEAN NOT NULL DEFAULT FALSE,

    FOREIGN KEY (parent) REFERENCES message (id)
);


CREATE TABLE IF NOT EXISTS reaction
(
    id        INTEGER PRIMARY KEY,
    parent    TEXT NOT NULL,
    author_id INT  NOT NULL,
    author    TEXT NOT NULL,
    type      TEXT NOT NULL,
    timestamp INT  NOT NULL,

    FOREIGN KEY (parent) REFERENCES message (id)
);
