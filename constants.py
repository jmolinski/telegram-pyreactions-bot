CONFIG_FILENAME = "conf.json"
DB_FILENAME = "test.db"

EMPTY_MSG = "\xad\xad"
INFORMATION_EMOJI = "ℹ️"
_LENNYFACE = b"( \xcd\xa1\xc2\xb0 \xcd\x9c\xca\x96 \xcd\xa1\xc2\xb0)".decode()

TEXTUAL_NORMALIZATION = {
    "xd": "xD",
    "rigcz": "RiGCz",
    "rel": "rel",
    "rak": "rak",
    "<3": "❤️",
    "lenny": _LENNYFACE,
    "nierel": "nierel",
    "baza:": "baza",
    "based:": "baza",
}
TEXTUAL_REACTIONS = (
    "+1",
    "-1",
    "xD",
    "rel",
    "nierel",
    "RiGCz",
    "rak",
    "lenny",
    _LENNYFACE,
    "baza",
)

REACTIONS_IN_SINGLE_MSG_LIMIT = 3
