CREATE TABLE IF NOT EXISTS message
(
    id              INTEGER PRIMARY KEY,
    chat_id         INT     NOT NULL,
    is_reply        BOOLEAN NOT NULL,
    parent          INT,
    is_bot_reaction boolean NOT NULL,
    expanded        boolean not null default FALSE,

    FOREIGN KEY (parent) REFERENCES message (id)
);


CREATE TABLE IF NOT EXISTS reaction
(
    id        INTEGER PRIMARY KEY,
    parent    INT,
    author_id int  NOT NULL,
    author    TEXT NOT NULL,
    type      TEXT NOT NULL,

    FOREIGN KEY (parent) REFERENCES message (id)
);
