import sqlite3
from contextlib import contextmanager



@contextmanager
def get_conn():
    c = sqlite3.connect("test.db")
    yield c
    c.commit()
    c.close()


with open('schema.sql') as f:
    with get_conn() as conn:
        conn.executescript(f.read())
