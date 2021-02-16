CREATE TABLE IF NOT EXISTS message
(
    id              INTEGER PRIMARY KEY,
    chat_id         INT     NOT NULL,
    parent          INT,
    is_bot_reaction BOOLEAN NOT NULL,
    expanded        BOOLEAN NOT NULL DEFAULT FALSE,

    FOREIGN KEY (parent) REFERENCES message (id)
);


CREATE TABLE IF NOT EXISTS reaction
(
    id        INTEGER PRIMARY KEY,
    parent    INT  NOT NULL,
    author_id INT  NOT NULL,
    author    TEXT NOT NULL,
    type      TEXT NOT NULL,
    timestamp INT  NOT NULL,

    FOREIGN KEY (parent) REFERENCES message (id)
);
