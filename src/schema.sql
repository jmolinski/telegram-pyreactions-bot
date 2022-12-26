CREATE TABLE IF NOT EXISTS message
(
    id              INTEGER PRIMARY KEY,
    original_id     INT     NOT NULL,
    author_id       INT     NOT NULL,
    author          TEXT    NOT NULL,
    chat_id         INT     NOT NULL,
    parent          INTEGER,
    is_bot_reaction BOOLEAN NOT NULL,
    is_ranking      BOOLEAN NOT NULL,
    is_anon         BOOLEAN NOT NULL,
    expanded        BOOLEAN NOT NULL DEFAULT FALSE,

    FOREIGN KEY (parent) REFERENCES message (id)
);


CREATE TABLE IF NOT EXISTS reaction
(
    id        INTEGER PRIMARY KEY,
    parent    INTEGER NOT NULL,
    author_id INT  NOT NULL,
    author    TEXT NOT NULL,
    type      TEXT NOT NULL,
    timestamp INT  NOT NULL,

    INDEX parent_idx (parent),

    FOREIGN KEY (parent) REFERENCES message (id)
);
