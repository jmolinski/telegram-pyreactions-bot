from __future__ import annotations

import sqlite3

from contextlib import contextmanager
from typing import Iterator

from src import constants


CONNECTION: sqlite3.Connection | None = None


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    global CONNECTION
    if CONNECTION is None:
        CONNECTION = sqlite3.connect(constants.DB_FILENAME, check_same_thread=False)

    try:
        yield CONNECTION
    except:
        # TODO handle errors, recreate connection?
        # would the exception be raised here or in .commit?
        raise

    CONNECTION.commit()


def close_conn() -> None:
    global CONNECTION
    if CONNECTION is not None:
        CONNECTION.close()
        CONNECTION = None


with open(constants.SCHEMA_FILENAME) as f:
    with get_conn() as conn:
        conn.executescript(f.read())
