from __future__ import annotations

import re

from typing import Any, TypeVar, cast

import demoji

from src.settings import get_settings

T = TypeVar("T")

CUSTOM_REACTION_PATTERN = re.compile(r"!(r(eact)?)\s+(.*)")
ANON_MSG_PATTERN = re.compile(r"!(a(non)?)\s+([\s\S]*)")


def unique_list(lst: list[T]) -> list[T]:
    n = []
    for item in lst:
        if item not in n:
            n.append(item)
    return n


def split_into_chunks(lst: list[T], n: int) -> list[list[T]]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def get_name_from_author_obj(data: dict[Any, Any]) -> str:
    username = data["username"]
    first_name = data["first_name"]
    return cast(str, username or first_name)


def find_emojis_in_str(s: str) -> list[str]:
    return demoji.findall_list(s, desc=False)  # type: ignore


def get_reaction_representation(text: str, count: int, with_count: bool = False) -> str:
    if text == "-1":
        return f"-{count}"
    elif text == "+1":
        return f"+{count}"
    else:
        if with_count and count > 1:
            return f"{count} {text}"
        else:
            return text


def try_int(v: str, default: int | None = None) -> int | None:
    try:
        return int(v)
    except:
        return default


def is_disallowed_reaction(r: str) -> bool:
    if r[0] in "-+":
        as_int = try_int(r[1:])
        if as_int is not None and as_int != 1:
            return True

    return r in get_settings().disallowed_reactions


def extract_custom_reaction(t: str) -> str | None:
    t = t.strip()
    match = re.match(CUSTOM_REACTION_PATTERN, t)
    if match is None:
        return None

    reaction = match.group(3).strip()
    if not reaction or is_disallowed_reaction(reaction):
        return None

    return reaction


def extract_anon_message_text(t: str) -> str | None:
    t = t.strip()
    match = re.match(ANON_MSG_PATTERN, t)
    if match is None:
        return None

    reaction = match.group(3).strip()
    return reaction if reaction else None


def _escape_markdown_v2(txt: str) -> str:
    return re.sub("(?=[~>#+-=|{}.!])", "\\\\", txt)


def remove_emojis_from_text(txt: str) -> str:
    return demoji.replace(txt)  # type: ignore


def hash_string(s: str) -> int:
    # FNV-1a constants
    fnv_prime = 0x100000001B3
    fnv_offset_basis = 0xCBF29CE484222325

    h = fnv_offset_basis
    for c in s:
        h ^= ord(c)
        h *= fnv_prime
    return h & 0xFFFFFFFFFFFFFFF
